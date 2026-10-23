"""End-to-end pipeline logic with FAKE GitHub/embedder/LLM and a real embedded Qdrant.

These tests prove idempotency, update/delete handling, filtering and citation checks.
They do NOT call Gemini or Langfuse (tracing is disabled here).
"""

import pytest
from fakes import CONTENT, FakeEmbedder, FakeGitHub, FakeLLM

from flutter_rag.config import Settings
from flutter_rag.errors import StorageLockedError, UpstreamError
from flutter_rag.generation import LLMAnswer
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import Runtime, ask, ingest, require_secrets
from flutter_rag.runconfig import RunConfig
from flutter_rag.vectorstore import open_qdrant

LAYOUT = """---
title: Understanding constraints
---
## The rule

Constraints go down. Sizes go up. Parent sets position. A widget gets its constraints
from its parent and then tells its parent about its size.

## Center

Center lets its child be any size up to the screen size, and positions it in the middle.
"""
RELOAD = """---
title: Hot reload
---
## How to perform a hot reload

Hot reload injects updated source code into the running Dart VM and keeps the app state,
so you can see changes quickly without restarting the app.
"""


def make_cfg(**filtering) -> RunConfig:
    return RunConfig.model_validate(
        {
            "config_id": "test",
            "corpus": {"name": "test", "include": [CONTENT + "**/*.md"]},
            "embedding": {"dimensions": 64},
            "filtering": {"min_chars": 10, **filtering},
            "generation": {"model": "fake-llm"},
        }
    )


@pytest.fixture
def env(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path, qdrant_path=tmp_path / "q")
    gh = FakeGitHub({CONTENT + "ui/layout.md": LAYOUT, CONTENT + "tools/reload.md": RELOAD})
    created = []

    def runtime(cfg=None, llm=None):
        rt = Runtime(
            cfg or make_cfg(),
            settings,
            embedder=FakeEmbedder(),
            llm=llm or FakeLLM(),
            tracer=Tracer(None, enabled=False),
            github_factory=lambda: gh,
        )
        created.append(rt)
        return rt

    yield settings, gh, runtime
    for rt in created:
        try:
            rt.close()
        except Exception:
            pass


def test_reingest_is_idempotent(env):
    _, gh, runtime = env
    rt = runtime()
    r1 = ingest(rt)
    assert r1.indexed_documents == ["tools/reload", "ui/layout"]
    points = r1.points_total
    assert points > 0
    calls = rt.embedder.provider.stats.api_calls

    r2 = ingest(rt)
    assert r2.indexed_documents == [] and r2.chunks_upserted == 0
    assert r2.points_total == points  # no duplicates
    assert rt.embedder.provider.stats.api_calls == calls  # no embedding calls
    assert r2.downloaded_files == 0


def test_modified_and_deleted_documents(env):
    _, gh, runtime = env
    rt = runtime()
    ingest(rt)
    gh.files[CONTENT + "tools/reload.md"] = RELOAD.replace("quickly", "very quickly")
    del gh.files[CONTENT + "ui/layout.md"]
    gh.commit = "c2"
    r = ingest(rt)
    assert r.indexed_documents == ["tools/reload"]
    assert r.removed_documents == ["ui/layout"]
    docs = {p.payload["document_id"] for p in rt.client.scroll(rt.store.collection, limit=100)[0]}
    assert docs == {"tools/reload"}


def test_ask_returns_only_sources_that_were_in_context(env):
    _, _, runtime = env
    llm = FakeLLM(LLMAnswer(status="answered", answer="Sizes go up [1] [9].", citations=[1, 9]))
    rt = runtime(llm=llm)
    ingest(rt)
    a = ask(rt, "What does the constraints rule say about sizes and parents?")
    assert a.status == "answered"
    assert [s.number for s in a.sources] == [1]
    assert "unsupported_citation: [9]" in a.warnings
    # source [1] is exactly the excerpt that was numbered [1] in the prompt sent to the LLM
    first_excerpt = llm.last_user_text.split("[1] ", 1)[1].split("\n---\n", 1)[0]
    assert f"Source: {a.sources[0].url}" in first_excerpt
    assert a.sources[0].url.startswith("https://docs.flutter.dev/")


def test_llm_refusal_is_insufficient_context(env):
    _, _, runtime = env
    llm = FakeLLM(LLMAnswer(status="insufficient_context", answer="No info.", citations=[]))
    rt = runtime(llm=llm)
    ingest(rt)
    a = ask(rt, "How do I bake bread?")
    assert a.status == "insufficient_context" and a.sources == []


def test_threshold_refuses_without_calling_llm(env):
    _, _, runtime = env
    llm = FakeLLM()
    rt = runtime(cfg=make_cfg(min_score=1.01), llm=llm)  # cosine never exceeds 1
    ingest(rt)
    a = ask(rt, "anything")
    assert a.status == "insufficient_context" and llm.calls == 0


def test_upstream_failure_is_not_reported_as_missing_answer(env):
    _, _, runtime = env
    llm = FakeLLM(error=UpstreamError("gemini", "rate_limited", "quota", 429))
    rt = runtime(llm=llm)
    ingest(rt)
    a = ask(rt, "What does hot reload keep?")
    assert a.status == "upstream_error"
    assert a.error["kind"] == "rate_limited" and a.error["retryable"]


def test_second_process_on_same_storage_gets_clear_error(env):
    settings, _, runtime = env
    runtime()  # holds the embedded storage
    import subprocess
    import sys

    code = (
        "from flutter_rag.vectorstore import open_qdrant\n"
        "from flutter_rag.errors import StorageLockedError\n"
        "from pathlib import Path\n"
        f"try:\n    open_qdrant(None, Path({str(settings.qdrant_path)!r}))\n"
        "except StorageLockedError as e:\n    print('LOCKED', e)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout
    assert out.startswith("LOCKED") and "QDRANT_URL" in out
    assert StorageLockedError and open_qdrant  # imported names used


def test_missing_keys_fail_fast(monkeypatch):
    for k in ("GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception) as exc:
        require_secrets(Settings(_env_file=None), "ask")
    assert "GEMINI_API_KEY" in str(exc.value) and "SETUP_ACCOUNTS" in str(exc.value)
