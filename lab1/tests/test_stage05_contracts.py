"""Shared stage 05 contracts (docs/contracts/stage05.md). FAKE providers, no network."""

import pytest
from fakes import CONTENT, FakeEmbedder, FakeGitHub, FakeLLM
from pydantic import ValidationError
from test_pipeline import LAYOUT, RELOAD, make_cfg

from flutter_rag.config import Settings
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import Runtime, ask, ingest, required_secrets, search
from flutter_rag.runconfig import ChunkingConfig, RunConfig


class ReverseReranker:
    """FAKE: reverses the candidate order and scores by position."""

    model_id = "fake-rerank"

    def __init__(self):
        self.calls = 0

    def rerank(self, query, candidates, top_n):
        self.calls += 1
        out = list(reversed(candidates))[:top_n]
        for i, c in enumerate(out):
            c.rerank_score = 1.0 - i / 10
        return out


def runtime(tmp_path, cfg, reranker=None):
    gh = FakeGitHub({CONTENT + "ui/layout.md": LAYOUT, CONTENT + "tools/reload.md": RELOAD})
    settings = Settings(_env_file=None, data_dir=tmp_path, qdrant_path=tmp_path / "q")
    return Runtime(
        cfg,
        settings,
        embedder=FakeEmbedder(),
        reranker=reranker,
        llm=FakeLLM(),
        tracer=Tracer(None, enabled=False),
        github_factory=lambda: gh,
    )


def test_search_without_reranker_keeps_vector_order(tmp_path):
    rt = runtime(tmp_path, make_cfg())
    try:
        ingest(rt)
        r = search(rt, "What does hot reload keep?")
        assert r.ranked == r.kept and all(c.rerank_score is None for c in r.ranked)
        assert r.context and all(c.chunk.section_ids for c in r.retrieved)
    finally:
        rt.close()


def test_reranker_reorders_filtered_candidates_and_is_reported(tmp_path):
    cfg = make_cfg()
    cfg.reranking.enabled, cfg.reranking.top_n = True, 2
    fake = ReverseReranker()
    rt = runtime(tmp_path, cfg, reranker=fake)
    try:
        ingest(rt)
        found = search(rt, "What does hot reload keep?")
        assert [c.chunk.chunk_id for c in found.ranked] == [
            c.chunk.chunk_id for c in reversed(found.kept)
        ][:2]
        a = ask(rt, "What does hot reload keep?")
        assert fake.calls == 2 and len(a.ranked) == 2 and a.ranked[0]["rerank_score"] == 1.0
    finally:
        rt.close()


def test_section_ids_are_document_and_anchor(tmp_path):
    rt = runtime(tmp_path, make_cfg())
    try:
        ingest(rt)
        ids = {
            s for c in search(rt, "constraints sizes parent").retrieved for s in c.chunk.section_ids
        }
        assert "ui/layout#the-rule" in ids or "ui/layout#center" in ids
        assert all("#" in s for s in ids)
    finally:
        rt.close()


def test_voyage_key_required_only_for_voyage_configs():
    base = make_cfg()
    assert "VOYAGE_API_KEY" not in required_secrets("ask", base)
    voyage = base.model_copy(deep=True)
    voyage.embedding.provider = "voyage"
    assert "VOYAGE_API_KEY" in required_secrets("ingest", voyage)
    rerank = base.model_copy(deep=True)
    rerank.reranking.enabled = True
    assert "VOYAGE_API_KEY" in required_secrets("ask", rerank)


def test_overlap_only_for_fixed_strategy():
    assert (
        ChunkingConfig(strategy="fixed", max_tokens=512, overlap=0.15).strategy_id
        == "fixed-512-o15"
    )
    with pytest.raises(ValidationError):
        ChunkingConfig(strategy="section", overlap=0.15)
    with pytest.raises(ValidationError):
        RunConfig.model_validate(
            {"config_id": "x", "generation": {"model": "m"}, "chunking": {"strategy": "words"}}
        )
