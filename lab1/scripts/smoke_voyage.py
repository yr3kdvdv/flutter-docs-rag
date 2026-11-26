"""REAL API SMOKE TEST for Voyage embeddings + reranker (not part of `pytest`).

Makes exactly 3 small real requests (free tier may be 3 RPM / 10K TPM):
  1. embeddings, input_type=document, 3 short texts
  2. embeddings, input_type=query, 1 text
  3. rerank, 3 Flutter-like snippets

Run from lab1/:  uv run python scripts/smoke_voyage.py [--env-file PATH]
The key is read through flutter_rag.config (SecretStr) and is never printed; only its presence.
Exit code 0 = all checks passed, 1 = a check failed, 4 = upstream error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import subprocess
import sys
from pathlib import Path

from flutter_rag.config import LAB1_DIR, Settings, load_settings
from flutter_rag.embeddings import _secret
from flutter_rag.embeddings.voyage import VoyageEmbedder
from flutter_rag.errors import UpstreamError
from flutter_rag.preprocessing.chunking import Chunk
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.reranking.voyage import VoyageReranker
from flutter_rag.retrieval import Candidate
from flutter_rag.runconfig import EmbeddingConfig, RerankingConfig

EMB = EmbeddingConfig(
    provider="voyage", model="voyage-4-lite", dimensions=1024, max_rpm=3, max_tpm=9000
)
RR = RerankingConfig(enabled=True, provider="voyage", model="rerank-2.5", max_rpm=3, max_tpm=9000)

DOCS = [
    "Hot reload injects updated source code into the running Dart VM and keeps app state.",
    "Use a Row widget to lay out children horizontally and a Column widget for vertical layout.",
    "To publish an Android app, build a release app bundle with flutter build appbundle.",
]
QUERY = "How do I arrange widgets horizontally?"
RELEVANT = 1
SNIPPETS = [
    "Expanded makes a child of a Row or Column fill the available space along the main axis.",
    "The pubspec.yaml file lists the package dependencies of a Flutter project.",
    "Wrap a child in Padding to add empty space around it.",
]
RERANK_QUERY = "How can a child take the remaining space in a Row?"
RERANK_EXPECTED = 0
SAFE_HEADERS = (
    "retry-after",
    "ratelimit",
    "x-ratelimit",
    "request-id",
    "voyage-processing-ms",
    "x-api-warning",
)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def header_report(headers: dict[str, str]) -> str:
    shown = {k: v for k, v in headers.items() if any(s in k for s in SAFE_HEADERS)}
    limits = [k for k in headers if "ratelimit" in k or "rate-limit" in k]
    return (
        f"rate-limit headers: {limits or 'none'}; selected: {shown}; all names: {sorted(headers)}"
    )


def candidate(i: int, text: str) -> Candidate:
    chunk = Chunk(
        chunk_id=f"smoke-{i}", document_id=f"smoke/{i}", strategy_id="smoke", ordinal=0,
        title="Smoke", url="https://docs.flutter.dev/", section_path=["Smoke"], anchor=None,
        text=text, embed_text=text, has_code=False, code_split=False, token_count=0,
        content_hash=str(i),
    )  # fmt: skip
    return Candidate(chunk=chunk, score=0.0, rank=i + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", type=Path, help=".env to read if the default one has no key")
    args = ap.parse_args()
    settings = load_settings()
    if settings.voyage_api_key is None and args.env_file:
        settings = Settings(_env_file=args.env_file)
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=LAB1_DIR
    ).stdout.strip()
    print("# REAL Voyage API smoke test (not a mocked unit test)")
    print(f"time_utc: {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}  git: {sha}")
    print(f"VOYAGE_API_KEY present: {settings.voyage_api_key is not None} (value not printed)")
    key = _secret(settings.voyage_api_key, "VOYAGE_API_KEY")
    limiter = RateLimiter(3, 9000)  # one shared client-side budget for all 3 requests
    ok = True
    try:
        emb = VoyageEmbedder(key, EMB, limiter=limiter)
        print(f"\n## embeddings model={emb.model_id} output_dimension={emb.dimensions}")
        print(f"endpoint: {emb._http.base_url}/embeddings")
        dvec = emb.embed(DOCS, "document")
        print(
            f"document: {len(dvec)} vectors, lengths={sorted({len(v) for v in dvec})}, "
            f"response model={emb.last_response_model!r}, HTTP {emb._http.last_status}, "
            f"latency={emb.last_latency_s:.3f}s, "
            f"usage.total_tokens={emb.stats.api_tokens}"
        )
        print(header_report(emb.last_response_headers))
        before = emb.stats.api_tokens
        [qvec] = emb.embed([QUERY], "query")
        print(
            f"query: 1 vector, length={len(qvec)}, response model={emb.last_response_model!r}, "
            f"HTTP {emb._http.last_status}, "
            f"latency={emb.last_latency_s:.3f}s, usage.total_tokens={emb.stats.api_tokens - before}"
        )
        print(header_report(emb.last_response_headers))
        sims = [cosine(qvec, d) for d in dvec]
        best = max(range(len(sims)), key=sims.__getitem__)
        print(f"query: {QUERY!r}")
        for i, (d, s) in enumerate(zip(DOCS, sims, strict=True)):
            print(f"  cos={s:.4f} doc[{i}] {d[:60]!r}")
        dims_ok = all(len(v) == 1024 for v in [*dvec, qvec])
        print(f"CHECK dims == 1024: {'PASS' if dims_ok else 'FAIL'}")
        print(f"CHECK closest doc is doc[{RELEVANT}]: {'PASS' if best == RELEVANT else 'FAIL'}")
        ok &= dims_ok and best == RELEVANT
        print(f"stats: {emb.stats}")
        print(f"retry events: {emb.retry_events}")

        rr = VoyageReranker(key, RR, limiter=limiter)
        print(f"\n## rerank model={rr.model_id}")
        cands = [candidate(i, t) for i, t in enumerate(SNIPPETS)]
        out = rr.rerank(RERANK_QUERY, cands, top_n=3)
        print(
            f"response model={rr.last_response_model!r}, HTTP {rr._http.last_status}, "
            f"latency={rr.last_latency_s:.3f}s, "
            f"usage.total_tokens={rr.stats.api_tokens}"
        )
        print(header_report(rr.last_response_headers))
        print(f"query: {RERANK_QUERY!r}")
        for c in out:
            print(f"  rerank_score={c.rerank_score:.4f} {c.chunk.chunk_id} {c.chunk.text[:60]!r}")
        same = all(any(o is c for c in cands) for o in out)
        top_ok = out[0].chunk.chunk_id == f"smoke-{RERANK_EXPECTED}"
        print(f"CHECK same Candidate objects returned: {'PASS' if same else 'FAIL'}")
        print(f"CHECK best snippet is smoke-{RERANK_EXPECTED}: {'PASS' if top_ok else 'FAIL'}")
        ok &= same and top_ok
        print(f"stats: {rr.stats}")
        print(f"retry events: {rr.retry_events}")
        print(f"client limiter waited: {limiter.waited_s:.2f}s")
    except UpstreamError as exc:
        print(f"UPSTREAM ERROR: {exc} (kind={exc.kind}, retry_after={exc.retry_after_s})")
        return 4
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
