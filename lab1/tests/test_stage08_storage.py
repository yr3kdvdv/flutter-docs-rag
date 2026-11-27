"""Collection provenance and Qdrant error regressions using the offline runtime."""

from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

import pytest
from fakes import CONTENT, FakeEmbedder, FakeGitHub, FakeLLM
from fastapi.testclient import TestClient
from httpx import ConnectError
from qdrant_client import models
from qdrant_client.http.exceptions import ResponseHandlingException
from test_evaluation_runner import dataset
from test_pipeline import LAYOUT, RELOAD, make_cfg

from flutter_rag import cli
from flutter_rag.api import create_app
from flutter_rag.config import Settings
from flutter_rag.errors import EXIT_UPSTREAM, IndexNotReadyError, RagError, UpstreamError
from flutter_rag.evaluation.runner import run_evaluation
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import Runtime, ask, ingest
from flutter_rag.vectorstore import SNAPSHOT_KEY

SHA_A = "a" * 40
SHA_B = "b" * 40
FILES = {CONTENT + "ui/layout.md": LAYOUT, CONTENT + "tools/reload.md": RELOAD}
QUESTION = "What do Flutter constraints do?"


def config(ref=SHA_A, max_tokens=512):
    base = make_cfg()
    return base.model_copy(
        update={
            "corpus": base.corpus.model_copy(update={"ref": ref}),
            "chunking": base.chunking.model_copy(update={"max_tokens": max_tokens}),
        }
    )


def with_commit(data, commit):
    return replace(
        data,
        items=[item.model_copy(update={"corpus_commit": commit}) for item in data.items],
    )


def runtime(tmp_path, cfg, gh):
    return Runtime(
        cfg,
        Settings(_env_file=None, data_dir=tmp_path, qdrant_path=tmp_path / "q"),
        embedder=FakeEmbedder(),
        llm=FakeLLM(),
        tracer=Tracer(None, enabled=False),
        github_factory=lambda: gh,
    )


@contextmanager
def opened(tmp_path, cfg, gh):
    rt = runtime(tmp_path, cfg, gh)
    try:
        yield rt
    finally:
        rt.close()


def test_two_collections_do_not_share_provenance(tmp_path):
    first = config()
    second = config(SHA_B, max_tokens=256)
    with opened(tmp_path, first, FakeGitHub(FILES, SHA_A)) as rt:
        ingest(rt)
    with opened(tmp_path, second, FakeGitHub(FILES, SHA_B)) as rt:
        ingest(rt)
        assert rt.run_metadata()["corpus_commit"] == SHA_B
    with opened(tmp_path, first, FakeGitHub(FILES, SHA_A)) as rt:
        assert ask(rt, QUESTION).meta["corpus_commit"] == SHA_A
        result = run_evaluation(
            rt,
            with_commit(dataset(tmp_path), SHA_A),
            mode="retrieval",
            run_id="matching",
            runs_dir=tmp_path,
        )
        assert result.processed == 3
        with pytest.raises(RagError, match="gold labels would not match"):
            run_evaluation(
                rt,
                with_commit(dataset(tmp_path), SHA_B),
                mode="retrieval",
                run_id="wrong",
                runs_dir=tmp_path,
            )
        assert not (tmp_path / "wrong").exists()
    with (
        opened(tmp_path, config(SHA_B), FakeGitHub(FILES, SHA_B)) as rt,
        pytest.raises(IndexNotReadyError, match=SHA_A),
    ):
        ask(rt, QUESTION)


def test_interrupted_ingest_is_not_readable_and_retry_finishes(tmp_path):
    with opened(tmp_path, config(), FakeGitHub(FILES, SHA_A)) as rt:
        ingest(rt)
    changed = {k: v + "\nPublished update to the Flutter documentation." for k, v in FILES.items()}
    with opened(tmp_path, config(SHA_B), FakeGitHub(changed, SHA_B)) as rt:
        upsert = rt.store.upsert

        def fail_second_document(chunks, vectors, payload):
            if payload["path"] == CONTENT + "ui/layout.md":
                raise UpstreamError("qdrant", "unavailable", "injected interruption")
            upsert(chunks, vectors, payload)

        with patch.object(rt.store, "upsert", side_effect=fail_second_document):
            with pytest.raises(UpstreamError, match="injected interruption"):
                ingest(rt)
        assert rt.store.count() > 0
        assert rt.run_metadata()["corpus_commit"] is None
        with pytest.raises(IndexNotReadyError, match="не подтверждён"):
            ask(rt, QUESTION)
    with opened(tmp_path, config(SHA_B), FakeGitHub(changed, SHA_B)) as rt:
        report = ingest(rt)
        assert report.indexed_documents == ["ui/layout"]
        assert ask(rt, QUESTION).meta["corpus_commit"] == SHA_B


def test_complete_legacy_index_is_reused_without_new_embeddings(tmp_path):
    with opened(tmp_path, config(), FakeGitHub(FILES, SHA_A)) as rt:
        ingest(rt)
        rt.client.update_collection(rt.store.collection, metadata={SNAPSHOT_KEY: None})
        rt.store.save_state({})  # simulate a copy of the Qdrant data without its old sidecar
    with opened(tmp_path, config(), FakeGitHub(FILES, SHA_A)) as rt:
        assert ask(rt, QUESTION).meta["corpus_commit"] == SHA_A
        before = rt.embedder.stats.api_calls
        report = ingest(rt)
        assert report.indexed_documents == []
        assert rt.embedder.stats.api_calls == before
        assert rt.store.read_snapshot()["commit"] == SHA_A


@pytest.mark.parametrize("delete_all", [False, True])
def test_missing_points_are_restored_from_cache(tmp_path, delete_all):
    with opened(tmp_path, config(), FakeGitHub(FILES, SHA_A)) as rt:
        original = ingest(rt).points_total
        if delete_all:
            rt.client.delete_collection(rt.store.collection)
            rt.store.ensure()  # the older sidecar is still present
        else:
            points, _ = rt.client.scroll(rt.store.collection)
            point = next(p for p in points if p.payload["document_id"] == "ui/layout")
            rt.client.delete(
                rt.store.collection, points_selector=models.PointIdsList(points=[point.id])
            )
        with pytest.raises(IndexNotReadyError, match="не подтверждён"):
            ask(rt, QUESTION)
        before = rt.embedder.stats.api_calls
        report = ingest(rt)
        assert "ui/layout" in report.indexed_documents
        assert report.points_total == original
        assert rt.embedder.stats.api_calls == before


def test_search_discards_results_if_collection_changes_during_query(tmp_path):
    with opened(tmp_path, config(), FakeGitHub(FILES, SHA_A)) as rt:
        ingest(rt)
        query = rt.client.query_points

        def change_after_query(*args, **kwargs):
            result = query(*args, **kwargs)
            old = rt.store.read_snapshot()
            rt.store.write_snapshot({**old, "generation": "replaced"})
            return result

        with patch.object(rt.client, "query_points", side_effect=change_after_query):
            with pytest.raises(IndexNotReadyError, match="изменился во время поиска"):
                ask(rt, QUESTION)
        assert rt.llm.calls == 0


def qdrant_outage():
    return ResponseHandlingException(ConnectError("injected private URL"))


def test_qdrant_outage_maps_readiness_and_ask_to_503(tmp_path):
    rt = runtime(tmp_path, config(), FakeGitHub(FILES, SHA_A))
    with TestClient(create_app("unused", runtime=rt)) as client:
        ingest(rt)
        with patch.object(rt.client, "collection_exists", side_effect=qdrant_outage()):
            response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"
        assert "private URL" not in response.text
        with patch.object(rt.client, "query_points", side_effect=qdrant_outage()):
            response = client.post("/ask", json={"question": QUESTION})
        assert response.status_code == 503
        assert response.json()["error"]["provider"] == "qdrant"


def test_qdrant_outage_maps_cli_to_exit_4(tmp_path, monkeypatch, capsys):
    rt = runtime(tmp_path, config(), FakeGitHub(FILES, SHA_A))
    ingest(rt)
    monkeypatch.setattr(cli, "_runtime", lambda *_args: rt)
    with patch.object(rt.client, "query_points", side_effect=qdrant_outage()):
        assert cli.main(["ask", QUESTION]) == EXIT_UPSTREAM
    assert "qdrant: unavailable" in capsys.readouterr().err
