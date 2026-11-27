"""Ingestion and query pipelines (docs/architecture.md §3.1, §3.2)."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal
from uuid import uuid4

from flutter_rag.config import Settings
from flutter_rag.embeddings import CachedEmbedder, EmbeddingCache, EmbeddingProvider, make_embedder
from flutter_rag.errors import IndexNotReadyError, MissingSecretError, UpstreamError
from flutter_rag.filtering import ContextItem, build_context, filter_candidates, render_context
from flutter_rag.generation import GeminiLLM, LLMResult, Prompt, load_prompt
from flutter_rag.grabber import RawStore, grab, manifest_dir
from flutter_rag.grabber.github import GitHubClient
from flutter_rag.grabber.manifest import Manifest
from flutter_rag.observability import Tracer, git_revision
from flutter_rag.preprocessing import PREPROCESS_VERSION
from flutter_rag.preprocessing.chunking import Chunk, chunk_document
from flutter_rag.preprocessing.clean import clean_markdown, split_fences
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.reranking import make_reranker
from flutter_rag.retrieval import Candidate, retrieve
from flutter_rag.runconfig import DOCS_INCLUDES_ROOT, RunConfig
from flutter_rag.vectorstore import PAYLOAD_SOURCE, VectorStore, open_qdrant

REQUIRED_SECRETS = {
    "ingest": ["GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
    "ask": ["GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
    "evaluate": ["GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
}


def required_secrets(command: str, cfg: RunConfig | None = None) -> list[str]:
    names = list(REQUIRED_SECRETS.get(command, []))
    if cfg is not None and (cfg.embedding.provider == "voyage" or cfg.reranking.enabled):
        names.append("VOYAGE_API_KEY")
    return names


def require_secrets(settings: Settings, command: str, cfg: RunConfig | None = None) -> None:
    """Fail fast before any work if a key needed by the command is missing (audit M4)."""
    status = settings.secret_status()
    missing = [n for n in required_secrets(command, cfg) if not status.get(n)]
    if missing:
        raise MissingSecretError(missing)


# --------------------------------------------------------------------------- runtime
@dataclass(frozen=True)
class IndexSnapshot:
    commit: str
    repo: str
    points: int
    generation: str


class Runtime:
    """Long-lived resources shared by CLI commands and the API (one Qdrant client!)."""

    def __init__(
        self,
        cfg: RunConfig,
        settings: Settings,
        *,
        embedder: EmbeddingProvider | None = None,
        reranker: Any | None = None,
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
            embedder = make_embedder(cfg.embedding, settings)
        self.embedder = CachedEmbedder(embedder, self.cache)
        if reranker is None and cfg.reranking.enabled:
            reranker = make_reranker(cfg.reranking, settings)
        self.reranker = reranker
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

    def index_snapshot(self) -> IndexSnapshot | None:
        points = self.store.count()
        if not points:
            return None
        record = self.store.read_snapshot()
        if record is not None:
            # The pending record deliberately has no point count. Never fall back to
            # legacy provenance if a write is in progress or was interrupted.
            return IndexSnapshot(**record) if record.get("points") == points else None

        # Pre-stage-08 indexes have no completion marker. Read their actual point
        # payloads and validate the collection against the manifest for that SHA.
        return self._legacy_snapshot(points)

    def _legacy_snapshot(self, points: int) -> IndexSnapshot | None:
        stored = dict(self.store.source_points())
        commits = {p.get("source_commit") for p in stored.values()}
        if len(commits) != 1 or len(stored) != points:
            return None
        commit = next(iter(commits))
        if not isinstance(commit, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", commit):
            return None
        path = manifest_dir(self.data_dir, self.cfg.corpus.name) / f"{commit}.json"
        if not path.is_file():
            return None
        manifest = Manifest.from_json(path.read_text())
        if manifest.commit_sha != commit or manifest.repo != self.cfg.corpus.repo:
            return None
        if any(doc.status == "failed" for doc in manifest.documents.values()):
            return None
        expected = {doc_id: doc for doc_id, doc in manifest.documents.items() if doc.status == "ok"}
        for point in stored.values():
            doc = expected.get(point.get("document_id"))
            if not doc or point.get("blob_sha") != doc.blob_sha:
                return None
            if point.get("source") != PAYLOAD_SOURCE:
                return None
        raw = RawStore(self.data_dir / "raw")
        if all(
            raw.has(sha)
            for doc in expected.values()
            for sha in (doc.blob_sha, *doc.includes.values())
        ):
            expected_points = {
                chunk.chunk_id: (doc_id, chunk.content_hash)
                for doc_id in expected
                for chunk in _document_chunks(self, manifest, raw, doc_id)[0]
            }
            actual_points = {
                key: (point["document_id"], point.get("content_hash"))
                for key, point in stored.items()
            }
            if expected_points != actual_points:
                return None
        elif self.store.load_state() != {key: _index_version(manifest, key) for key in expected}:
            return None
        elif {point["document_id"] for point in stored.values()} != set(expected):
            return None
        if self.store.read_snapshot() is not None:
            # Another writer began while the legacy collection was being read.
            return None
        return IndexSnapshot(commit, manifest.repo, points, "legacy")

    def check_index(
        self, snapshot: IndexSnapshot | None, expected_commit: str | None = None
    ) -> IndexSnapshot:
        if snapshot is None:
            raise IndexNotReadyError(
                f"индекс {self.store.collection} пуст или снимок не подтверждён — "
                "сначала `flutter-rag ingest`"
            )
        ref = self.cfg.corpus.ref
        pinned_commit = ref.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", ref) else None
        different_commit = next(
            (sha for sha in (pinned_commit, expected_commit) if sha and snapshot.commit != sha),
            None,
        )
        if snapshot.repo != self.cfg.corpus.repo or different_commit:
            raise IndexNotReadyError(
                f"индекс {self.store.collection} использует снимок "
                f"{snapshot.repo}@{snapshot.commit}; "
                f"ожидался {self.cfg.corpus.repo}@{different_commit or ref} — "
                "сначала `flutter-rag ingest` с нужным конфигом"
            )
        return snapshot

    def run_metadata(self) -> dict[str, Any]:
        snapshot = self.index_snapshot()
        if snapshot is not None:
            self.check_index(snapshot)
        return self._metadata(snapshot)

    def _metadata(self, snapshot: IndexSnapshot | None) -> dict[str, Any]:
        return {
            "config_id": self.cfg.config_id,
            "config_fingerprint": self.cfg.fingerprint(),
            "collection": self.cfg.collection_name,
            "corpus_commit": snapshot.commit if snapshot else None,
            "embedding_model": f"{self.cfg.embedding.model}@{self.cfg.embedding.dimensions}",
            "llm_model": self.cfg.generation.model,
            "thinking_budget": self.cfg.generation.thinking_budget,
            "chunking": self.cfg.chunking.strategy_id,
            "top_k": self.cfg.retrieval.top_k,
            "min_score": self.cfg.filtering.min_score,
            "reranker": self.cfg.reranking.model if self.cfg.reranking.enabled else None,
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
    with rt.store.ingest_lock():
        return _ingest(rt)


def _ingest(rt: Runtime) -> IngestReport:
    t0 = time.monotonic()
    cfg = rt.cfg
    previous = rt.index_snapshot()
    meta = rt._metadata(previous)
    # Grab has yet to resolve the new ref. Use the collection's previous snapshot.
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
                res = grab(cfg.corpus, cfg.corpus.name, rt.data_dir, client)
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

        indexed = defaultdict(dict)
        if rt.store.exists():
            for point_id, point in rt.store.source_points():
                doc_id = point.get("document_id")
                if point.get("source") != PAYLOAD_SOURCE or not isinstance(doc_id, str):
                    raise IndexNotReadyError(f"неизвестный формат точек в {rt.store.collection}")
                indexed[doc_id][point_id] = (point.get("blob_sha"), point.get("content_hash"))
        # A recreated or empty collection must not reuse progress from its old sidecar.
        state = rt.store.load_state() if indexed else {}
        rt.store.ensure()
        raw = RawStore(rt.data_dir / "raw")
        ok_docs = {k: d for k, d in manifest.documents.items() if d.status == "ok"}
        failed_docs = {k for k, d in manifest.documents.items() if d.status == "failed"}
        known_snapshot = (
            previous and previous.commit == manifest.commit_sha and previous.repo == manifest.repo
        )
        to_index = []
        for doc_id, doc in sorted(ok_docs.items()):
            version = _index_version(manifest, doc_id)
            stored_points = indexed.get(doc_id, {})
            known_version = state.get(doc_id) == version
            if (
                previous
                and stored_points
                and known_version
                and all(blob_sha == doc.blob_sha for blob_sha, _ in stored_points.values())
            ):
                continue
            if known_version or known_snapshot:
                chunks, _ = _document_chunks(rt, manifest, raw, doc_id)
                if stored_points == {
                    chunk.chunk_id: (doc.blob_sha, chunk.content_hash) for chunk in chunks
                }:
                    state[doc_id] = version
                    continue
            to_index.append(doc_id)
        # Remove only pages that left the snapshot or are excluded on purpose (skipped).
        # A failed download keeps the last good version and its state (review F2).
        to_remove = sorted((set(state) | set(indexed)) - set(ok_docs) - failed_docs)
        stale = sorted(failed_docs & indexed.keys())

        # Retain the previous certified snapshot if a download failure did not
        # change anything in the collection. Any point mutation is marked before it
        # happens so an interrupted reindex cannot masquerade as either snapshot.
        pending = IndexSnapshot(manifest.commit_sha, manifest.repo, -1, uuid4().hex)
        if to_index or to_remove:
            rt.store.write_snapshot(asdict(pending))

        missing_renders: dict[str, list[str]] = {}
        upserted = 0
        with rt.tracer.observe("preprocess_embed_upsert", input={"documents": to_index}) as obs:
            for doc_id in to_index:
                doc = ok_docs[doc_id]
                chunks, missing = _document_chunks(rt, manifest, raw, doc_id)
                if missing:
                    missing_renders[doc_id] = missing
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
                state.pop(doc_id, None)
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

        points = rt.store.count()
        rt.store.save_state(state)
        if not res.failed and (
            to_index
            or to_remove
            or previous is None
            or previous.generation == "legacy"
            or previous.commit != manifest.commit_sha
            or previous.repo != manifest.repo
        ):
            rt.store.write_snapshot(asdict(replace(pending, points=points)))
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
            points_total=points,
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


def _document_chunks(
    rt: Runtime, manifest: Manifest, raw: RawStore, doc_id: str
) -> tuple[list[Chunk], list[str]]:
    doc = manifest.documents[doc_id]

    def resolve(target: str) -> str | None:
        sha = doc.includes.get(DOCS_INCLUDES_ROOT + target)
        return raw.read(sha) if sha and raw.has(sha) else None

    cleaned = clean_markdown(raw.read(doc.blob_sha), resolve)
    chunks = chunk_document(
        document_id=doc_id,
        title=cleaned.title or doc_id,
        url=doc.url,
        body=cleaned.body,
        cfg=rt.cfg.chunking,
    )
    return chunks, cleaned.missing_renders


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
    ranked: list[dict] = field(default_factory=list)  # after filter + rerank
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
    meta = rt._metadata(None)
    lat: dict[str, float] = {}
    answer = Answer(status="upstream_error", question=question, text=None, sources=[], meta=meta)
    not_ready: IndexNotReadyError | None = None
    with rt.tracer.trace(
        "rag.ask", input={"question": question}, metadata=meta, tags=["ask"]
    ) as root:
        answer.trace_id = rt.tracer.current_trace_id()
        try:
            snapshot = rt.check_index(rt.index_snapshot())
            answer.meta["corpus_commit"] = snapshot.commit
            with rt.tracer.annotate(root, {"corpus_commit": snapshot.commit}):
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


@dataclass
class SearchResult:
    """Every stage of retrieval, for `ask` and for retrieval-only evaluation (contract §4)."""

    retrieved: list[Candidate]  # vector search order, top_k
    kept: list[Candidate]  # after filtering (threshold, dedupe, length)
    ranked: list[Candidate]  # after the reranker (== kept when reranking is off)
    context: list[ContextItem]  # what the LLM gets, numbered [1..n]
    dropped: dict[str, int]


def _candidate_row(c: Candidate) -> dict:
    return {
        "rank": c.rank,
        "score": round(c.score, 4),
        "rerank_score": None if c.rerank_score is None else round(c.rerank_score, 4),
        "document_id": c.chunk.document_id,
        "section": c.chunk.section,
        "section_ids": c.chunk.section_ids,
        "chunk_id": c.chunk.chunk_id,
    }


def search(
    rt: Runtime,
    question: str,
    lat: dict[str, float] | None = None,
    *,
    expected_commit: str | None = None,
) -> SearchResult:
    """retrieve -> filter -> rerank -> build_context, one observation per stage.

    Raises IndexNotReadyError on an empty index and UpstreamError on provider failures.
    """
    cfg, tr = rt.cfg, rt.tracer
    lat = lat if lat is not None else {}
    snapshot = rt.check_index(rt.index_snapshot(), expected_commit)
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
        if rt.index_snapshot() != snapshot:
            raise IndexNotReadyError("Снимок индекса изменился во время поиска — повторите запрос.")
        obs.update(output=[_candidate_row(c) for c in candidates])

    with tr.observe(
        "filter", input={"candidates": len(candidates), "config": cfg.filtering.model_dump()}
    ) as obs:
        report = filter_candidates(candidates, cfg.filtering)
        obs.update(output={"kept": len(report.kept), "dropped": dict(report.dropped)})

    ranked = report.kept
    if rt.reranker is not None and report.kept:
        with (
            tr.observe(
                "rerank",
                input={"candidates": len(report.kept), "top_n": cfg.reranking.top_n},
                metadata={"model": rt.reranker.model_id},
            ) as obs,
            _Timer(lat, "rerank"),
        ):
            ranked = rt.reranker.rerank(question, report.kept, cfg.reranking.top_n)
            obs.update(output=[_candidate_row(c) for c in ranked])

    with tr.observe("build_context", input={"candidates": len(ranked)}) as obs:
        items = build_context(
            ranked,
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
    return SearchResult(candidates, report.kept, ranked, items, dict(report.dropped))


def _ask_inner(rt: Runtime, question: str, answer: Answer, lat: dict[str, float]) -> str:
    tr = rt.tracer
    found = search(rt, question, lat, expected_commit=answer.meta["corpus_commit"])
    answer.retrieved = [_candidate_row(c) for c in found.retrieved]
    answer.ranked = [_candidate_row(c) for c in found.ranked]
    items = found.context
    language = question_language(question)

    if not items:
        # Below threshold / nothing indexed: refuse WITHOUT calling the LLM.
        answer.status = "insufficient_context"
        answer.text = REFUSAL_TEXT[language]
        return ""

    context = render_context(items)
    user_text = rt.prompt.render_user(context=context, question=question)
    retry_instruction = _GENERATION_RETRY.format(
        language="Russian" if language == "ru" else "English"
    )
    for attempt, instruction in enumerate(("", retry_instruction), start=1):
        result = _generate_answer(rt, user_text, lat, attempt, instruction)
        usage = answer.usage or {}
        for metric, value in result.usage.items():
            usage[metric] = usage.get(metric, 0) + value
        answer.usage = usage
        with tr.observe(
            "validate", input=result.parsed.model_dump(), metadata={"attempt": attempt}
        ) as obs:
            accepted = _apply_llm_result(answer, result, items, language)
            obs.update(
                output={
                    "accepted": accepted,
                    "status": answer.status,
                    "warnings": list(answer.warnings),
                    "sources": [s.number for s in answer.sources],
                }
            )
        if accepted:
            return context

    raise UpstreamError("gemini", "bad_request", "model answer failed validation after one retry")


_GENERATION_RETRY = (
    "Correct the output format. Write the answer prose in {language}. Preserve identifiers and "
    "code. If answering, include at least one citation from the numbered excerpts and use "
    "exactly the same citation numbers in the prose and the citations array. If the excerpts do "
    "not support an answer, return insufficient_context with an empty citations array."
)


def _generate_answer(
    rt: Runtime, user_text: str, lat: dict[str, float], attempt: int, instruction: str
) -> LLMResult:
    cfg, tr = rt.cfg, rt.tracer
    prompt = rt.prompt
    metadata = {
        "prompt": f"{prompt.name}/{prompt.version}",
        "prompt_sha256": prompt.sha256,
        "attempt": attempt,
    }
    if instruction:
        metadata["repair_instruction"] = instruction
        prompt = replace(prompt, system=f"{prompt.system}\n\n{instruction}")
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
            metadata=metadata,
        ) as gen,
        _Timer(lat, "llm" if attempt == 1 else "llm_retry"),
    ):
        result: LLMResult = rt.llm.generate(prompt, user_text)
        gen.update(
            output=result.raw_text,
            usage_details=result.usage,
            metadata={"model_version": result.model_version},
        )
    return result


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
_CITATION = re.compile(r"(?<!\\)\[([0-9]+)\](?!\()")
_INLINE_ANSWER_CODE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.DOTALL)
_CYRILLIC_WORD = re.compile(r"[а-яё]+", re.IGNORECASE)
_LATIN_WORD = re.compile(r"[a-z]+", re.IGNORECASE)


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


def _apply_llm_result(
    answer: Answer, result: LLMResult, items: list[ContextItem], language: str
) -> bool:
    parsed = result.parsed
    if parsed.status == "insufficient_context":
        answer.status = "insufficient_context"
        answer.text = REFUSAL_TEXT[language]
        return True

    prose = "\n".join(
        _INLINE_ANSWER_CODE.sub(" ", segment)
        for is_code, segment in split_fences(parsed.answer)
        if not is_code
    )
    by_number = {i.number: i for i in items}
    by_marker = {str(n): n for n in by_number}
    declared = list(dict.fromkeys(parsed.citations))
    inline = list(dict.fromkeys(_CITATION.findall(prose)))
    valid = [n for n in declared if n in by_number]
    warnings = []
    if invalid := [n for n in declared if n not in by_number]:
        warnings.append(f"unsupported_citation: {invalid}")
    if invalid_inline := [marker for marker in inline if marker not in by_marker]:
        warnings.append(f"unsupported_inline_citation: [{', '.join(invalid_inline)}]")
    if set(valid) != {by_marker[marker] for marker in inline if marker in by_marker}:
        warnings.append("citation_text_mismatch")
    if not valid:
        warnings.append("answered_without_citations")
    outside_quotes = _QUOTED.sub(" ", prose)
    language_text = outside_quotes if _LETTER.search(outside_quotes) else prose
    russian_words = len(_CYRILLIC_WORD.findall(language_text))
    english_words = len(_LATIN_WORD.findall(language_text))
    if (language == "en" and russian_words > english_words) or (
        language == "ru" and english_words > russian_words
    ):
        warnings.append(f"answer_language_mismatch: expected {language}")
    if warnings:
        answer.warnings.extend(warning for warning in warnings if warning not in answer.warnings)
        return False

    answer.status = "answered"
    answer.text = parsed.answer
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
    return True


def _index_version(manifest, document_id: str) -> str:
    return f"{manifest.version_key(document_id)}|pp={PREPROCESS_VERSION}"


def _secret(value) -> str | None:
    return value.get_secret_value() if value else None
