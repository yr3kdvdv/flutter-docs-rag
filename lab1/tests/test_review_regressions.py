"""Regression tests for findings F1-F6 of the Codex verification (docs/reviews/verification.md).

FAKE GitHub/embedder/LLM, real grabber/preprocessing/cache/embedded Qdrant/ASGI app.
A failed download is INJECTED here; this does not prove how real GitHub 5xx look.
"""

from contextlib import contextmanager

import pytest
from fakes import CONTENT, INCLUDES, FakeEmbedder, FakeGitHub, FakeLLM
from fastapi.testclient import TestClient
from test_pipeline import LAYOUT, make_cfg

from flutter_rag import cli
from flutter_rag.api import create_app
from flutter_rag.config import Settings
from flutter_rag.errors import IndexNotReadyError, MissingSecretError, UpstreamError
from flutter_rag.generation import LLMAnswer
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import (
    REFUSAL_TEXT,
    Runtime,
    ask,
    ingest,
    question_language,
    require_secrets,
)

PAGE = CONTENT + "ui/layout.md"
FRAGMENT = INCLUDES + "docs/fragment.md"
FRAGMENT_TEXT = "## Fragment\n\nUNIQUE_FRAGMENT_CONTENT: hot reload keeps the state.\n"


class FailingGitHub(FakeGitHub):
    """Raises the error our GitHub client raises after its retries are exhausted."""

    fail: set[str]

    def __init__(self, files, commit="c1"):
        super().__init__(files, commit)
        self.fail = set()

    def fetch_raw(self, commit_sha, path):
        if path in self.fail:
            raise UpstreamError("github", "unavailable", "injected exhausted retries", 503)
        return super().fetch_raw(commit_sha, path)


@pytest.fixture
def make_rt(tmp_path):
    made = []

    def make(gh, llm=None, tracer=None):
        settings = Settings(_env_file=None, data_dir=tmp_path, qdrant_path=tmp_path / "q")
        rt = Runtime(
            make_cfg(),
            settings,
            embedder=FakeEmbedder(),
            llm=llm or FakeLLM(),
            tracer=tracer or Tracer(None, enabled=False),
            github_factory=lambda: gh,
        )
        made.append(rt)
        return rt

    yield make
    for rt in made:
        rt.close()


def texts(rt) -> str:
    return "\n".join(
        p.payload["text"] for p in rt.client.scroll(rt.store.collection, limit=1000)[0]
    )


# ---------------------------------------------------------------- F1
def test_failed_include_is_indexed_after_successful_retry(make_rt):
    gh = FailingGitHub(
        {PAGE: LAYOUT + '\n{% render "docs/fragment.md" %}\n', FRAGMENT: FRAGMENT_TEXT}
    )
    gh.fail = {FRAGMENT}
    rt = make_rt(gh)
    first = ingest(rt)
    assert first.failed == [FRAGMENT]
    assert first.documents["failed"] == 1 and first.indexed_documents == []
    assert "UNIQUE_FRAGMENT_CONTENT" not in texts(rt)

    gh.fail = set()
    retry = ingest(rt)
    assert retry.failed == [] and retry.indexed_documents == ["ui/layout"]
    assert "UNIQUE_FRAGMENT_CONTENT" in texts(rt)


def test_failed_new_include_keeps_previous_complete_version(make_rt):
    gh = FailingGitHub(
        {PAGE: LAYOUT + '\n{% render "docs/fragment.md" %}\n', FRAGMENT: FRAGMENT_TEXT}
    )
    rt = make_rt(gh)
    ingest(rt)
    gh.files[FRAGMENT] = FRAGMENT_TEXT.replace("UNIQUE_FRAGMENT_CONTENT", "NEW_FRAGMENT_CONTENT")
    gh.commit, gh.fail = "c2", {FRAGMENT}
    r = ingest(rt)
    assert r.stale_documents == ["ui/layout"] and r.removed_documents == []
    assert "UNIQUE_FRAGMENT_CONTENT" in texts(rt)  # old complete text is still searchable
    gh.fail = set()
    ingest(rt)
    assert "NEW_FRAGMENT_CONTENT" in texts(rt) and "UNIQUE_FRAGMENT_CONTENT" not in texts(rt)


# ---------------------------------------------------------------- F2
def test_failed_update_download_keeps_previous_points(make_rt):
    gh = FailingGitHub({PAGE: LAYOUT})
    rt = make_rt(gh)
    first = ingest(rt)
    gh.files[PAGE] = LAYOUT.replace("Sizes go up.", "Sizes move upward.")
    gh.commit, gh.fail = "c2", {PAGE}
    failed = ingest(rt)
    assert failed.points_total == first.points_total > 0
    assert failed.removed_documents == [] and failed.stale_documents == ["ui/layout"]
    assert failed.diff["deleted"] == 0 and failed.diff["failed"] == 1
    assert "Sizes go up." in texts(rt)

    gh.fail = set()
    repaired = ingest(rt)
    assert repaired.indexed_documents == ["ui/layout"] and repaired.stale_documents == []
    assert "Sizes move upward." in texts(rt) and "Sizes go up." not in texts(rt)


def test_mass_download_failure_does_not_empty_the_index(make_rt):
    other = CONTENT + "tools/other.md"
    gh = FailingGitHub({PAGE: LAYOUT, other: LAYOUT.replace("Center", "Align")})
    rt = make_rt(gh)
    points = ingest(rt).points_total
    gh.files = {p: t + "\nchanged\n" for p, t in gh.files.items()}
    gh.commit, gh.fail = "c2", set(gh.files)
    assert ingest(rt).points_total == points


# ---------------------------------------------------------------- F3
def test_ask_before_ingest_is_not_ready_not_insufficient_context(make_rt):
    llm = FakeLLM()
    rt = make_rt(FakeGitHub({PAGE: LAYOUT}), llm=llm)
    with pytest.raises(IndexNotReadyError):
        ask(rt, "What are constraints?")
    assert llm.calls == 0


def test_api_ask_before_ingest_returns_503_json(make_rt):
    rt = make_rt(FakeGitHub({PAGE: LAYOUT}))
    app = create_app("unused", runtime=rt)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/ask", json={"question": "What are constraints?"})
        assert r.status_code == 503 and r.json()["status"] == "not_ready"
        ingest(rt)
        assert client.post("/ask", json={"question": "What are constraints?"}).status_code == 200


# ---------------------------------------------------------------- F4
KEYS = ("GEMINI_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def test_blank_keys_from_env_example_are_missing(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=\nLANGFUSE_PUBLIC_KEY=   \nLANGFUSE_SECRET_KEY=''\n")
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    settings = Settings(_env_file=env)
    assert not any(settings.secret_status()[k] for k in KEYS)
    with pytest.raises(MissingSecretError):
        require_secrets(settings, "ingest")


def test_cli_blank_keys_exit_2_without_traceback(monkeypatch, capsys):
    for k in KEYS:
        monkeypatch.setenv(k, "")
    assert cli.main(["env-check"]) == 0
    assert capsys.readouterr().out.count("MISSING") >= 3
    assert cli.main(["ingest"]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


# ---------------------------------------------------------------- F5
class RecordingTracer(Tracer):
    def __init__(self):
        super().__init__(None, enabled=False)
        self.trace_meta, self.annotated = None, []

    @contextmanager
    def trace(self, name, *, input, metadata, tags):
        self.trace_meta = dict(metadata)
        with super().trace(name, input=input, metadata=metadata, tags=tags) as root:
            yield root

    @contextmanager
    def annotate(self, root, metadata):
        self.annotated.append(dict(metadata))
        yield


def test_ingest_trace_gets_the_snapshot_it_actually_indexed(make_rt):
    gh = FakeGitHub({PAGE: LAYOUT}, commit="c1")
    tracer = RecordingTracer()
    rt = make_rt(gh, tracer=tracer)
    ingest(rt)
    assert "corpus_commit" not in tracer.trace_meta
    assert tracer.trace_meta["previous_corpus_commit"] is None
    assert tracer.annotated == [{"corpus_commit": "c1"}]
    gh.commit = "c2"
    gh.files[PAGE] = LAYOUT + "\nmore\n"
    ingest(rt)
    assert tracer.trace_meta["previous_corpus_commit"] == "c1"
    assert tracer.annotated[-1] == {"corpus_commit": "c2"}


# ---------------------------------------------------------------- F6
@pytest.mark.parametrize(
    "question, expected",
    [
        ("Как настроить Firebase Cloud Messaging для push-уведомлений во Flutter?", "ru"),
        ("How do I use hot reload?", "en"),
        # G1 (re-verification e366b6e): quoted Russian name inside an English question
        ('How do I publish a Flutter app named "Привет" to the Apple App Store?', "en"),
        ("How do I show the text «Привет, мир» in a Text widget?", "en"),
        ("Why does `Text('Привет')` overflow in a Row?", "en"),
        ("Don't I need 'Привет' localized?", "en"),
        # Russian questions full of Latin names, quotes and code stay Russian
        ("Почему говорят «Constraints go down. Sizes go up. Parent sets position»?", "ru"),
        ('Как работает `setState` в StatefulWidget и что делает "hot reload"?', "ru"),
        ("Что значит «Привет»?", "ru"),
        ("«Как работает hot reload?»", "ru"),  # fully quoted: the whole text decides
    ],
)
def test_question_language(question, expected):
    assert question_language(question) == expected


def test_english_refusal_kept_english_for_quoted_russian_name(make_rt):
    english = LLMAnswer(status="insufficient_context", answer="No info.", citations=[])
    rt = make_rt(FakeGitHub({PAGE: LAYOUT}), llm=FakeLLM(english))
    ingest(rt)
    a = ask(rt, 'How do I publish a Flutter app named "Привет" to the Apple App Store?')
    assert a.status == "insufficient_context" and a.text == REFUSAL_TEXT["en"]


def test_english_refusal_to_russian_question_is_returned_in_russian(make_rt):
    english = LLMAnswer(
        status="insufficient_context",
        answer="The provided documentation does not contain information on this.",
        citations=[],
    )
    rt = make_rt(FakeGitHub({PAGE: LAYOUT}), llm=FakeLLM(english))
    ingest(rt)
    ru = ask(rt, "Как настроить Firebase Cloud Messaging для push-уведомлений во Flutter?")
    assert ru.status == "insufficient_context" and ru.text == REFUSAL_TEXT["ru"]
    en = ask(rt, "How do I configure Firebase Cloud Messaging?")
    assert en.text == REFUSAL_TEXT["en"]


def test_english_answer_to_russian_question_is_flagged(make_rt):
    llm = FakeLLM(LLMAnswer(status="answered", answer="Sizes go up [1].", citations=[1]))
    rt = make_rt(FakeGitHub({PAGE: LAYOUT}), llm=llm)
    ingest(rt)
    a = ask(rt, "Что говорит правило про размеры?")
    assert a.status == "answered" and "answer_language_mismatch: expected ru" in a.warnings
