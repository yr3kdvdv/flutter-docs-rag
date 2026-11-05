"""Translate google-genai / httpx exceptions into UpstreamError."""

from __future__ import annotations

import re

import httpx
from google.genai import errors as genai_errors

from flutter_rag.errors import UpstreamError, kind_from_status

RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s")
MAX_SERVER_HINT_S = 60.0


def to_upstream(exc: Exception, provider: str = "gemini") -> UpstreamError:
    if isinstance(exc, UpstreamError):
        return exc
    if isinstance(exc, genai_errors.APIError):
        kind = kind_from_status(exc.code)
        if "API_KEY_INVALID" in str(exc) or "API key not valid" in str(exc):
            kind = "auth"  # Gemini answers HTTP 400 for a bad key (seen on 2026-10-23)
        err = UpstreamError(provider, kind, _short(exc), exc.code)
        m = RETRY_DELAY_RE.search(str(exc))
        err.retry_after_s = min(float(m.group(1)), MAX_SERVER_HINT_S) if m else None
        return err
    if isinstance(exc, httpx.TimeoutException):
        return UpstreamError(provider, "timeout", "request timed out")
    if isinstance(exc, httpx.TransportError):
        return UpstreamError(provider, "unavailable", type(exc).__name__)
    raise exc


def _short(exc: genai_errors.APIError) -> str:
    msg = getattr(exc, "message", None) or str(exc)
    return msg.splitlines()[0][:200]
