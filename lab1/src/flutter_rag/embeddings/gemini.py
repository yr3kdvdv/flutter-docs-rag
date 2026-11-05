"""Gemini embeddings via google-genai (batched, rate-limited, bounded retries)."""

from __future__ import annotations

from collections.abc import Sequence

from google import genai
from google.genai import types

from flutter_rag.embeddings import EmbeddingTask, EmbedStats
from flutter_rag.gemini_errors import to_upstream
from flutter_rag.preprocessing.chunking import estimate_tokens
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retry import call_with_retries
from flutter_rag.runconfig import EmbeddingConfig

TASK_TYPES: dict[EmbeddingTask, str] = {
    "document": "RETRIEVAL_DOCUMENT",
    "query": "RETRIEVAL_QUERY",
}
MAX_BATCH = 100  # assumed batchEmbedContents limit; we use batch_size 50 well below it


class GeminiEmbedder:
    def __init__(self, api_key: str, cfg: EmbeddingConfig, limiter: RateLimiter | None = None):
        self.model_id = cfg.model
        self.dimensions = cfg.dimensions
        self.batch_size = min(cfg.batch_size, MAX_BATCH)
        self.max_tpm = cfg.max_tpm
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(cfg.timeout_s * 1000)),
        )
        self._limiter = limiter or RateLimiter(cfg.max_rpm, cfg.max_tpm)
        self.stats = EmbedStats()

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        """Split by count and, if a TPM limit is set, keep each batch under half of it."""
        cap = self.max_tpm // 2 if self.max_tpm else None
        batches, cur, cur_tok = [], [], 0
        for t in texts:
            tok = estimate_tokens(t)
            if cur and (len(cur) >= self.batch_size or (cap and cur_tok + tok > cap)):
                batches.append(cur)
                cur, cur_tok = [], 0
            cur.append(t)
            cur_tok += tok
        if cur:
            batches.append(cur)
        return batches

    def embed(self, texts: Sequence[str], task: EmbeddingTask) -> list[list[float]]:
        out: list[list[float]] = []
        config = types.EmbedContentConfig(
            task_type=TASK_TYPES[task], output_dimensionality=self.dimensions
        )
        for batch in self._batches(texts):
            tokens = sum(estimate_tokens(t) for t in batch)
            before = self._limiter.waited_s
            self._limiter.acquire(tokens)
            self.stats.limiter_wait_s += self._limiter.waited_s - before

            def call(batch: list[str] = batch) -> list[list[float]]:
                self.stats.api_calls += 1
                resp = self._client.models.embed_content(
                    model=self.model_id, contents=batch, config=config
                )
                return [list(e.values) for e in resp.embeddings]

            def on_retry(err, delay) -> None:
                self.stats.retries += 1

            vecs = call_with_retries(call, translate=to_upstream, on_retry=on_retry)
            if len(vecs) != len(batch) or any(len(v) != self.dimensions for v in vecs):
                raise ValueError("embedding response has unexpected shape")
            self.stats.texts_sent += len(batch)
            self.stats.est_tokens_sent += tokens
            out.extend(vecs)
        return out
