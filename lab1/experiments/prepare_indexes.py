"""Prefill stock Gemini document embeddings across pages, then run the normal ingest."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from flutter_rag.config import load_settings
from flutter_rag.embeddings import EmbedStats, make_embedder
from flutter_rag.evaluation.check import clean_document
from flutter_rag.grabber import RawStore, load_latest_manifest
from flutter_rag.pipeline import Runtime, ingest, require_secrets
from flutter_rag.preprocessing.chunking import chunk_document
from flutter_rag.runconfig import load_run_config


def document_texts(rt, manifest):
    raw = RawStore(rt.data_dir / "raw")
    texts = {}
    for doc_id, entry in sorted(manifest.documents.items()):
        if entry.status == "ok":
            page = clean_document(manifest, raw, doc_id)
            chunks = chunk_document(
                document_id=doc_id,
                title=page.title or doc_id,
                url=entry.url,
                body=page.body,
                cfg=rt.cfg.chunking,
            )
            texts.update(dict.fromkeys(chunk.embed_text for chunk in chunks))
    return list(texts)


def save(output, record):
    path = output / f"{record['config_id']}.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def prepare(rt, output):
    manifest = load_latest_manifest(rt.data_dir, rt.cfg.corpus.name)
    if manifest is None or manifest.commit_sha != rt.cfg.corpus.ref:
        raise ValueError("Prefill requires the existing pinned raw snapshot")
    texts = document_texts(rt, manifest)
    if not texts:
        raise ValueError("Snapshot has no document chunks")
    provider = rt.embedder.provider
    provider.stats = EmbedStats()
    run_meta = rt.run_metadata()
    record = {
        "config_id": rt.cfg.config_id,
        "operation": "prefill",
        "pipeline": run_meta,
        "unique_texts": len(texts),
    }
    with rt.tracer.trace("experiment.prefill", input=record, metadata=run_meta, tags=["stage06"]):
        record["trace_id"] = rt.tracer.current_trace_id()
        try:
            batch_size = min(rt.cfg.embedding.batch_size, provider.max_batch)
            for start in range(0, len(texts), batch_size):
                rt.embedder.embed(texts[start : start + batch_size], "document")
        except Exception as error:
            record["error"] = str(error)
            raise
        finally:
            record["embedding"] = asdict(provider.stats)
            save(output, record)
    rt.tracer.flush()
    provider.stats = EmbedStats()
    report = ingest(rt)
    save(output, {"config_id": rt.cfg.config_id, "operation": "ingest", **asdict(report)})
    print(rt.cfg.config_id, report.points_total, "points", flush=True)
    if report.failed or report.corpus_commit != manifest.commit_sha:
        raise RuntimeError("Index is incomplete or the pinned commit changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("configs", nargs="+")
    args = parser.parse_args()
    configs = [load_run_config(path) for path in args.configs]
    settings = load_settings()
    first = configs[0].embedding
    if first.provider != "gemini" or any(config.embedding != first for config in configs):
        parser.error("Expected shared Gemini embedding settings across the chunking variants")
    args.out.mkdir(parents=True, exist_ok=True)
    require_secrets(settings, "ingest", configs[0])
    provider = make_embedder(first, settings)  # shared limiter across all indexes
    for config in configs:
        rt = Runtime(config, settings, embedder=provider)
        try:
            prepare(rt, args.out)
        finally:
            rt.close()


if __name__ == "__main__":
    main()
