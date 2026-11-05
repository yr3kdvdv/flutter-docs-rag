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

PLANNED = {
    "evaluate": "run an experiment config against the dev/test dataset (stage 05)",
}


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
    require_secrets(settings, command)
    return Runtime(load_run_config(args.config), settings)


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
