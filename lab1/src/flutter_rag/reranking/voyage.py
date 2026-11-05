"""Voyage AI reranker over REST (rate-limited, bounded retries).

Per-request limits (docs.voyageai.com/docs/reranker, read 2026-11-06, rerank-2.5): at most
1,000 documents; query <= 8,000 tokens; query + any single document <= 32,000 tokens; total
tokens = query_tokens x n_documents + sum(document tokens) <= 600K. Billed usage uses the
same formula.

If the estimated total does not fit `max_tpm` (free tier: 10K TPM, ~20 chunks of 512 tokens do
not fit), the candidates are scored in several requests. A cross-encoder scores every
(query, document) pair independently, so scores from different requests are comparable and are
merged before taking top_n.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from flutter_rag.embeddings.voyage_http import VoyageHTTP, to_upstream
from flutter_rag.preprocessing.chunking import estimate_tokens
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retrieval import Candidate
from flutter_rag.retry import call_with_retries
from flutter_rag.runconfig import RerankingConfig

MAX_RETRY_EVENTS = 100  # keep only the latest retries in memory

MAX_DOCUMENTS = 1000
MAX_REQUEST_TOKENS = 600_000


@dataclass
class RerankStats:
    api_calls: int = 0
    documents_sent: int = 0
    est_tokens_sent: int = 0
    api_tokens: int = 0
    retries: int = 0
    limiter_wait_s: float = 0.0


class VoyageReranker:
    def __init__(
        self,
        api_key: str,
        cfg: RerankingConfig,
        limiter: RateLimiter | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.model_id = cfg.model
        caps = [MAX_REQUEST_TOKENS]
        if cfg.max_tpm:
            caps.append(cfg.max_tpm)
        self.request_token_cap = min(caps)
        self._http = VoyageHTTP(api_key, cfg.timeout_s, base_url=base_url, transport=transport)
        self._limiter = limiter or RateLimiter(cfg.max_rpm, cfg.max_tpm)
        self._sleep = sleep
        self.stats = RerankStats()
        self.last_response_model: str | None = None  # model id echoed by the API
        self.retry_events: list[dict] = []  # one entry per retry (no secrets)

    def __repr__(self) -> str:
        return f"VoyageReranker(model_id={self.model_id!r})"

    @property
    def last_response_headers(self) -> dict[str, str]:
        return dict(self._http.last_headers)

    @property
    def last_latency_s(self) -> float | None:
        return self._http.last_latency_s

    def _groups(self, query_tokens: int, docs: list[str]) -> list[list[int]]:
        """Indices of `docs` split so each request's estimated total fits the cap."""
        groups: list[list[int]] = []
        cur: list[int] = []
        cur_tok = 0
        for i, d in enumerate(docs):
            tok = query_tokens + estimate_tokens(d)
            if cur and (len(cur) >= MAX_DOCUMENTS or cur_tok + tok > self.request_token_cap):
                groups.append(cur)
                cur, cur_tok = [], 0
            cur.append(i)
            cur_tok += tok
        if cur:
            groups.append(cur)
        return groups

    def rerank(self, query: str, candidates: list[Candidate], top_n: int) -> list[Candidate]:
        """Return at most top_n of the SAME candidate objects, best first, rerank_score set."""
        if not candidates or top_n <= 0:
            return []
        docs = [c.chunk.embed_text for c in candidates]
        q_tok = estimate_tokens(query)
        scores: dict[int, float] = {}
        for group in self._groups(q_tok, docs):
            group_docs = [docs[i] for i in group]
            tokens = q_tok * len(group_docs) + sum(estimate_tokens(d) for d in group_docs)
            before = self._limiter.waited_s
            self._limiter.acquire(tokens)
            self.stats.limiter_wait_s += self._limiter.waited_s - before
            payload = {
                "query": query,
                "documents": group_docs,
                "model": self.model_id,
                "truncation": True,  # API default
            }

            def call(payload: dict = payload) -> dict:
                self.stats.api_calls += 1
                return self._http.post("/rerank", payload)

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
            self.last_response_model = body.get("model")
            for local, score in self._scores(body, len(group_docs)).items():
                scores[group[local]] = score
            self.stats.documents_sent += len(group_docs)
            self.stats.est_tokens_sent += tokens
            self.stats.api_tokens += int((body.get("usage") or {}).get("total_tokens") or 0)

        for i, c in enumerate(candidates):
            c.rerank_score = scores[i]
        # stable sort: equal scores keep the vector-search order
        order = sorted(range(len(candidates)), key=lambda i: -scores[i])
        return [candidates[i] for i in order[:top_n]]

    def _scores(self, body: dict, expected: int) -> dict[int, float]:
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise ValueError(f"voyage rerank response has no data (model {self.model_id})")
        out: dict[int, float] = {}
        for d in data:
            idx, score = d.get("index"), d.get("relevance_score")
            if not isinstance(idx, int) or not 0 <= idx < expected or idx in out:
                raise ValueError(f"voyage rerank response has a bad index {idx!r}")
            out[idx] = float(score)
        if len(out) != expected:
            raise ValueError(
                f"voyage rerank scored {len(out)} of {expected} documents (model {self.model_id})"
            )
        return out

    def close(self) -> None:
        self._http.close()
