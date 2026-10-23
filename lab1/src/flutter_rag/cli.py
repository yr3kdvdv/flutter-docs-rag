"""Command-line entry point.

Only `env-check` is implemented at stage 01. Other commands are listed so the
interface is visible, but they exit with code 2 instead of pretending to work.
"""

from __future__ import annotations

import argparse
import sys

from flutter_rag import __version__
from flutter_rag.config import load_settings

PLANNED = {
    "ingest": "grab Flutter docs, clean, chunk, embed and upsert into Qdrant (stage 03)",
    "ask": "answer a question with sources and a Langfuse trace (stage 03)",
    "serve": "run the FastAPI service (stage 03)",
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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flutter-rag")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("env-check", help="show versions and which secrets are set (never values)")
    for name, help_text in PLANNED.items():
        sub.add_parser(name, help=f"[not implemented] {help_text}")
    args = parser.parse_args(argv)

    if args.command == "env-check":
        return cmd_env_check()
    print(f"'{args.command}' is not implemented yet: {PLANNED[args.command]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
