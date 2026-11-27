"""Screen fixed vector thresholds on a complete threshold-free dev retrieval run."""

import argparse
import json
from pathlib import Path

from flutter_rag.evaluation.dataset import load_split
from flutter_rag.runconfig import load_run_config

THRESHOLDS = (None, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85)


def profile(rows, gold, threshold):
    result = {
        "min_score": threshold,
        "hit5": 0,
        "covered5": 0,
        "context_covered": 0,
        "answerable_empty": 0,
        "unanswerable_empty": 0,
        "rounded_boundary_items": [],
    }
    for row in rows:
        ranked = row["ranked"]
        if threshold is not None:
            ranked = [candidate for candidate in ranked if candidate["score"] >= threshold]
            if any(abs(candidate["score"] - threshold) < 0.000051 for candidate in row["ranked"]):
                result["rounded_boundary_items"].append(row["id"])
        sections = gold[row["id"]]
        # Removing a descending vector-score suffix keeps a subset of the original context.
        context_ids = set(row["context_chunk_ids"])
        context = [candidate for candidate in ranked if candidate["chunk_id"] in context_ids]
        if not sections:
            result["unanswerable_empty"] += not context
            continue
        covered5 = sections & {section for c in ranked[:5] for section in c["section_ids"]}
        covered_context = sections & {section for c in context for section in c["section_ids"]}
        result["hit5"] += bool(covered5)
        result["covered5"] += len(covered5)
        result["context_covered"] += len(covered_context)
        result["answerable_empty"] += not context
    return result


def sweep(path):
    meta = json.loads((path / "meta.json").read_text())
    config = load_run_config(path / "config.yaml")
    dataset = load_split("dev")
    if (
        not meta["complete"]
        or meta["identity"]["mode"] != "retrieval"
        or meta["dataset"]["split"] != "dev"
        or meta["dataset"]["sha256"] != dataset.sha256
        or config.reranking.enabled
        or config.filtering.min_score is not None
    ):
        raise ValueError(f"Expected a complete threshold-free, rerank-off dev run: {path}")
    attempts = [json.loads(line) for line in (path / "raw.jsonl").read_text().splitlines()]
    rows = {row["id"]: row for row in attempts if row["error"] is None}
    gold = {item.id: set(item.gold_sections) for item in dataset.items}
    if rows.keys() != gold.keys():
        raise ValueError("Dev rows do not match the dataset")
    results = [profile(rows.values(), gold, value) for value in THRESHOLDS]
    baseline = results[0]
    viable = (
        row
        for row in results[1:]
        if not row["answerable_empty"]
        and all(row[k] >= baseline[k] for k in ("hit5", "covered5", "context_covered"))
    )
    selected = max((baseline, *viable), key=lambda row: row["unanswerable_empty"])
    return {
        "run_id": meta["run_id"],
        "config_fingerprint": meta["identity"]["config_fingerprint"],
        "gold_sections": sum(map(len, gold.values())),
        "screened_candidate": selected["min_score"],
        "requires_exact_run": selected["min_score"] is not None,
        "thresholds": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps([sweep(path) for path in args.run], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
