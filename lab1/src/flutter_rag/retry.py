"""Bounded retries for external calls: exponential backoff + jitter, honours server hints."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from flutter_rag.errors import UpstreamError


def call_with_retries[T](
    fn: Callable[[], T],
    *,
    translate: Callable[[Exception], UpstreamError],
    attempts: int = 4,
    base_delay_s: float = 2.0,
    max_delay_s: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[UpstreamError, float], None] | None = None,
) -> T:
    """Call fn; retry only retryable UpstreamErrors (429, 5xx, timeouts) up to `attempts` times."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - translated or re-raised below
            err = translate(exc)
            if not err.retryable or attempt == attempts:
                raise err from exc
            delay = err.retry_after_s or min(max_delay_s, base_delay_s * 2 ** (attempt - 1))
            delay += random.uniform(0, 0.5)
            if on_retry:
                on_retry(err, delay)
            sleep(delay)
    raise AssertionError("unreachable")
