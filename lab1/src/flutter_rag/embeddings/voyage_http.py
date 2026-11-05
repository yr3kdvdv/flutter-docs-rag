"""Minimal Voyage AI REST transport shared by the embedder and the reranker.

We call the REST API with httpx instead of the `voyageai` SDK (0.5.0 is installed):
- the SDK has its own tenacity retries; ours (flutter_rag.retry) must be the only ones;
- we need the HTTP status, the Retry-After header and the response headers / latency of
  every call (rate-limit observations, Langfuse metadata), which the SDK hides on success;
- httpx.MockTransport makes offline tests exact, without patching SDK internals.

The API key lives only in the Authorization header of the httpx client. It is never part of
an exception message, a log line or a repr (`_mask` also scrubs it from server messages).
"""

from __future__ import annotations

import re
import time
from email.utils import parsedate_to_datetime

import httpx

from flutter_rag.errors import UpstreamError, kind_from_status

PROVIDER = "voyage"
DEFAULT_BASE_URL = "https://api.voyageai.com/v1"
MONGODB_BASE_URL = "https://ai.mongodb.com/v1"  # keys issued by MongoDB Atlas start with "al-"
MAX_SERVER_HINT_S = 60.0
_KEY_LIKE = re.compile(r"\b(?:pa|al)-[A-Za-z0-9_\-]{8,}")


class VoyageHTTPError(Exception):
    """Non-2xx answer from the Voyage API (message already scrubbed of secrets)."""

    def __init__(self, status_code: int, message: str, retry_after_s: float | None = None):
        self.status_code = status_code
        self.retry_after_s = retry_after_s
        super().__init__(f"HTTP {status_code}: {message}")
        self.message = message


class VoyageHTTP:
    def __init__(
        self,
        api_key: str,
        timeout_s: float,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        if not api_key:
            raise ValueError("Voyage API key is empty")
        self._key = api_key
        self.base_url = base_url or (
            MONGODB_BASE_URL if api_key.startswith("al-") else DEFAULT_BASE_URL
        )
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_s,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            transport=transport,
        )
        self.last_headers: dict[str, str] = {}
        self.last_latency_s: float | None = None
        self.last_status: int | None = None

    def __repr__(self) -> str:  # never show the key
        return f"VoyageHTTP(base_url={self.base_url!r})"

    def post(self, path: str, payload: dict) -> dict:
        t0 = time.perf_counter()
        resp = self._client.post(path, json=payload)
        self.last_latency_s = time.perf_counter() - t0
        self.last_status = resp.status_code
        self.last_headers = {k.lower(): v for k, v in resp.headers.items()}
        if resp.status_code >= 400:
            raise VoyageHTTPError(
                resp.status_code,
                self._mask(_error_message(resp)),
                _retry_after(resp.headers.get("retry-after")),
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise VoyageHTTPError(resp.status_code, "response is not JSON") from exc

    def _mask(self, text: str) -> str:
        return _KEY_LIKE.sub("***", text.replace(self._key, "***"))

    def close(self) -> None:
        self._client.close()


def to_upstream(exc: Exception) -> UpstreamError:
    """Translate transport/HTTP failures; anything else (our bugs) is re-raised as is."""
    if isinstance(exc, UpstreamError):
        return exc
    if isinstance(exc, VoyageHTTPError):
        status = exc.status_code
        if status in (408, 504):
            kind = "timeout"
        elif status >= 500 or status < 400:
            kind = "unavailable"
        else:
            kind = kind_from_status(status)
        err = UpstreamError(PROVIDER, kind, exc.message, status)
        err.retry_after_s = exc.retry_after_s
        return err
    if isinstance(exc, httpx.TimeoutException):
        return UpstreamError(PROVIDER, "timeout", "request timed out")
    if isinstance(exc, httpx.TransportError):
        return UpstreamError(PROVIDER, "unavailable", type(exc).__name__)
    raise exc


def _error_message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        msg = body.get("detail") or body.get("message") or body.get("error") or ""
        msg = msg if isinstance(msg, str) else str(msg)
    else:
        msg = resp.text or resp.reason_phrase
    return (msg.splitlines()[0] if msg else resp.reason_phrase)[:200]


def _retry_after(value: str | None) -> float | None:
    """Retry-After is either delta-seconds or an HTTP date (RFC 9110 §10.2.3)."""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError):
            return None
    return min(max(seconds, 0.0), MAX_SERVER_HINT_S)
