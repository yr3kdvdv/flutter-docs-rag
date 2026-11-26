"""Pure evaluation metrics (docs/contracts/stage05.md §5.2). No I/O, no providers.

Retrieval works on the ranked list = `SearchResult.ranked` (after filter + rerank), given as
rows with `document_id` and `section_ids` (the `Answer.ranked` row format). A row matches the
gold at the section level if its `section_ids` intersect `gold_sections`, at the document level
if its `document_id` is in `gold_documents`. Retrieval metrics are only for answerable items.

Definitions for one item, K in {1,3,5,10,20}:
- Hit@K       1 if any of the first K rows matches, else 0;
- Recall@K    share of gold sections (documents) covered by the first K rows;
- Precision@K matching rows among the first K / K (K, not the list length: a short list is
              not rewarded);
- MRR@K       1 / rank of the first matching row if rank <= K, else 0. `mrr` = no cutoff.
Aggregates report absolute numbers (k/n) next to means (review [2.5]).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

KS: tuple[int, ...] = (1, 3, 5, 10, 20)
LEVELS: tuple[str, ...] = ("section", "document")

Row = Mapping[str, Any]


def candidate_rows(candidates: Iterable[Any]) -> list[dict]:
    """SearchResult candidates -> the rows the metrics use (same keys as Answer.ranked)."""
    return [
        {
            "rank": c.rank,
            "score": round(c.score, 4),
            "rerank_score": None if c.rerank_score is None else round(c.rerank_score, 4),
            "document_id": c.chunk.document_id,
            "section_ids": list(c.chunk.section_ids),
            "chunk_id": c.chunk.chunk_id,
        }
        for c in candidates
    ]


def _units(row: Row, level: str) -> set[str]:
    if level == "section":
        return set(row.get("section_ids") or [])
    return {row["document_id"]}


def retrieval_item_metrics(
    ranked: Sequence[Row],
    gold_sections: Sequence[str],
    gold_documents: Sequence[str],
    ks: Sequence[int] = KS,
) -> dict[str, dict[str, float]]:
    """{level: {"hit@5": 1.0, "recall@5": 0.5, "precision@5": 0.2, "mrr@5": 0.5, "mrr": ...}}"""
    out: dict[str, dict[str, float]] = {}
    for level, gold in (("section", set(gold_sections)), ("document", set(gold_documents))):
        if not gold:
            raise ValueError("retrieval metrics need a non-empty gold set (answerable items)")
        matches = [bool(_units(r, level) & gold) for r in ranked]
        first = next((i + 1 for i, m in enumerate(matches) if m), None)
        m: dict[str, float] = {"mrr": 1.0 / first if first else 0.0, "first_rank": first or 0}
        for k in ks:
            top = ranked[:k]
            covered = set().union(*(_units(r, level) & gold for r in top)) if top else set()
            m[f"hit@{k}"] = 1.0 if any(matches[:k]) else 0.0
            m[f"recall@{k}"] = len(covered) / len(gold)
            m[f"covered@{k}"] = len(covered)
            m[f"precision@{k}"] = sum(matches[:k]) / k
            m[f"mrr@{k}"] = 1.0 / first if first and first <= k else 0.0
        m["gold"] = len(gold)
        out[level] = m
    return out


def aggregate_retrieval(
    per_item: Sequence[Mapping[str, Mapping[str, float]]], ks: Sequence[int] = KS
) -> dict[str, Any]:
    """Means over items plus absolute counts: hit as k/n, recall also micro (covered/gold)."""
    n = len(per_item)
    out: dict[str, Any] = {"n": n}
    for level in LEVELS:
        lv: dict[str, Any] = {}
        rows = [m[level] for m in per_item]
        gold_total = int(sum(r["gold"] for r in rows))
        for k in ks:
            hits = int(sum(r[f"hit@{k}"] for r in rows))
            covered = int(sum(r[f"covered@{k}"] for r in rows))
            lv[f"hit@{k}"] = {"k": hits, "n": n, "rate": _rate(hits, n)}
            lv[f"recall@{k}"] = {
                "macro": _mean(r[f"recall@{k}"] for r in rows),
                "micro": {"k": covered, "n": gold_total, "rate": _rate(covered, gold_total)},
            }
            lv[f"precision@{k}"] = _mean(r[f"precision@{k}"] for r in rows)
            lv[f"mrr@{k}"] = _mean(r[f"mrr@{k}"] for r in rows)
        lv["mrr"] = _mean(r["mrr"] for r in rows)
        out[level] = lv
    return out


# --------------------------------------------------------------------------- generation
def refusal_correct(answerable: bool, status: str) -> bool | None:
    """Answerable -> must be answered; unanswerable -> must be refused. None for upstream_error
    (a failed provider call is not a refusal and is counted separately)."""
    if status == "upstream_error":
        return None
    return status == "answered" if answerable else status == "insufficient_context"


def citation_matches(
    cited_chunk_ids: Sequence[str],
    ranked: Sequence[Row],
    gold_sections: Sequence[str],
    gold_documents: Sequence[str],
) -> dict[str, int]:
    """How many cited sources are gold, at section and document level.

    Cited chunks are looked up in the ranked rows (the context is built from them)."""
    by_id = {r["chunk_id"]: r for r in ranked}
    gs, gd = set(gold_sections), set(gold_documents)
    sec = doc = 0
    for cid in cited_chunk_ids:
        row = by_id.get(cid)
        if row is None:
            continue
        sec += bool(_units(row, "section") & gs)
        doc += row["document_id"] in gd
    return {"cited": len(cited_chunk_ids), "gold_section": sec, "gold_document": doc}


def must_include_found(answer_text: str | None, must_include: Sequence[str]) -> list[bool]:
    """Case-insensitive substring presence of every required fact/identifier."""
    text = (answer_text or "").lower()
    return [m.lower() in text for m in must_include]


_WS = re.compile(r"\s+")


def code_present(answer_text: str | None, expected_code: str | None) -> bool | None:
    """Whitespace-insensitive presence of the expected code fragment; None if none expected."""
    if not expected_code:
        return None
    return _WS.sub("", expected_code) in _WS.sub("", answer_text or "")


def aggregate_generation(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """rows: per-item generation results produced by the runner (see runner._generation)."""
    out: dict[str, Any] = {"n": len(rows)}
    errors = [r for r in rows if r["status"] == "upstream_error"]
    ok = [r for r in rows if r["status"] != "upstream_error"]
    out["upstream_error"] = {"k": len(errors), "n": len(rows)}
    for name, answerable in (("answerable", True), ("unanswerable", False)):
        group = [r for r in ok if r["answerable"] is answerable]
        good = sum(bool(r["refusal_correct"]) for r in group)
        out[f"refusal_accuracy_{name}"] = {
            "k": good,
            "n": len(group),
            "rate": _rate(good, len(group)),
        }
    good = sum(bool(r["refusal_correct"]) for r in ok)
    out["refusal_accuracy"] = {"k": good, "n": len(ok), "rate": _rate(good, len(ok))}

    answered = [r for r in ok if r["answerable"] and r["status"] == "answered"]
    cited = sum(r["citations"]["cited"] for r in answered)
    for level in ("section", "document"):
        k = sum(r["citations"][f"gold_{level}"] for r in answered)
        out[f"citation_precision_{level}"] = {"k": k, "n": cited, "rate": _rate(k, cited)}
    no_cite = sum(r["citations"]["cited"] == 0 for r in answered)
    out["answered_without_citations"] = {"k": no_cite, "n": len(answered)}

    with_must = [r for r in ok if r["answerable"] and r["must_include"]]
    terms = sum(len(r["must_include"]) for r in with_must)
    found = sum(sum(r["must_include"]) for r in with_must)
    full = sum(all(r["must_include"]) for r in with_must)
    out["must_include_terms"] = {"k": found, "n": terms, "rate": _rate(found, terms)}
    out["must_include_all"] = {"k": full, "n": len(with_must), "rate": _rate(full, len(with_must))}

    with_code = [r for r in ok if r["answerable"] and r["code_present"] is not None]
    present = sum(bool(r["code_present"]) for r in with_code)
    out["expected_code_present"] = {
        "k": present,
        "n": len(with_code),
        "rate": _rate(present, len(with_code)),
    }

    judged = [r["judge"] for r in ok if r.get("judge")]
    for key in ("correctness", "faithfulness"):
        values = [j[key] for j in judged]
        out[f"judge_{key}"] = {
            "n": len(values),
            "mean": _mean(values),
            "distribution": {str(s): values.count(s) for s in range(1, 6)},
        }
    return out


def _mean(values: Iterable[float]) -> float | None:
    vals = list(values)
    return round(sum(vals) / len(vals), 4) if vals else None


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None
