"""Optional reranker over filtered candidates (docs/contracts/stage05.md §3).

A reranker reorders candidates by query relevance, sets `Candidate.rerank_score` and keeps
`top_n`. It never adds candidates, so rerank on/off is compared on the same candidate set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from flutter_rag.config import Settings
    from flutter_rag.retrieval import Candidate
    from flutter_rag.runconfig import RerankingConfig


class Reranker(Protocol):
    model_id: str

    def rerank(self, query: str, candidates: list[Candidate], top_n: int) -> list[Candidate]:
        """Return at most top_n of `candidates`, best first, each with rerank_score set."""
        ...


def make_reranker(cfg: RerankingConfig, settings: Settings) -> Reranker | None:
    if not cfg.enabled:
        return None
    if cfg.provider == "voyage":
        from flutter_rag.embeddings import _secret
        from flutter_rag.reranking.voyage import VoyageReranker

        return VoyageReranker(_secret(settings.voyage_api_key, "VOYAGE_API_KEY"), cfg)
    raise NotImplementedError(f"reranker {cfg.provider!r}: not supported")
