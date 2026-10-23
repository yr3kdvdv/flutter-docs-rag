"""Langfuse tracing helpers.

One trace per ask/ingest; one observation per pipeline stage; LLM calls are
`generation` observations with model, usage and prompt version. A Langfuse failure
never breaks the answer: the trace id is then None and a warning is logged.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from flutter_rag.config import REPO_ROOT, Settings

log = logging.getLogger(__name__)


def git_revision() -> dict[str, Any]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return {"git_sha": sha, "git_dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"git_sha": None, "git_dirty": None}


class _NullObservation:
    trace_id = None
    id = None

    def update(self, **_: Any) -> None:
        pass


class Tracer:
    """Thin wrapper so the pipeline does not depend on the Langfuse API directly."""

    def __init__(self, settings: Settings | None, enabled: bool = True):
        self._lf = None
        self.error: str | None = None
        if enabled and settings and settings.langfuse_public_key and settings.langfuse_secret_key:
            try:
                from langfuse import Langfuse

                self._lf = Langfuse(
                    public_key=settings.langfuse_public_key.get_secret_value(),
                    secret_key=settings.langfuse_secret_key.get_secret_value(),
                    base_url=settings.langfuse_base_url,
                )
            except Exception as exc:  # noqa: BLE001 - tracing must not break the app
                self.error = f"langfuse init failed: {type(exc).__name__}"
                log.warning(self.error)

    @property
    def enabled(self) -> bool:
        return self._lf is not None

    @contextmanager
    def trace(self, name: str, *, input: Any, metadata: dict, tags: list[str]) -> Iterator[Any]:
        if not self._lf:
            yield _NullObservation()
            return
        from langfuse import propagate_attributes

        with propagate_attributes(trace_name=name, tags=tags, metadata=_flat(metadata)):
            with self._lf.start_as_current_observation(
                as_type="span", name=name, input=input, metadata=metadata
            ) as root:
                yield root

    @contextmanager
    def observe(self, name: str, *, as_type: str = "span", **kwargs: Any) -> Iterator[Any]:
        if not self._lf:
            yield _NullObservation()
            return
        with self._lf.start_as_current_observation(as_type=as_type, name=name, **kwargs) as obs:
            yield obs

    def current_trace_id(self) -> str | None:
        return self._lf.get_current_trace_id() if self._lf else None

    def trace_url(self, trace_id: str | None) -> str | None:
        if not (self._lf and trace_id):
            return None
        try:
            return self._lf.get_trace_url(trace_id=trace_id)
        except Exception:  # noqa: BLE001
            return None

    def flush(self) -> None:
        if self._lf:
            try:
                self._lf.flush()
            except Exception as exc:  # noqa: BLE001
                self.error = f"langfuse flush failed: {type(exc).__name__}"
                log.warning(self.error)

    def fetch_observations(self, trace_id: str) -> list[dict]:
        """Read a trace back from the Langfuse API (delivery proof)."""
        if not self._lf:
            raise RuntimeError("Langfuse is not configured")
        resp = self._lf.api.observations.get_many(trace_id=trace_id, fields="core,basic")
        return [
            {"name": o.name, "type": o.type, "parent": o.parent_observation_id} for o in resp.data
        ]


def _flat(metadata: dict) -> dict[str, str]:
    """propagate_attributes accepts string values only."""
    return {k: str(v) for k, v in metadata.items() if v is not None}
