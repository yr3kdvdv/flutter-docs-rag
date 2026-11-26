"""Command-line entry point.

Exit codes: 0 ok (including a correct "insufficient_context" refusal), 2 configuration /
missing keys / not implemented, 3 local Qdrant storage locked, 4 external service failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from flutter_rag import __version__
from flutter_rag.config import load_settings
from flutter_rag.errors import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_STORAGE,
    EXIT_UPSTREAM,
    RagError,
    StorageLockedError,
    UpstreamError,
)

DEFAULT_CONFIG = "configs/slice.yaml"
EVAL_CONFIG = "configs/full.yaml"  # the dataset is labelled on the full-corpus snapshot

PLANNED: dict[str, str] = {}


def cmd_env_check() -> int:
    settings = load_settings()
    print(f"flutter-rag {__version__}")
    print(f"python {sys.version.split()[0]}")
    print(f"langfuse base url: {settings.langfuse_base_url}")
    print(f"qdrant: {settings.qdrant_url or f'embedded at {settings.qdrant_path}'}")
    for name, present in settings.secret_status().items():
        print(f"{name}: {'set' if present else 'MISSING'}")
    return EXIT_OK


def _runtime(args: argparse.Namespace, command: str):
    from flutter_rag.pipeline import Runtime, require_secrets
    from flutter_rag.runconfig import load_run_config

    settings = load_settings()
    cfg = load_run_config(args.config)
    require_secrets(settings, command, cfg)  # Voyage key only for Voyage configs
    return Runtime(cfg, settings)


def _save(path: str | None, data: dict) -> None:
    if path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"saved: {p}")


def cmd_ingest(args: argparse.Namespace) -> int:
    from flutter_rag.pipeline import ingest

    rt = _runtime(args, "ingest")
    try:
        report = ingest(rt)
    finally:
        rt.close()
    data = asdict(report)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    _save(args.save, data)
    return EXIT_OK if not report.failed else EXIT_UPSTREAM


def cmd_ask(args: argparse.Namespace) -> int:
    from flutter_rag.pipeline import ask

    rt = _runtime(args, "ask")
    try:
        answer = ask(rt, args.question)
    finally:
        rt.close()
    data = answer.to_dict()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"status: {answer.status}\n")
        print(answer.text or "")
        if answer.sources:
            print("\nИсточники:")
            for s in answer.sources:
                section = f" — {s.section}" if s.section else ""
                print(f"  [{s.number}] {s.title}{section}\n      {s.url}  (score {s.score})")
        for w in answer.warnings:
            print(f"warning: {w}")
        if answer.error:
            print(f"error: {answer.error['message']}", file=sys.stderr)
        print(f"\ntrace: {answer.trace_id}\n{answer.trace_url or ''}")
    _save(args.save, data)
    return EXIT_UPSTREAM if answer.status == "upstream_error" else EXIT_OK


def cmd_trace_show(args: argparse.Namespace) -> int:
    from flutter_rag.observability import Tracer

    settings = load_settings()
    tracer = Tracer(settings)
    for _ in range(args.wait // 5 + 1):
        obs = tracer.fetch_observations(args.trace_id)
        if obs:
            break
        time.sleep(5)
    print(
        json.dumps(
            {
                "trace_id": args.trace_id,
                "observations": obs,
                "url": tracer.trace_url(args.trace_id),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return EXIT_OK if obs else EXIT_UPSTREAM


def cmd_dataset_check(args: argparse.Namespace) -> int:
    """Validate the dataset against the manifest + raw store of the config's corpus (§5.1)."""
    from flutter_rag.evaluation.check import check_dataset
    from flutter_rag.grabber import RawStore, load_latest_manifest
    from flutter_rag.runconfig import load_run_config

    settings = load_settings()
    cfg = load_run_config(args.config)
    manifest = load_latest_manifest(settings.data_dir, cfg.corpus.name)
    if manifest is None:
        print(
            f"error: no manifest for corpus {cfg.corpus.name!r} in {settings.data_dir}; "
            "run `flutter-rag ingest` first",
            file=sys.stderr,
        )
        return EXIT_CONFIG
    report = check_dataset(manifest, RawStore(settings.data_dir / "raw"), version=args.dataset)
    print(f"dataset: {report.dataset}  corpus: {manifest.commit_sha}")
    for split, sha in report.files.items():
        print(f"{split}.jsonl sha256 {sha}")
    print("type          split  ru  en")
    for split, table in report.counts.items():
        for t, c in table.items():
            print(f"{t:<13} {split:<5} {c['ru']:>3} {c['en']:>3}")
    print(
        f"checked: {report.checked_excerpts} excerpts, {report.checked_sections} gold sections, "
        f"{report.checked_absent_terms} absent terms; statuses {report.statuses}"
    )
    for err in report.errors:
        print(f"FAIL {err}", file=sys.stderr)
    print("OK" if report.ok else f"{len(report.errors)} problem(s)")
    return EXIT_OK if report.ok else EXIT_CONFIG


def cmd_evaluate(args: argparse.Namespace) -> int:
    from flutter_rag.evaluation.dataset import load_split
    from flutter_rag.evaluation.judge import GeminiJudge
    from flutter_rag.evaluation.runner import default_run_id, run_evaluation

    # Split guard before any key check or API call (N03).
    dataset = load_split(args.split, version=args.dataset, final=args.final)
    rt = _runtime(args, "evaluate")
    try:
        judge = None
        if args.mode == "full":
            judge = GeminiJudge(
                rt.settings.gemini_api_key.get_secret_value(),
                args.judge_model,
                args.judge_prompt,
            )
        run_id = args.run_id or default_run_id(rt.cfg.config_id, args.mode, args.split)
        summary = run_evaluation(
            rt,
            dataset,
            mode=args.mode,
            run_id=run_id,
            final=args.final,
            judge=judge,
            config_path=args.config,
            limit=args.limit,
            max_consecutive_errors=args.max_consecutive_errors,
        )
    finally:
        rt.close()
    metrics = json.loads((summary.out_dir / "metrics.json").read_text())
    sec = metrics["retrieval"]["section"]
    doc = metrics["retrieval"]["document"]
    print(f"run: {summary.run_id}\nout: {summary.out_dir}")
    print(
        f"processed {summary.processed}, skipped (already done) {summary.skipped}, "
        f"errors this run {summary.errors}" + (" (stopped early)" if summary.stopped_early else "")
    )
    n = metrics["retrieval"]["n"]
    for k in (1, 5, 20):
        s_hit, d_hit = sec[f"hit@{k}"]["k"], doc[f"hit@{k}"]["k"]
        print(f"section hit@{k} {s_hit}/{n}  document hit@{k} {d_hit}/{n}")
    print(f"section MRR {sec['mrr']}  document MRR {doc['mrr']}")
    gen = metrics.get("generation")
    if gen:
        for key in ("refusal_accuracy_answerable", "refusal_accuracy_unanswerable"):
            print(f"{key} {gen[key]['k']}/{gen[key]['n']}")
        print(f"upstream_error {gen['upstream_error']['k']}/{gen['upstream_error']['n']}")
        print(
            f"judge correctness mean {gen['judge_correctness']['mean']} "
            f"(n={gen['judge_correctness']['n']}), faithfulness mean "
            f"{gen['judge_faithfulness']['mean']}"
        )
    if summary.remaining_errors or metrics["not_run"]:
        print(
            f"incomplete: errors {summary.remaining_errors}, not run {metrics['not_run']}; "
            f"resume with --run-id {summary.run_id}",
            file=sys.stderr,
        )
        return EXIT_UPSTREAM
    return EXIT_OK


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from flutter_rag.api import create_app

    # Embedded Qdrant allows one process per storage folder: never more than 1 worker (B2).
    uvicorn.run(create_app(args.config), host=args.host, port=args.port, workers=1)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flutter-rag")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env-check", help="show versions and which secrets are set (never values)")

    def with_config(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("--config", default=DEFAULT_CONFIG, help=f"default: {DEFAULT_CONFIG}")
        return p

    p = with_config(sub.add_parser("ingest", help="grab docs -> chunks -> embeddings -> Qdrant"))
    p.add_argument("--save", help="write the JSON report to this file")
    p = with_config(sub.add_parser("ask", help="answer a question with sources and a trace"))
    p.add_argument("question")
    p.add_argument("--json", action="store_true")
    p.add_argument("--save", help="write the JSON answer to this file")
    p = sub.add_parser("trace-show", help="read a trace back from the Langfuse API")
    p.add_argument("trace_id")
    p.add_argument("--wait", type=int, default=30, help="seconds to wait for ingestion")
    p = with_config(sub.add_parser("serve", help="run the FastAPI service (1 worker)"))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p = sub.add_parser("evaluate", help="run a config against the dev (or --final test) split")
    p.add_argument("--config", default=EVAL_CONFIG, help=f"default: {EVAL_CONFIG}")
    p.add_argument("--split", choices=["dev", "test"], default="dev")
    p.add_argument("--final", action="store_true", help="required for --split test (N03)")
    p.add_argument("--mode", choices=["retrieval", "full"], default="retrieval")
    p.add_argument("--run-id", help="resume this run (items without errors are skipped)")
    p.add_argument("--dataset", default="flutter-qa-v1")
    p.add_argument("--judge-model", default="gemini-3.1-flash-lite")
    p.add_argument("--judge-prompt", default="v1")
    p.add_argument("--limit", type=int, help="process at most N pending items")
    p.add_argument(
        "--max-consecutive-errors",
        type=int,
        default=3,
        help="stop after N failed items in a row (quota); 0 = never",
    )
    p = sub.add_parser("dataset-check", help="validate the dataset against the corpus snapshot")
    p.add_argument("--config", default=EVAL_CONFIG, help=f"default: {EVAL_CONFIG}")
    p.add_argument("--dataset", default="flutter-qa-v1")
    for name, help_text in PLANNED.items():
        sub.add_parser(name, help=f"[not implemented] {help_text}")
    args = parser.parse_args(argv)

    if args.command in PLANNED:
        print(f"'{args.command}' is not implemented yet: {PLANNED[args.command]}", file=sys.stderr)
        return EXIT_CONFIG
    handlers = {
        "env-check": lambda: cmd_env_check(),
        "ingest": lambda: cmd_ingest(args),
        "ask": lambda: cmd_ask(args),
        "trace-show": lambda: cmd_trace_show(args),
        "serve": lambda: cmd_serve(args),
        "evaluate": lambda: cmd_evaluate(args),
        "dataset-check": lambda: cmd_dataset_check(args),
    }
    try:
        return handlers[args.command]()
    except StorageLockedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_STORAGE
    except UpstreamError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UPSTREAM
    except RagError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
