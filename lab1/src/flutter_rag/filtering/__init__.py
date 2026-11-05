"""Score threshold, deduplication, length filter and the bounded LLM context."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from flutter_rag.retrieval import Candidate
from flutter_rag.runconfig import FilteringConfig


@dataclass
class FilterReport:
    kept: list[Candidate]
    dropped: Counter = field(default_factory=Counter)


def filter_candidates(candidates: list[Candidate], cfg: FilteringConfig) -> FilterReport:
    """Threshold -> dedupe by content hash -> minimum length.

    Dedupe removes only identical texts (audit H2): other chunks of the same section,
    e.g. the continuation of a long code sample, are kept.
    """
    report = FilterReport(kept=[])
    seen: set[str] = set()
    for c in candidates:
        if cfg.min_score is not None and c.score < cfg.min_score:
            report.dropped["below_min_score"] += 1
        elif c.chunk.content_hash in seen:
            report.dropped["duplicate"] += 1
        elif len(c.chunk.text) < cfg.min_chars:
            report.dropped["too_short"] += 1
        else:
            seen.add(c.chunk.content_hash)
            report.kept.append(c)
    return report


@dataclass
class ContextItem:
    number: int  # [n] used in the prompt and citations
    candidate: Candidate


def build_context(
    candidates: list[Candidate], *, max_chunks: int, max_tokens: int
) -> list[ContextItem]:
    """Pick the best candidates within the budget, then order them for reading:
    documents in order of their best rank, chunks of one document by ordinal (audit L2)."""
    picked: list[Candidate] = []
    used = 0
    for c in candidates:  # already in relevance order
        if len(picked) >= max_chunks:
            break
        if used + c.chunk.token_count > max_tokens:
            continue
        picked.append(c)
        used += c.chunk.token_count
    doc_order: dict[str, int] = {}
    for c in picked:
        doc_order.setdefault(c.chunk.document_id, len(doc_order))
    picked.sort(key=lambda c: (doc_order[c.chunk.document_id], c.chunk.ordinal))
    return [ContextItem(i, c) for i, c in enumerate(picked, start=1)]


def render_context(items: list[ContextItem]) -> str:
    blocks = []
    for it in items:
        ch = it.candidate.chunk
        where = f"{ch.title}" + (f" > {ch.section}" if ch.section_path else "")
        blocks.append(f"[{it.number}] {where}\nSource: {ch.source_url}\n\n{ch.text}")
    return "\n\n---\n\n".join(blocks)
