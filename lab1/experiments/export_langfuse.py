"""Read back trace and score IDs for evaluation runs without exporting their inputs."""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from langfuse import Langfuse

from flutter_rag.config import load_settings


def pages(query, **filters):
    cursor = None
    seen = set()
    while True:
        response = query(limit=100, cursor=cursor, **filters)
        yield from response.data
        cursor = response.meta.cursor
        if not cursor:
            return
        if cursor in seen:
            raise ValueError("Langfuse returned a repeated page cursor")
        seen.add(cursor)


def readback(api, metadata, scores_by_trace):
    session = metadata["langfuse"]["session_id"]
    expected_ids = set(metadata["all_trace_ids"])
    mode = metadata["identity"]["mode"]
    roots = {
        row.trace_id: {"id": row.trace_id, "observation_id": row.id, "name": row.name}
        for row in pages(
            api.observations.get_many,
            session_id=session,
            is_root_observation=True,
            name=f"eval.{mode}",
            fields="core,basic",
        )
        if row.trace_id in expected_ids
    }
    scores = [row for trace_id in roots for row in scores_by_trace[trace_id]]
    return {
        "run_id": metadata["run_id"],
        "session_id": session,
        "pipeline_git_sha": metadata["pipeline"]["git_sha"],
        "dataset_sha256": metadata["dataset"]["sha256"],
        "trace_count": len(roots),
        "missing_trace_ids": sorted(expected_ids - roots.keys()),
        "items_without_trace_id": sorted(
            item for item, trace_id in metadata["trace_ids"].items() if not trace_id
        ),
        "traces": sorted(roots.values(), key=lambda row: row["id"]),
        "scores": sorted(scores, key=lambda row: (row["trace_id"], row["name"], row["id"])),
        "scores_by_name": dict(sorted(Counter(row["name"] for row in scores).items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    settings = load_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        parser.error("Langfuse keys are missing")
    client = Langfuse(
        public_key=settings.langfuse_public_key.get_secret_value(),
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
    )
    metadata = [json.loads((run / "meta.json").read_text()) for run in args.runs]
    scores_by_trace: dict[str, list[dict]] = {
        trace_id: [] for item in metadata for trace_id in item["all_trace_ids"]
    }
    start = min(datetime.fromisoformat(item["created_at"]) for item in metadata)
    for row in pages(client.api.scores.get_many, from_timestamp=start, fields="subject"):
        if row.subject and row.subject.kind == "trace" and row.subject.id in scores_by_trace:
            scores_by_trace[row.subject.id].append(
                {"id": row.id, "trace_id": row.subject.id, "name": row.name, "value": row.value}
            )
    results = [readback(client.api, item, scores_by_trace) for item in metadata]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    if any(row["missing_trace_ids"] or row["items_without_trace_id"] for row in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
