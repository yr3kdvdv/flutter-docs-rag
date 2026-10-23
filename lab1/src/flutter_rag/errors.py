"""Error taxonomy shared by all modules (docs/architecture.md §5).

"The corpus has no answer" is NOT an error: it is Answer.status == "insufficient_context".
Everything here means the system could not do its job.
"""

from __future__ import annotations

from typing import Literal

UpstreamKind = Literal["rate_limited", "unavailable", "timeout", "auth", "bad_request"]

# CLI exit codes
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_STORAGE = 3
EXIT_UPSTREAM = 4


class RagError(Exception):
    """Base class; message is safe to show to the user (no stack trace, no secrets)."""


class MissingSecretError(RagError):
    def __init__(self, names: list[str]):
        self.names = names
        super().__init__(
            f"Не задан(ы) {', '.join(names)}. Заполните .env по docs/SETUP_ACCOUNTS.md "
            "и проверьте командой `uv run flutter-rag env-check`."
        )


class StorageLockedError(RagError):
    def __init__(self, path: str):
        super().__init__(
            f"Локальная база Qdrant ({path}) занята другим процессом "
            "(например, работающим `flutter-rag serve`). Остановите его или задайте QDRANT_URL."
        )


class IndexNotReadyError(RagError):
    pass


class UpstreamError(RagError):
    """An external service (GitHub, Gemini, Voyage, Qdrant server) failed."""

    def __init__(
        self,
        provider: str,
        kind: UpstreamKind,
        message: str,
        status_code: int | None = None,
    ):
        self.provider = provider
        self.kind = kind
        self.status_code = status_code
        self.retryable = kind in ("rate_limited", "unavailable", "timeout")
        self.retry_after_s: float | None = None  # server hint, if any
        super().__init__(
            f"{provider}: {kind}"
            + (f" (HTTP {status_code})" if status_code else "")
            + f": {message}"
        )

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "status_code": self.status_code,
            "retryable": self.retryable,
            "message": str(self),
        }


def kind_from_status(status: int | None) -> UpstreamKind:
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "auth"
    if status is not None and 400 <= status < 500:
        return "bad_request"
    return "unavailable"
