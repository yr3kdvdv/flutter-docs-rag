"""Batch query embeddings once for the frozen final configuration."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from flutter_rag.config import load_settings
from flutter_rag.evaluation.dataset import load_split
from flutter_rag.pipeline import Runtime, require_secrets
from flutter_rag.runconfig import load_run_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final", action="store_true", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = load_run_config(args.config)
    data = load_split("test", final=args.final)
    settings = load_settings()
    require_secrets(settings, "evaluate", config)
    runtime = Runtime(config, settings)
    try:
        metadata = runtime.run_metadata()
        if metadata["git_dirty"] or any(
            item.corpus_commit != metadata["corpus_commit"] for item in data.items
        ):
            raise ValueError("Expected the frozen code and pinned final corpus")
        record = {
            **metadata,
            "dataset_sha256": data.sha256,
            "dataset_version": data.version,
            "split": data.split,
            "items": len(data.items),
        }
        with runtime.tracer.trace(
            "experiment.final_query_prefill",
            input=record,
            metadata=record,
            tags=["stage06", "final"],
        ):
            record["trace_id"] = runtime.tracer.current_trace_id()
            runtime.embedder.embed([item.question for item in data.items], "query")
            record["embedding"] = asdict(runtime.embedder.stats)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
