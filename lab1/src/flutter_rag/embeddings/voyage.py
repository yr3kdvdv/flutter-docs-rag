"""Voyage AI embeddings over REST (batched, rate-limited, bounded retries).

Per-request limits (docs.voyageai.com/docs/embeddings, read 2026-11-06): at most 1,000 texts
and at most 1M tokens per request for voyage-4-lite / voyage-3.5-lite, 320K for voyage-4 /
voyage-3.5 / voyage-2, 120K for the large/domain models. Our token counts are an estimate
(chars/4, assumption A-2), so batches additionally stay under half of `max_tpm`.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import httpx

from flutter_rag.embeddings import EmbeddingTask, EmbedStats
from flutter_rag.embeddings.voyage_http import VoyageHTTP, to_upstream
from flutter_rag.preprocessing.chunking import estimate_tokens
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retry import call_with_retries
from flutter_rag.runconfig import EmbeddingConfig

MAX_RETRY_EVENTS = 100  # keep only the latest retries in memory

INPUT_TYPES: dict[EmbeddingTask, str] = {"document": "document", "query": "query"}
MAX_BATCH = 1000
_REQUEST_TOKEN_LIMITS = {
    "voyage-4-lite": 1_000_000,
    "voyage-3.5-lite": 1_000_000,
    "voyage-4": 320_000,
    "voyage-3.5": 320_000,
    "voyage-2": 320_000,
}
DEFAULT_REQUEST_TOKEN_LIMIT = 120_000  # the strictest documented limit


def request_token_limit(model: str) -> int:
    return _REQUEST_TOKEN_LIMITS.get(model, DEFAULT_REQUEST_TOKEN_LIMIT)


class VoyageEmbedder:
    def __init__(
        self,
        api_key: str,
        cfg: EmbeddingConfig,
        limiter: RateLimiter | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model_id = cfg.model
        self.dimensions = cfg.dimensions
        self.max_batch = MAX_BATCH
        self.batch_size = max(1, min(cfg.batch_size, MAX_BATCH))
        self.max_tpm = cfg.max_tpm
        caps = [request_token_limit(cfg.model)]
        if cfg.max_tpm:
            caps.append(cfg.max_tpm // 2)
        self.batch_token_cap = min(caps)
        self._http = VoyageHTTP(api_key, cfg.timeout_s, base_url=base_url, transport=transport)
        self._limiter = limiter or RateLimiter(cfg.max_rpm, cfg.max_tpm)
        self._sleep = sleep
        self.stats = EmbedStats()
        self.last_response_model: str | None = None  # model id echoed by the API
        self.retry_events: list[dict] = []  # one entry per retry (no secrets)

    def __repr__(self) -> str:
        return f"VoyageEmbedder(model_id={self.model_id!r}, dimensions={self.dimensions})"

    @property
    def last_response_headers(self) -> dict[str, str]:
        return dict(self._http.last_headers)

    @property
    def last_latency_s(self) -> float | None:
        return self._http.last_latency_s

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        """Split by count and by the estimated-token cap; a single long text is its own batch."""
        batches: list[list[str]] = []
        cur: list[str] = []
        cur_tok = 0
        for t in texts:
            tok = estimate_tokens(t)
            if cur and (len(cur) >= self.batch_size or cur_tok + tok > self.batch_token_cap):
                batches.append(cur)
                cur, cur_tok = [], 0
            cur.append(t)
            cur_tok += tok
        if cur:
            batches.append(cur)
        return batches

    def embed(self, texts: Sequence[str], task: EmbeddingTask) -> list[list[float]]:
        out: list[list[float]] = []
        input_type = INPUT_TYPES[task]
        for batch in self._batches(texts):
            tokens = sum(estimate_tokens(t) for t in batch)
            before = self._limiter.waited_s
            self._limiter.acquire(tokens)
            self.stats.limiter_wait_s += self._limiter.waited_s - before
            payload = {
                "input": batch,
                "model": self.model_id,
                "input_type": input_type,
                "output_dimension": self.dimensions,
                "output_dtype": "float",
                "truncation": True,  # API default; chunks are far below the 32K context
            }

            def call(payload: dict = payload) -> dict:
                self.stats.api_calls += 1
                return self._http.post("/embeddings", payload)

            def on_retry(err, delay) -> None:
                self.stats.retries += 1
                self.retry_events.append(
                    {
                        "kind": err.kind,
                        "status_code": err.status_code,
                        "retry_after_s": err.retry_after_s,
                        "delay_s": round(delay, 2),
                        "message": str(err)[:200],
                    }
                )
                del self.retry_events[:-MAX_RETRY_EVENTS]

            body = call_with_retries(
                call, translate=to_upstream, on_retry=on_retry, sleep=self._sleep
            )
            vecs = self._vectors(body, len(batch))
            self.last_response_model = body.get("model")
            self.stats.texts_sent += len(batch)
            self.stats.est_tokens_sent += tokens
            self.stats.api_tokens += int((body.get("usage") or {}).get("total_tokens") or 0)
            out.extend(vecs)
        return out

    def _vectors(self, body: dict, expected: int) -> list[list[float]]:
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != expected:
            got = len(data) if isinstance(data, list) else "no"
            raise ValueError(
                f"voyage embeddings response has {got} vectors for {expected} texts "
                f"(model {self.model_id})"
            )
        data = sorted(data, key=lambda d: d.get("index", 0))
        vecs = [list(d.get("embedding") or []) for d in data]
        bad = {len(v) for v in vecs if len(v) != self.dimensions}
        if bad:
            raise ValueError(
                f"voyage returned vectors of length {sorted(bad)} but the config expects "
                f"{self.dimensions} (model {self.model_id}); a collection never mixes dimensions"
            )
        return vecs

    def close(self) -> None:
        self._http.close()
