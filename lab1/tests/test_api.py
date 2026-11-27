"""HTTP API with a FAKE-backed runtime (no external calls)."""

import json

import pytest
from fakes import CONTENT, FakeEmbedder, FakeGitHub, FakeLLM, ScriptedLLM
from fastapi.testclient import TestClient

from flutter_rag import cli
from flutter_rag.api import create_app
from flutter_rag.config import Settings
from flutter_rag.errors import UpstreamError
from flutter_rag.generation import LLMAnswer, load_prompt
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


def test_ask_repairs_english_answer_and_ignores_names_and_code(tmp_path):
    valid_text = (
        'Keep the name "Привет" and show the value Салют with hot reload [1].\n'
        'Use `a[99]` or ``print("`текст`[77]")``.\n'
        '~~~dart\n// Список[69]\nfinal message = "Привет!";\n~~~\n'
    )
    llm = ScriptedLLM(
        LLMAnswer(
            status="answered", answer="Состояние сохраняется после перезагрузки [1].", citations=[1]
        ),
        LLMAnswer(status="answered", answer=valid_text, citations=[1]),
    )
    rt = runtime(tmp_path, llm)
    initial_system = rt.prompt.system
    with TestClient(create_app("unused", runtime=rt)) as client:
        ingest(rt)
        response = client.post("/ask", json={"question": "What does hot reload keep?"})
    answer = response.json()
    assert response.status_code == 200 and answer["status"] == "answered"
    assert answer["text"] == valid_text
    assert [source["number"] for source in answer["sources"]] == [1]
    assert answer["warnings"] == ["answer_language_mismatch: expected en"]
    assert answer["usage"] == {"input": 2, "output": 2, "total": 4}
    assert "llm_retry" in answer["latency_ms"]
    assert llm.system_prompts[0] == initial_system
    assert llm.system_prompts[1].startswith(initial_system)
    assert "Write the answer prose in English" in llm.system_prompts[1]


def test_api_reports_invalid_model_answer_without_claiming_corpus_absence(tmp_path):
    llm = FakeLLM(LLMAnswer(status="answered", answer="App state [99].", citations=[99]))
    rt = runtime(tmp_path, llm)
    with TestClient(create_app("unused", runtime=rt)) as client:
        ingest(rt)
        response = client.post("/ask", json={"question": "What does hot reload keep?"})
    answer = response.json()
    assert response.status_code == 503 and answer["status"] == "upstream_error"
    assert answer["error"]["kind"] == "bad_request"
    assert answer["text"] is None and answer["sources"] == [] and llm.calls == 2


@pytest.mark.parametrize(
    ("question", "text"),
    [
        ("Какой текст ошибки показан?", "«No such file or directory» [1]."),
        ("Какой API выбрать?", "Подойдёт Flutter StatefulWidget, setState, BuildContext [1]."),
        ("What does the example read?", "The excerpt says «Read a[99]» [1]."),
    ],
)
def test_ask_treats_quoted_text_and_identifiers_as_literals(tmp_path, question, text):
    llm = FakeLLM(LLMAnswer(status="answered", answer=text, citations=[1]))
    rt = runtime(tmp_path, llm)
    with TestClient(create_app("unused", runtime=rt)) as client:
        ingest(rt)
        response = client.post("/ask", json={"question": question})
    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "answered" and answer["text"] == text
    assert [source["number"] for source in answer["sources"]] == [1]
    assert not answer["warnings"] and llm.calls == 1


@pytest.mark.parametrize(
    ("text", "citations", "warning"),
    [
        ("It keeps app state [99].", [99], "answered_without_citations"),
        ("It keeps app state.", [1], "citation_text_mismatch"),
        (
            "It keeps app state [1] [99].",
            [1],
            "unsupported_inline_citation: [99]",
        ),
        ("It keeps app state [1].", [], "citation_text_mismatch"),
    ],
)
def test_cli_rejects_unconfirmed_citations(tmp_path, monkeypatch, capsys, text, citations, warning):
    llm = FakeLLM(LLMAnswer(status="answered", answer=text, citations=citations))
    rt = runtime(tmp_path, llm)
    ingest(rt)
    monkeypatch.setattr(cli, "_runtime", lambda *_: rt)
    assert cli.main(["ask", "--json", "What does hot reload keep?"]) == 4
    answer = json.loads(capsys.readouterr().out)
    assert answer["status"] == "upstream_error"
    assert "model answer failed validation" in answer["error"]["message"]
    assert answer["text"] is None and answer["sources"] == []
    assert warning in answer["warnings"] and llm.calls == 2


def test_answer_prompt_substitutes_only_slots_from_template():
    prompt = load_prompt("answer", "v1.2")
    rendered = prompt.render_user(
        context="An excerpt containing {question}.",
        question="A question containing {context}?",
    )
    assert "An excerpt containing {question}." in rendered
    assert rendered.endswith("Question: A question containing {context}?")
