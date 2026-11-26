"""Validate stage 06 artifacts and summarize them as JSON without rerunning evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from flutter_rag.errors import RagError
from flutter_rag.evaluation.dataset import DEFAULT_DATASET, QAItem, load_split
from flutter_rag.evaluation.metrics import aggregate_retrieval, retrieval_item_metrics
from flutter_rag.evaluation.runner import compute_metrics
from flutter_rag.generation import load_prompt
from flutter_rag.runconfig import load_run_config

Row = dict[str, Any]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def fraction(numerator: int, denominator: int) -> dict:
    return {
        "k": numerator,
        "n": denominator,
        "rate": round(numerator / denominator, 4) if denominator else None,
    }


def section_metrics(
    pairs: Iterable[tuple[QAItem, Row]], field: str, cutoffs: tuple[int, ...]
) -> dict:
    ks = tuple(sorted({*cutoffs, 8}))
    rows = [
        retrieval_item_metrics(row[field], item.gold_sections, item.gold_documents, ks=ks)
        for item, row in pairs
    ]
    aggregate = aggregate_retrieval(rows, ks=ks)["section"]
    return {
        "at": {
            k: {
                "hit": aggregate[f"hit@{k}"],
                "recall_micro": aggregate[f"recall@{k}"]["micro"],
            }
            for k in cutoffs
        },
        "mrr@8": {
            "reciprocal_rank_sum": round(sum(row["section"]["mrr@8"] for row in rows), 6),
            "n": len(rows),
            "mean": aggregate["mrr@8"],
        },
    }


def context_metrics(pairs: list[tuple[QAItem, Row]], max_chunks: int) -> dict:
    per_item = {}
    for item, row in pairs:
        gold = set(item.gold_sections)
        ranked = {candidate["chunk_id"]: candidate for candidate in row["ranked"]}
        ids = row.get("context_chunk_ids")
        require(ids is None or len(ids) <= max_chunks, f"context exceeds budget for {item.id}")
        require(ids is None or set(ids) <= ranked.keys(), f"unknown context chunk for {item.id}")
        top = row["ranked"][:max_chunks]
        ranked_sections = {section for candidate in top for section in candidate["section_ids"]}
        context_sections = (
            {section for chunk in ids for section in ranked[chunk]["section_ids"]}
            if ids is not None
            else None
        )
        per_item[item.id] = {
            "gold": len(gold),
            "ranked": len(gold & ranked_sections),
            "context": len(gold & context_sections) if context_sections is not None else None,
        }

    observed = [counts for counts in per_item.values() if counts["context"] is not None]
    return {
        "ranked_cutoff": max_chunks,
        "answerable_with_context_ids": fraction(len(observed), len(pairs)),
        "ranked_gold_on_same_items": fraction(
            sum(r["ranked"] for r in observed), sum(r["gold"] for r in observed)
        ),
        "context_gold_on_same_items": fraction(
            sum(r["context"] for r in observed), sum(r["gold"] for r in observed)
        ),
        "by_item": per_item,
    }


def distribution(values: Iterable[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "median": None, "p95": None}
    return {
        "n": len(ordered),
        "median": round(statistics.median(ordered), 4),
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def operational_metrics(rows: list[Row]) -> dict:
    usage: dict[str, Counter] = {}
    usage_rows: Counter = Counter()
    latencies: dict[str, list[float]] = {}
    for row in rows:
        providers = {
            **row.get("provider_usage", {}),
            "generation": (row.get("answer") or {}).get("usage"),
            "judge": (row.get("judge") or {}).get("usage"),
        }
        for name, counts in providers.items():
            if counts:
                usage.setdefault(name, Counter()).update(counts)
                usage_rows[name] += 1
        for stage, latency in row["latency_ms"].items():
            latencies.setdefault(stage, []).append(latency)
    return {
        "usage_all_attempts": {
            name: {
                "rows_with_usage": usage_rows[name],
                **{field: round(total, 4) for field, total in counts.items()},
            }
            for name, counts in usage.items()
        },
        "latency_ms_all_attempts": {
            stage: distribution(values) for stage, values in latencies.items()
        },
        "context_tokens_est": distribution(
            row["context_tokens_est"] for row in rows if "context_tokens_est" in row
        ),
    }


def generation_metrics(items: dict[str, QAItem], latest: dict[str, Row], metrics: dict) -> dict:
    answerable = [key for key, item in items.items() if item.answerable]
    unanswerable = [key for key, item in items.items() if not item.answerable]
    success = {key: row for key, row in latest.items() if row["error"] is None}
    judged = {
        key: success[key]["judge"]
        for key in answerable
        if key in success and success[key].get("judge") is not None
    }
    warnings = Counter(
        warning.partition(":")[0]
        for row in success.values()
        for warning in row["answer"]["warnings"]
    )
    answer_statuses = {
        key: row["answer"]["status"] for key, row in latest.items() if row.get("answer")
    }
    return {
        "answerable_answered": fraction(
            sum(answer_statuses.get(key) == "answered" for key in answerable),
            len(answerable),
        ),
        "judge_ge_4_both_on_all_answerable": fraction(
            sum(r["correctness"] >= 4 and r["faithfulness"] >= 4 for r in judged.values()),
            len(answerable),
        ),
        "answerable_judged": fraction(len(judged), len(answerable)),
        "correct_refusals": fraction(
            sum(answer_statuses.get(key) == "insufficient_context" for key in unanswerable),
            len(unanswerable),
        ),
        **{
            field: metrics[field]
            for field in (
                "citation_precision_section",
                "citation_precision_document",
                "answered_without_citations",
                "must_include_terms",
                "expected_code_present",
            )
        },
        "warnings": warnings,
    }


def analyze(path: Path, *, final: bool) -> dict:
    meta_bytes = (path / "meta.json").read_bytes()
    meta = json.loads(meta_bytes)
    identity = meta["identity"]
    split = identity["split"]
    require(split in {"dev", "test"}, "expected dev or test split")
    require(split == "dev" or (final and identity["final"]), "test artifacts require --final")
    require(identity["final"] is (split == "test"), "split and final flag disagree")
    require(identity["dataset_version"] == DEFAULT_DATASET, "unexpected dataset version")
    files = {
        "meta.json": meta_bytes,
        **{name: (path / name).read_bytes() for name in ("metrics.json", "raw.jsonl")},
    }
    dataset = load_split(split, version=identity["dataset_version"], final=final)
    items = {item.id: item for item in dataset.items}
    require(len(items) == len(dataset.items), "duplicate dataset item IDs")
    require(all(item.status == "verified" for item in items.values()), "dataset is not verified")
    require(
        meta["dataset"]["sha256"] == identity["dataset_sha256"] == dataset.sha256
        and meta["dataset"]["split"] == dataset.split
        and meta["dataset"]["version"] == dataset.version
        and meta["dataset"]["items"] == len(items)
        and meta["final"] == identity["final"],
        "dataset identity does not match the local verified split",
    )

    config_path = path / "config.yaml"
    cfg = load_run_config(config_path)
    files["config.yaml"] = config_path.read_bytes()
    pipe = meta["pipeline"]
    run_id = meta["run_id"]
    mode = identity["mode"]
    require(mode in {"retrieval", "full"}, "invalid mode")
    require(meta["langfuse"]["session_id"] == run_id, "Langfuse session does not match run ID")
    require(
        cfg.fingerprint() == pipe["config_fingerprint"] == identity["config_fingerprint"]
        and cfg.collection_name == pipe["collection"]
        and cfg.config_id == pipe["config_id"]
        and cfg.generation.model == pipe["llm_model"]
        and f"{cfg.embedding.model}@{cfg.embedding.dimensions}" == pipe["embedding_model"],
        "config does not match run provenance",
    )
    require(
        cfg.corpus.ref == pipe["corpus_commit"] == identity["corpus_commit"]
        and all(item.corpus_commit == pipe["corpus_commit"] for item in items.values()),
        "corpus snapshot does not match the gold dataset",
    )
    prompt = load_prompt(cfg.generation.prompt_name, cfg.generation.prompt_version)
    require(
        prompt.sha256[:16] == pipe["prompt_sha256"] == identity["prompt_sha256"],
        "generator prompt hash does not match",
    )
    if mode == "full":
        judge = meta["judge"]
        name, version = judge["prompt_version"].split("/", 1)
        require(
            judge["model"] == identity["judge_model"]
            and load_prompt(name, version).sha256[:16]
            == judge["prompt_sha256"]
            == identity["judge_prompt_sha256"],
            "judge prompt hash or model does not match",
        )
    require(
        bool(re.fullmatch(r"[a-f0-9]{40}", pipe["git_sha"]))
        and identity["git_sha"] == pipe["git_sha"]
        and identity["git_dirty"] is pipe["git_dirty"] is False
        and all(
            inv["git_sha"] == pipe["git_sha"] and inv["git_dirty"] is False
            for inv in meta["invocations"]
        ),
        "Git SHA or clean state differs across invocations",
    )

    rows = [json.loads(line) for line in files["raw.jsonl"].splitlines() if line.strip()]
    seen: Counter = Counter()
    failures = []
    for row in rows:
        item = items.get(row["id"])
        require(item is not None, f"unknown dataset item: {row['id']}")
        seen[item.id] += 1
        require(
            row["run_id"] == run_id
            and row["mode"] == mode
            and row["attempt"] == seen[item.id]
            and row["question"] == item.question
            and row["type"] == item.type
            and row["language"] == item.language
            and row["answerable"] == item.answerable,
            f"raw attempt does not match provenance for {item.id}",
        )
        if error := row["error"]:
            failures.append(
                {
                    "id": item.id,
                    "attempt": row["attempt"],
                    "trace_id": row.get("trace_id"),
                    **{
                        field: error.get(field)
                        for field in ("stage", "provider", "kind", "status_code")
                    },
                }
            )
        elif item.answerable:
            require(
                retrieval_item_metrics(row["ranked"], item.gold_sections, item.gold_documents)
                == row["retrieval_metrics"],
                f"stored retrieval metrics disagree with gold labels for {item.id}",
            )

    metrics, latest = compute_metrics(rows, dataset, mode)
    require(metrics == json.loads(files["metrics.json"]), "metrics.json does not match raw rows")
    trace_ids = {key: row.get("trace_id") for key, row in sorted(latest.items())}
    require(
        trace_ids == meta["trace_ids"]
        and [row["trace_id"] for row in rows if row.get("trace_id")] == meta["all_trace_ids"]
        and metrics["errors"] == meta["remaining_errors"]
        and metrics["not_run"] == sorted(meta["not_run"])
        and meta["complete"] == (not metrics["errors"] and not metrics["not_run"]),
        "summary metadata does not match raw rows",
    )
    answerable = [
        (items[key], row)
        for key, row in sorted(latest.items())
        if items[key].answerable and row["error"] is None
    ]

    return {
        "run_id": run_id,
        "mode": mode,
        "dataset": meta["dataset"],
        "pipeline": pipe,
        "judge": meta["judge"],
        "artifact_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "complete": meta["complete"],
        "completed_items": fraction(metrics["completed"], len(items)),
        "attempts": len(rows),
        "failed_attempts": failures,
        "remaining_errors": metrics["errors"],
        "not_run": metrics["not_run"],
        "trace_ids": trace_ids,
        "retrieved_sections": section_metrics(answerable, "retrieved", (3, 5, 10, 20)),
        "ranked_sections": section_metrics(answerable, "ranked", (5, 8)),
        "context_sections": context_metrics(answerable, cfg.filtering.max_chunks),
        "generation": generation_metrics(items, latest, metrics["generation"])
        if mode == "full"
        else None,
        **operational_metrics(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+", help="paths to stage 06 run directories")
    parser.add_argument("--final", action="store_true", help="allow analysis of final artifacts")
    args = parser.parse_args()
    summaries = []
    for path in args.runs:
        try:
            summaries.append(analyze(path, final=args.final))
        except (OSError, ValueError, KeyError, TypeError, RagError) as error:
            parser.exit(2, f"{path}: {error}\n")
    print(json.dumps({"runs": summaries}, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
