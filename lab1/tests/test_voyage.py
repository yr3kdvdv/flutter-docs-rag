"""Voyage embeddings + reranker — OFFLINE, MOCKED transport (httpx.MockTransport).

Nothing here calls the real Voyage API; these tests check our request building, batching,
retries, error translation and response validation. The real smoke test is separate:
lab1/scripts/smoke_voyage.py (evidence: docs/evidence/stage05/voyage-smoke.txt).
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from flutter_rag.config import Settings
from flutter_rag.embeddings import CachedEmbedder, EmbeddingCache, make_embedder
from flutter_rag.embeddings.voyage import VoyageEmbedder
from flutter_rag.embeddings.voyage_http import _retry_after
from flutter_rag.errors import MissingSecretError, UpstreamError
from flutter_rag.preprocessing.chunking import Chunk
from flutter_rag.ratelimit import RateLimiter
from flutter_rag.reranking import make_reranker
from flutter_rag.reranking.voyage import VoyageReranker
from flutter_rag.retrieval import Candidate
from flutter_rag.runconfig import EmbeddingConfig, RerankingConfig

KEY = "pa-TESTKEY-0123456789abcdefSECRET"
DIMS = 8


def emb_cfg(**kw) -> EmbeddingConfig:
    base = dict(provider="voyage", model="voyage-4-lite", dimensions=DIMS, batch_size=50)
    base.update(kw)
    return EmbeddingConfig(**base)


class FakeVoyage:
    """Scripted Voyage server: `script` is a list of responses or callables, then default OK."""

    def __init__(self, script=None, dims: int = DIMS):
        self.script = list(script or [])
        self.dims = dims
        self.requests: list[dict] = []
        self.auth: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, **body})
        self.auth.append(request.headers.get("authorization", ""))
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            if isinstance(step, httpx.Response):
                return step
        if request.url.path.endswith("/embeddings"):
            data = [
                {"object": "embedding", "index": i, "embedding": [float(i)] * self.dims}
                for i in range(len(body["input"]))
            ]
            return httpx.Response(200, json={"data": data, "usage": {"total_tokens": 7}})
        # rerank: score = number of query words found in the document
        q = set(body["query"].lower().split())
        scored = [
            {"index": i, "relevance_score": len(q & set(d.lower().split())) / 10}
            for i, d in enumerate(body["documents"])
        ]
        scored.sort(key=lambda d: -d["relevance_score"])
        return httpx.Response(200, json={"data": scored, "usage": {"total_tokens": 11}})


def embedder(server: FakeVoyage, sleeps: list | None = None, **cfg) -> VoyageEmbedder:
    return VoyageEmbedder(
        KEY,
        emb_cfg(**cfg),
        limiter=RateLimiter(None, None),
        transport=httpx.MockTransport(server),
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def err(status: int, detail: str = "error", headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json={"detail": detail}, headers=headers or {})


# --- embeddings -------------------------------------------------------------------------


@pytest.mark.parametrize("task", ["document", "query"])
def test_task_maps_to_input_type_and_dimension(task):
    server = FakeVoyage()
    vecs = embedder(server).embed(["a", "b"], task)
    [req] = server.requests
    assert req["path"] == "/v1/embeddings"
    assert req["input_type"] == task and req["output_dimension"] == DIMS
    assert req["model"] == "voyage-4-lite" and req["input"] == ["a", "b"]
    assert server.auth == [f"Bearer {KEY}"]
    assert len(vecs) == 2 and all(len(v) == DIMS for v in vecs)


def test_response_order_follows_index_field():
    data = [{"index": 1, "embedding": [1.0] * DIMS}, {"index": 0, "embedding": [0.0] * DIMS}]
    server = FakeVoyage([httpx.Response(200, json={"data": data, "usage": {}})])
    assert [v[0] for v in embedder(server).embed(["x", "y"], "document")] == [0.0, 1.0]


def test_wrong_vector_length_is_a_clear_error():
    server = FakeVoyage(dims=DIMS + 1)
    with pytest.raises(ValueError, match=r"length \[9\].*expects 8"):
        embedder(server).embed(["a"], "document")


def test_wrong_vector_count_is_a_clear_error():
    data = [{"index": 0, "embedding": [0.0] * DIMS}]
    server = FakeVoyage([httpx.Response(200, json={"data": data})])
    with pytest.raises(ValueError, match="1 vectors for 2 texts"):
        embedder(server).embed(["a", "b"], "document")


def test_batches_split_by_count():
    server = FakeVoyage()
    e = embedder(server, batch_size=3)
    vecs = e.embed([f"t{i}" for i in range(7)], "document")
    assert [len(r["input"]) for r in server.requests] == [3, 3, 1]
    assert len(vecs) == 7 and e.stats.api_calls == 3 and e.stats.texts_sent == 7
    assert e.stats.api_tokens == 21


def test_batches_split_by_token_budget():
    server = FakeVoyage()
    e = embedder(server, max_tpm=400)  # cap = 200 estimated tokens per request
    text = "x" * 400  # 100 estimated tokens
    e.embed([text] * 5, "document")
    assert [len(r["input"]) for r in server.requests] == [2, 2, 1]


def test_batch_size_is_capped_by_provider_limit():
    e = embedder(FakeVoyage(), batch_size=5000)
    assert e.batch_size == e.max_batch == 1000


@pytest.mark.parametrize("status", [429, 503])
def test_retryable_errors_are_retried_then_succeed(status):
    sleeps: list[float] = []
    server = FakeVoyage([err(status), err(status)])
    e = embedder(server, sleeps)
    assert len(e.embed(["a"], "query")) == 1
    assert len(server.requests) == 3 and len(sleeps) == 2 and e.stats.retries == 2


def test_retry_after_header_is_honoured():
    sleeps: list[float] = []
    server = FakeVoyage([err(429, f"slow down {KEY}", {"Retry-After": "7"})])
    e = embedder(server, sleeps)
    e.embed(["a"], "query")
    assert 7.0 <= sleeps[0] <= 7.5
    [event] = e.retry_events
    assert (event["kind"], event["status_code"], event["retry_after_s"]) == (
        "rate_limited",
        429,
        7.0,
    )
    assert KEY not in json.dumps(e.retry_events)


def test_retry_after_parsing():
    assert _retry_after("3") == 3.0
    assert _retry_after("9999") == 60.0
    assert _retry_after("garbage") is None and _retry_after(None) is None
    assert _retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0  # date in the past


def test_auth_error_is_not_retried_and_key_not_leaked():
    server = FakeVoyage([err(401, f"Provided API key is invalid: {KEY}")])
    e = embedder(server)
    with pytest.raises(UpstreamError) as exc:
        e.embed(["a"], "document")
    u = exc.value
    assert (u.provider, u.kind, u.status_code, u.retryable) == ("voyage", "auth", 401, False)
    assert len(server.requests) == 1
    for text in (str(u), repr(u), json.dumps(u.to_dict()), repr(e), repr(e._http)):
        assert KEY not in text and "SECRET" not in text


def test_retries_are_bounded():
    server = FakeVoyage([err(503)] * 10)
    with pytest.raises(UpstreamError) as exc:
        embedder(server).embed(["a"], "document")
    assert exc.value.kind == "unavailable" and len(server.requests) == 4


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, "bad_request"),
        (403, "auth"),
        (429, "rate_limited"),
        (500, "unavailable"),
        (504, "timeout"),
    ],
)
def test_status_translation(status, kind):
    server = FakeVoyage([err(status)] * 4)
    with pytest.raises(UpstreamError) as exc:
        embedder(server).embed(["a"], "document")
    assert exc.value.kind == kind and exc.value.status_code == status


def test_transport_timeout_is_translated():
    server = FakeVoyage([httpx.ReadTimeout("slow")] * 4)
    with pytest.raises(UpstreamError) as exc:
        embedder(server).embed(["a"], "document")
    assert exc.value.kind == "timeout" and exc.value.provider == "voyage"


def test_cached_embedder_reads_voyage_stats(tmp_path):
    server = FakeVoyage()
    cached = CachedEmbedder(embedder(server), EmbeddingCache(tmp_path / "c.sqlite"))
    cached.embed(["a", "b"], "document")
    cached.embed(["a", "b"], "document")
    assert len(server.requests) == 1 and cached.stats.cache_hits == 2


def test_limiter_receives_estimated_tokens():
    seen = []

    class SpyLimiter(RateLimiter):
        def acquire(self, tokens: int = 0) -> None:
            seen.append(tokens)

    e = VoyageEmbedder(
        KEY, emb_cfg(), limiter=SpyLimiter(None, None), transport=httpx.MockTransport(FakeVoyage())
    )
    e.embed(["x" * 40, "y" * 40], "document")
    assert seen == [20]


# --- reranker ---------------------------------------------------------------------------


def cand(i: int, text: str) -> Candidate:
    chunk = Chunk(
        chunk_id=f"c{i}", document_id=f"doc{i}", strategy_id="section-512-o0", ordinal=0,
        title="T", url="u", section_path=["S"], anchor=None, text=text,
        embed_text=f"Page: T > S\n\n{text}", has_code=False, code_split=False,
        token_count=10, content_hash=f"h{i}",
    )  # fmt: skip
    return Candidate(chunk=chunk, score=1.0 - i / 100, rank=i + 1)


def reranker(server: FakeVoyage, sleeps: list | None = None, **cfg) -> VoyageReranker:
    return VoyageReranker(
        KEY,
        RerankingConfig(enabled=True, **cfg),
        limiter=RateLimiter(None, None),
        transport=httpx.MockTransport(server),
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


CANDS_TEXT = [
    "hot reload keeps state",
    "row and column layout widgets",
    "flex layout widgets row column expanded",
]


def test_rerank_orders_same_objects_with_scores_and_top_n():
    server = FakeVoyage()
    cands = [cand(i, t) for i, t in enumerate(CANDS_TEXT)]
    out = reranker(server).rerank("flex expanded layout", cands, top_n=2)
    assert [c.chunk.chunk_id for c in out] == ["c2", "c1"]
    assert all(any(o is c for c in cands) for o in out)
    assert out[0].rerank_score > out[1].rerank_score > 0 and cands[0].rerank_score == 0
    [req] = server.requests
    assert req["path"] == "/v1/rerank" and req["model"] == "rerank-2.5"
    assert req["documents"] == [c.chunk.embed_text for c in cands]


def test_rerank_empty_candidates_makes_no_call():
    server = FakeVoyage()
    assert reranker(server).rerank("q", [], top_n=5) == []
    assert server.requests == []


def test_rerank_top_n_larger_than_candidates():
    cands = [cand(i, t) for i, t in enumerate(CANDS_TEXT)]
    out = reranker(FakeVoyage()).rerank("layout", cands, top_n=10)
    assert len(out) == 3 and all(c.rerank_score is not None for c in out)


def test_rerank_splits_by_token_budget_and_merges_scores():
    server = FakeVoyage()
    # each document ~ 100 estimated tokens + query ~ 2 -> cap 250 fits two documents
    cands = [cand(i, ("layout " if i == 3 else "other ") * 57) for i in range(5)]
    r = reranker(server, max_tpm=250)
    out = r.rerank("layout", cands, top_n=2)
    assert [len(q["documents"]) for q in server.requests] == [2, 2, 1]
    assert out[0].chunk.chunk_id == "c3" and r.stats.api_calls == 3


def test_rerank_retries_429_then_succeeds_and_no_retry_on_401():
    sleeps: list[float] = []
    server = FakeVoyage([err(429, headers={"Retry-After": "2"})])
    r = reranker(server, sleeps)
    assert len(r.rerank("layout", [cand(0, "layout")], top_n=1)) == 1
    assert len(server.requests) == 2 and 2.0 <= sleeps[0] <= 2.5 and r.stats.retries == 1

    server = FakeVoyage([err(401, f"bad key {KEY}")])
    with pytest.raises(UpstreamError) as exc:
        reranker(server).rerank("q", [cand(0, "x")], top_n=1)
    assert exc.value.kind == "auth" and len(server.requests) == 1
    assert KEY not in str(exc.value)


def test_rerank_bad_response_is_a_clear_error():
    bad = httpx.Response(200, json={"data": [{"index": 5, "relevance_score": 0.1}]})
    with pytest.raises(ValueError, match="bad index"):
        reranker(FakeVoyage([bad])).rerank("q", [cand(0, "x")], top_n=1)


# --- factories --------------------------------------------------------------------------


def settings(key: str | None) -> Settings:
    return Settings.model_construct(voyage_api_key=SecretStr(key) if key else None)


def test_make_embedder_dispatches_voyage():
    e = make_embedder(emb_cfg(dimensions=1024), settings(KEY))
    assert isinstance(e, VoyageEmbedder) and e.dimensions == 1024
    assert e.model_id == "voyage-4-lite"
    with pytest.raises(MissingSecretError):
        make_embedder(emb_cfg(), settings(None))


def test_make_reranker_dispatch():
    assert make_reranker(RerankingConfig(enabled=False), settings(None)) is None
    r = make_reranker(RerankingConfig(enabled=True, model="rerank-2.5"), settings(KEY))
    assert isinstance(r, VoyageReranker) and r.model_id == "rerank-2.5"
    with pytest.raises(MissingSecretError):
        make_reranker(RerankingConfig(enabled=True), settings(None))
