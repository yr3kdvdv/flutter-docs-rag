"""HTTP API with a FAKE-backed runtime (no external calls)."""

from fakes import CONTENT, FakeEmbedder, FakeGitHub, FakeLLM
from fastapi.testclient import TestClient

from flutter_rag.api import create_app
from flutter_rag.config import Settings
from flutter_rag.errors import UpstreamError
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import Runtime, ingest
from flutter_rag.runconfig import RunConfig

PAGE = (
    "---\ntitle: Hot reload\n---\n## Hot reload\n\n"
    "Hot reload keeps the app state while code changes.\n"
)


def runtime(tmp_path, llm):
    cfg = RunConfig.model_validate(
        {
            "config_id": "api",
            "corpus": {"name": "api"},
            "embedding": {"dimensions": 32},
            "filtering": {"min_chars": 10},
            "generation": {"model": "fake"},
        }
    )
    settings = Settings(_env_file=None, data_dir=tmp_path, qdrant_path=tmp_path / "q")
    return Runtime(
        cfg,
        settings,
        embedder=FakeEmbedder(32),
        llm=llm,
        tracer=Tracer(None, enabled=False),
        github_factory=lambda: FakeGitHub({CONTENT + "tools/hot-reload.md": PAGE}),
    )


def test_health_ready_and_ask(tmp_path):
    rt = runtime(tmp_path, FakeLLM())
    with TestClient(create_app("unused", runtime=rt)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").status_code == 503  # empty index
        ingest(rt)
        assert client.get("/ready").json()["status"] == "ready"
        r = client.post("/ask", json={"question": "What does hot reload keep?"})
        assert r.status_code == 200 and r.json()["status"] == "answered"
        assert client.post("/ask", json={"question": ""}).status_code == 422


def test_upstream_rate_limit_maps_to_429(tmp_path):
    llm = FakeLLM(error=UpstreamError("gemini", "rate_limited", "quota", 429))
    rt = runtime(tmp_path, llm)
    with TestClient(create_app("unused", runtime=rt)) as client:
        ingest(rt)
        r = client.post("/ask", json={"question": "What does hot reload keep?"})
        assert r.status_code == 429 and r.json()["status"] == "upstream_error"
