"""Retries, rate limiting and error translation — offline, with fake clocks and errors."""

import httpx
import pytest
from google.genai import errors as genai_errors

from flutter_rag.errors import UpstreamError
from flutter_rag.gemini_errors import to_upstream
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retry import call_with_retries


def test_retries_429_then_succeeds():
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise UpstreamError("gemini", "rate_limited", "quota", 429)
        return "ok"

    assert call_with_retries(fn, translate=to_upstream, sleep=sleeps.append) == "ok"
    assert len(calls) == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_retry_attempts_are_bounded():
    sleeps = []

    def fn():
        raise UpstreamError("gemini", "unavailable", "503", 503)

    with pytest.raises(UpstreamError):
        call_with_retries(fn, translate=to_upstream, attempts=3, sleep=sleeps.append)
    assert len(sleeps) == 2


def test_auth_and_bad_request_are_not_retried():
    calls = []

    def fn():
        calls.append(1)
        raise UpstreamError("gemini", "auth", "bad key", 403)

    with pytest.raises(UpstreamError) as exc:
        call_with_retries(fn, translate=to_upstream, sleep=lambda s: None)
    assert len(calls) == 1 and exc.value.kind == "auth"


def test_server_retry_hint_is_used():
    err = genai_errors.ClientError(
        429,
        {
            "error": {
                "code": 429,
                "message": "quota",
                "status": "RESOURCE_EXHAUSTED",
                "details": [{"retryDelay": "7s"}],
            }
        },
    )
    up = to_upstream(err)
    assert up.kind == "rate_limited" and up.retry_after_s == 7.0


def test_timeouts_and_transport_errors_map_to_retryable():
    assert to_upstream(httpx.ReadTimeout("t")).kind == "timeout"
    assert to_upstream(httpx.ConnectError("c")).kind == "unavailable"


def test_rate_limiter_waits_for_token_budget():
    now = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        now[0] += s

    rl = RateLimiter(max_rpm=None, max_tpm=1000, clock=lambda: now[0], sleep=sleep)
    rl.acquire(600)
    rl.acquire(300)
    assert sleeps == []
    rl.acquire(300)  # 1200 > 1000 within the window -> must wait ~60 s
    assert len(sleeps) == 1 and 59 < sleeps[0] < 61


def test_rate_limiter_rejects_impossible_request():
    with pytest.raises(ValueError):
        RateLimiter(max_rpm=None, max_tpm=100).acquire(101)


def test_invalid_key_400_is_classified_as_auth():
    err = genai_errors.ClientError(
        400,
        {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
                "details": [{"reason": "API_KEY_INVALID"}],
            }
        },
    )
    up = to_upstream(err)
    assert up.kind == "auth" and not up.retryable
