"""Ingestion and query pipelines (docs/architecture.md §3.1, §3.2)."""

from __future__ import annotations

import re
import time
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from flutter_rag.config import Settings
from flutter_rag.embeddings import CachedEmbedder, EmbeddingCache, EmbeddingProvider
from flutter_rag.errors import IndexNotReadyError, MissingSecretError, RagError, UpstreamError
from flutter_rag.filtering import build_context, filter_candidates, render_context
from flutter_rag.generation import GeminiLLM, LLMResult, Prompt, load_prompt
from flutter_rag.grabber import RawStore, grab, load_latest_manifest
from flutter_rag.grabber.github import GitHubClient
from flutter_rag.observability import Tracer, git_revision
from flutter_rag.preprocessing import PREPROCESS_VERSION
from flutter_rag.preprocessing.chunking import chunk_document
from flutter_rag.preprocessing.clean import clean_markdown
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.retrieval import retrieve
from flutter_rag.runconfig import DOCS_INCLUDES_ROOT, RunConfig
from flutter_rag.vectorstore import VectorStore, open_qdrant

REQUIRED_SECRETS = {
    "ingest": ["GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
    "ask": ["GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
}


def require_secrets(settings: Settings, command: str) -> None:
    """Fail fast before any work if a key needed by the command is missing (audit M4)."""
    status = settings.secret_status()
    missing = [n for n in REQUIRED_SECRETS.get(command, []) if not status.get(n)]
    if missing:
        raise MissingSecretError(missing)


# --------------------------------------------------------------------------- runtime
class Runtime:
    """Long-lived resources shared by CLI commands and the API (one Qdrant client!)."""

    def __init__(
        self,
        cfg: RunConfig,
        settings: Settings,
        *,
        embedder: EmbeddingProvider | None = None,
        llm: Any | None = None,
        tracer: Tracer | None = None,
        github_factory: Any | None = None,
    ):
        self.cfg = cfg
        self.settings = settings
        self.data_dir = settings.data_dir
        self.client = open_qdrant(settings.qdrant_url, settings.qdrant_path)
        self.store = VectorStore(
            self.client,
            cfg.collection_name,
            cfg.embedding.dimensions,
            self.data_dir / "index" / "state",
        )
        self.cache = EmbeddingCache(self.data_dir / "cache" / "embeddings.sqlite")
        if embedder is None:
            from flutter_rag.embeddings.gemini import GeminiEmbedder

            embedder = GeminiEmbedder(settings.gemini_api_key.get_secret_value(), cfg.embedding)
        self.embedder = CachedEmbedder(embedder, self.cache)
        if llm is None:
            llm = GeminiLLM(
                settings.gemini_api_key.get_secret_value(),
                cfg.generation,
                RateLimiter(max_rpm=12, max_tpm=None),  # free tier: 15 RPM (AI Studio)
            )
        self.llm = llm
        self.prompt: Prompt = load_prompt(cfg.generation.prompt_name, cfg.generation.prompt_version)
        self.tracer = tracer or Tracer(settings)
        self.github_factory = github_factory or (
            lambda: GitHubClient(cfg.corpus.repo, _secret(settings.github_token))
        )

    def close(self) -> None:
        self.tracer.flush()
        self.cache.close()
        self.client.close()

    def run_metadata(self) -> dict[str, Any]:
        manifest = load_latest_manifest(self.data_dir, self.cfg.config_id)
        return {
            "config_id": self.cfg.config_id,
            "config_fingerprint": self.cfg.fingerprint(),
            "collection": self.cfg.collection_name,
            "corpus_commit": manifest.commit_sha if manifest else None,
            "embedding_model": f"{self.cfg.embedding.model}@{self.cfg.embedding.dimensions}",
            "llm_model": self.cfg.generation.model,
            "prompt_version": f"{self.prompt.name}/{self.prompt.version}",
            "prompt_sha256": self.prompt.sha256[:16],
            **git_revision(),
        }


# --------------------------------------------------------------------------- ingest
@dataclass
class IngestReport:
    corpus_commit: str
    documents: dict[str, int]
    diff: dict[str, int]
    downloaded_files: int
    github_requests: int
    indexed_documents: list[str]
    removed_documents: list[str]
    chunks_upserted: int
    points_total: int
    embedding: dict[str, Any]
    failed: list[str]
    stale_documents: list[str]  # download failed: the previous indexed version is kept
    missing_renders: dict[str, list[str]]
    duration_s: float
    trace_id: str | None = None
    trace_url: str | None = None


def ingest(rt: Runtime) -> IngestReport:
    t0 = time.monotonic()
    cfg = rt.cfg
    meta = rt.run_metadata()
    # The snapshot is only known after grab; before it latest.json holds the PREVIOUS one,
    # so it must not be reported as this run's corpus_commit (review F5).
    meta["previous_corpus_commit"] = meta.pop("corpus_commit")
    with (
        rt.tracer.trace(
            "rag.ingest", input={"config_id": cfg.config_id}, metadata=meta, tags=["ingest"]
        ) as root,
        ExitStack() as after_grab,
    ):
        with rt.tracer.observe(
            "grab", input={"repo": cfg.corpus.repo, "ref": cfg.corpus.ref}
        ) as obs:
            client = rt.github_factory()
            try:
                res = grab(cfg.corpus, cfg.config_id, rt.data_dir, client)
            finally:
                client.close()
            manifest = res.manifest
            obs.update(
                output={
                    "commit": manifest.commit_sha,
                    "downloaded": res.downloaded,
                    "diff": {k: len(v) for k, v in asdict(res.diff).items()},
                    "failed": res.failed,
                }
            )
        after_grab.enter_context(rt.tracer.annotate(root, {"corpus_commit": manifest.commit_sha}))

        rt.store.ensure()
        state = rt.store.load_state()
        ok_docs = {k: d for k, d in manifest.documents.items() if d.status == "ok"}
        failed_docs = {k for k, d in manifest.documents.items() if d.status == "failed"}
        to_index = [k for k in sorted(ok_docs) if state.get(k) != _index_version(manifest, k)]
        # Remove only pages that left the snapshot or are excluded on purpose (skipped).
        # A failed download keeps the last good version and its state (review F2).
        to_remove = sorted(set(state) - set(ok_docs) - failed_docs)
        stale = sorted(failed_docs & set(state))

        raw = RawStore(rt.data_dir / "raw")

        def resolver(doc_includes: dict[str, str]):
            def resolve(target: str) -> str | None:
                sha = doc_includes.get(DOCS_INCLUDES_ROOT + target)
                return raw.read(sha) if sha and raw.has(sha) else None

            return resolve

        missing_renders: dict[str, list[str]] = {}
        upserted = 0
        with rt.tracer.observe("preprocess_embed_upsert", input={"documents": to_index}) as obs:
            for doc_id in to_index:
                doc = ok_docs[doc_id]
                cleaned = clean_markdown(raw.read(doc.blob_sha), resolver(doc.includes))
                if cleaned.missing_renders:
                    missing_renders[doc_id] = cleaned.missing_renders
                chunks = chunk_document(
                    document_id=doc_id,
                    title=cleaned.title or doc_id,
                    url=doc.url,
                    body=cleaned.body,
                    cfg=cfg.chunking,
                )
                vectors = rt.embedder.embed([c.embed_text for c in chunks], "document")
                rt.store.delete_document(doc_id)  # replaces the old version, no duplicates
                rt.store.upsert(
                    chunks,
                    vectors,
                    {
                        "source_commit": manifest.commit_sha,
                        "path": doc.path,
                        "blob_sha": doc.blob_sha,
                        "updated_at": manifest.created_at,
                    },
                )
                upserted += len(chunks)
                state[doc_id] = _index_version(manifest, doc_id)
                rt.store.save_state(state)  # progress survives an interrupted run
            for doc_id in to_remove:
                rt.store.delete_document(doc_id)
                state.pop(doc_id)
                rt.store.save_state(state)
            stats = asdict(rt.embedder.stats)
            obs.update(
                output={
                    "chunks_upserted": upserted,
                    "removed": to_remove,
                    "stale": stale,
                    "embedding": stats,
                }
            )

        statuses = {
            s: sum(d.status == s for d in manifest.documents.values())
            for s in ("ok", "skipped", "failed")
        }
        report = IngestReport(
            corpus_commit=manifest.commit_sha,
            documents=statuses,
            diff={k: len(v) for k, v in asdict(res.diff).items()},
            downloaded_files=res.downloaded,
            github_requests=res.github_requests,
            indexed_documents=to_index,
            removed_documents=to_remove,
            chunks_upserted=upserted,
            points_total=rt.store.count(),
            embedding=stats,
            failed=res.failed,
            stale_documents=stale,
            missing_renders=missing_renders,
            duration_s=round(time.monotonic() - t0, 2),
        )
        report.trace_id = rt.tracer.current_trace_id()
        root.update(output={k: v for k, v in asdict(report).items() if k != "trace_id"})
    rt.tracer.flush()
    report.trace_url = rt.tracer.trace_url(report.trace_id)
    return report


# --------------------------------------------------------------------------- ask
Status = Literal["answered", "insufficient_context", "upstream_error"]


@dataclass
class Source:
    number: int
    title: str
    section: str
    url: str
    score: float
    chunk_id: str


@dataclass
class Answer:
    status: Status
    question: str
    text: str | None
    sources: list[Source]
    retrieved: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: dict | None = None
    usage: dict | None = None
    latency_ms: dict[str, float] = field(default_factory=dict)
    trace_id: str | None = None
    trace_url: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class _Timer:
    def __init__(self, sink: dict[str, float], name: str):
        self.sink, self.name = sink, name

    def __enter__(self):
        self.t = time.monotonic()

    def __exit__(self, *exc):
        self.sink[self.name] = round((time.monotonic() - self.t) * 1000, 1)


def ask(rt: Runtime, question: str) -> Answer:
    meta = rt.run_metadata()
    lat: dict[str, float] = {}
    answer = Answer(status="upstream_error", question=question, text=None, sources=[], meta=meta)
    not_ready: IndexNotReadyError | None = None
    with rt.tracer.trace(
        "rag.ask", input={"question": question}, metadata=meta, tags=["ask"]
    ) as root:
        answer.trace_id = rt.tracer.current_trace_id()
        try:
            _ask_inner(rt, question, answer, lat)
        except UpstreamError as err:
            answer.status, answer.error = "upstream_error", err.to_dict()
            root.update(level="ERROR", status_message=str(err))
        except IndexNotReadyError as err:  # no index is a system state, not "no answer"
            not_ready = err
            answer.error = {"kind": "index_not_ready", "message": str(err)}
            root.update(level="ERROR", status_message=str(err))
        answer.latency_ms = lat
        root.update(
            output={
                "status": answer.status,
                "answer": answer.text,
                "sources": [asdict(s) for s in answer.sources],
                "warnings": answer.warnings,
                "error": answer.error,
            }
        )
    rt.tracer.flush()
    answer.trace_url = rt.tracer.trace_url(answer.trace_id)
    if not_ready:
        raise not_ready
    return answer


def _ask_inner(rt: Runtime, question: str, answer: Answer, lat: dict[str, float]) -> None:
    cfg, tr = rt.cfg, rt.tracer
    if rt.store.count() == 0:
        raise IndexNotReadyError(
            f"индекс {rt.store.collection} пуст или не создан — сначала `flutter-rag ingest`"
        )
    with (
        tr.observe(
            "retrieve",
            as_type="retriever",
            input={"question": question, "top_k": cfg.retrieval.top_k},
            metadata={"embedding_model": cfg.embedding.model},
        ) as obs,
        _Timer(lat, "retrieve"),
    ):
        candidates = retrieve(question, rt.embedder, rt.store, cfg.retrieval.top_k)
        answer.retrieved = [
            {
                "rank": c.rank,
                "score": round(c.score, 4),
                "document_id": c.chunk.document_id,
                "section": c.chunk.section,
                "chunk_id": c.chunk.chunk_id,
            }
            for c in candidates
        ]
        obs.update(output=answer.retrieved)

    with tr.observe(
        "filter", input={"candidates": len(candidates), "config": cfg.filtering.model_dump()}
    ) as obs:
        report = filter_candidates(candidates, cfg.filtering)
        obs.update(output={"kept": len(report.kept), "dropped": dict(report.dropped)})

    if cfg.reranking.enabled:
        raise RagError("reranking is configured but not implemented yet (stage 05)")

    with tr.observe("build_context", input={"kept": len(report.kept)}) as obs:
        items = build_context(
            report.kept,
            max_chunks=cfg.filtering.max_chunks,
            max_tokens=cfg.generation.max_context_tokens,
        )
        obs.update(
            output=[
                {
                    "n": i.number,
                    "chunk_id": i.candidate.chunk.chunk_id,
                    "source": i.candidate.chunk.source_url,
                }
                for i in items
            ]
        )

    if not items:
        # Below threshold / nothing indexed: refuse WITHOUT calling the LLM.
        answer.status = "insufficient_context"
        answer.text = REFUSAL_TEXT[question_language(question)]
        return

    user_text = rt.prompt.render_user(context=render_context(items), question=question)
    with (
        tr.observe(
            "llm",
            as_type="generation",
            model=cfg.generation.model,
            input=user_text,
            model_parameters={
                "temperature": cfg.generation.temperature,
                "max_output_tokens": cfg.generation.max_output_tokens,
            },
            metadata={
                "prompt": f"{rt.prompt.name}/{rt.prompt.version}",
                "prompt_sha256": rt.prompt.sha256,
            },
        ) as gen,
        _Timer(lat, "llm"),
    ):
        result: LLMResult = rt.llm.generate(rt.prompt, user_text)
        gen.update(
            output=result.raw_text,
            usage_details=result.usage,
            metadata={"model_version": result.model_version},
        )
    answer.usage = result.usage

    with tr.observe("validate", input=result.parsed.model_dump()) as obs:
        _apply_llm_result(answer, result, items, question_language(question))
        obs.update(
            output={
                "status": answer.status,
                "warnings": answer.warnings,
                "sources": [s.number for s in answer.sources],
            }
        )


_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)

# Refusals are structural (status == insufficient_context), so their text is ours, not the
# model's: at temperature 0 Gemini still sometimes refused in English (review F6). The model's
# own wording stays in the LLM observation of the trace.
REFUSAL_TEXT = {
    "ru": "В проиндексированной документации нет информации для ответа на этот вопрос.",
    "en": "The indexed documentation does not contain information to answer this question.",
}


# Quoted names and code literals do not define the language of the question (review G1):
# "How do I publish an app named "Привет"?" is English. Single quotes count only as a pair
# outside words, so English apostrophes ("don't") are left alone.
_QUOTED = re.compile(
    r"```.*?```|`[^`]*`|\"[^\"]*\"|«[^»]*»|“[^”]*”|„[^“”]*[“”]|(?<!\w)'[^']*'(?!\w)",
    re.DOTALL,
)
_LETTER = re.compile(r"[^\W\d_]")


def question_language(question: str) -> str:
    """'ru' if the question outside quotes/code has any Cyrillic letter, else 'en'.

    Not a majority vote: Russian questions about Flutter are often mostly Latin names
    ("Как настроить Firebase Cloud Messaging ... во Flutter?"). If nothing but quotes is
    left (the whole question is quoted), the full text decides. Known limit: an unquoted
    Russian name inside an English question still gives 'ru'.
    """
    outside = _QUOTED.sub(" ", question)
    text = outside if _LETTER.search(outside) else question
    return "ru" if _CYRILLIC.search(text) else "en"


def _apply_llm_result(answer: Answer, result: LLMResult, items, language: str = "en") -> None:
    parsed = result.parsed
    by_number = {i.number: i for i in items}
    valid = [n for n in dict.fromkeys(parsed.citations) if n in by_number]
    invalid = [n for n in parsed.citations if n not in by_number]
    if invalid:
        answer.warnings.append(f"unsupported_citation: {invalid}")
    answer.text = parsed.answer
    if parsed.status == "insufficient_context":
        answer.status = "insufficient_context"
        answer.text = REFUSAL_TEXT[language]
        return
    if language == "ru" and not _CYRILLIC.search(parsed.answer):
        answer.warnings.append("answer_language_mismatch: expected ru")
    if not valid:
        answer.warnings.append("answered_without_citations")
    answer.status = "answered"
    for n in valid:
        c = by_number[n].candidate
        answer.sources.append(
            Source(
                n,
                c.chunk.title,
                c.chunk.section,
                c.chunk.source_url,
                round(c.score, 4),
                c.chunk.chunk_id,
            )
        )


def _index_version(manifest, document_id: str) -> str:
    return f"{manifest.version_key(document_id)}|pp={PREPROCESS_VERSION}"


def _secret(value) -> str | None:
    return value.get_secret_value() if value else None
