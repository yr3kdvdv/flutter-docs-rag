"""Client-side sliding-window limiter for requests/minute and tokens/minute."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

WINDOW_S = 60.0


class RateLimiter:
    def __init__(
        self,
        max_rpm: int | None,
        max_tpm: int | None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.max_rpm = max_rpm
        self.max_tpm = max_tpm
        self._clock = clock
        self._sleep = sleep
        self._events: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()
        self.waited_s = 0.0

    def acquire(self, tokens: int = 0) -> None:
        if self.max_tpm is not None and tokens > self.max_tpm:
            raise ValueError(f"single request of {tokens} tokens exceeds max_tpm={self.max_tpm}")
        with self._lock:
            while True:
                now = self._clock()
                while self._events and now - self._events[0][0] >= WINDOW_S:
                    self._events.popleft()
                used_tokens = sum(t for _, t in self._events)
                rpm_ok = self.max_rpm is None or len(self._events) < self.max_rpm
                tpm_ok = self.max_tpm is None or used_tokens + tokens <= self.max_tpm
                if rpm_ok and tpm_ok:
                    self._events.append((now, tokens))
                    return
                wait = WINDOW_S - (now - self._events[0][0]) + 0.05
                self.waited_s += wait
                self._sleep(wait)
