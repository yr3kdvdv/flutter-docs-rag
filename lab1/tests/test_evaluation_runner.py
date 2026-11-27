"""Runner: output layout, resume, error rows, split guard. FAKE providers + real embedded Qdrant.

Nothing here calls Gemini or Langfuse (tracing disabled); see tests/fakes.py.
"""

import json

import pytest
from fakes import CONTENT, FakeEmbedder, FakeGitHub, FakeLLM
from test_pipeline import LAYOUT, RELOAD, make_cfg

from flutter_rag import cli
from flutter_rag.config import Settings
from flutter_rag.errors import RagError, UpstreamError
from flutter_rag.evaluation.dataset import Dataset, QAItem, SplitGuardError
from flutter_rag.evaluation.judge import (
    JudgeResult,
    load_judge_prompt,
    parse_verdict,
    render_judge_input,
)
from flutter_rag.evaluation.runner import RunMismatchError, run_evaluation
from flutter_rag.generation import LLMAnswer
from flutter_rag.observability import Tracer
from flutter_rag.pipeline import Runtime, ingest


class FakeJudge:
    model_id = "fake-judge"

    def __init__(self, error=None):
        self.prompt = load_judge_prompt("v1")
        self.calls = []
        self.error = error

    def judge(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        return JudgeResult(4, 5, "ok", self.model_id, "v", {"total": 1}, "{}", "")


def item(n, type_, question, sections, docs, answerable=True, **over):
    data = {
        "id": f"dev-{n:03d}",
        "split": "dev",
        "dataset_version": "tiny",
        "type": type_,
        "language": "en",
        "question": question,
        "answerable": answerable,
        "expected_answer": "x",
        "must_include": ["sizes"] if answerable else [],
        "expected_code": None,
        "gold_documents": docs,
        "gold_sections": sections,
        "supporting_excerpts": [{"section_id": s, "text": "t"} for s in sections],
        "corpus_commit": "c1",
        "status": "draft",
        "notes": "",
    }
    data.update(over)
    return QAItem.model_validate(data)


ITEMS = [
    item(
        1,
        "factoid",
        "What does the constraints rule say about sizes?",
        ["ui/layout#the-rule"],
        ["ui/layout"],
    ),
    item(
        2,
        "multi_doc",
        "Hot reload state and Center child size?",
        ["ui/layout#center", "tools/reload#how-to-perform-a-hot-reload"],
        ["ui/layout", "tools/reload"],
    ),
    item(3, "unanswerable", "How do I read NFC tags?", [], [], answerable=False),
]


def dataset(tmp_path, split="dev"):
    return Dataset("tiny", split, tmp_path / "dev.jsonl", "sha-1", ITEMS)


@pytest.fixture
def make_rt(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", qdrant_path=tmp_path / "q")
    gh = FakeGitHub({CONTENT + "ui/layout.md": LAYOUT, CONTENT + "tools/reload.md": RELOAD})
    opened = []

    def make(llm=None):
        rt = Runtime(
            make_cfg(),
            settings,
            embedder=FakeEmbedder(),
            llm=llm or FakeLLM(),
            tracer=Tracer(None, enabled=False),
            github_factory=lambda: gh,
        )
        opened.append(rt)
        return rt

    rt = make()
    ingest(rt)
    rt.close()
    opened.clear()
    yield make
    for rt in opened:
        try:
            rt.close()
        except Exception:
            pass


def read_raw(out):
    return [json.loads(x) for x in (out / "raw.jsonl").read_text().splitlines()]


def test_retrieval_run_layout_and_metrics(tmp_path, make_rt):
    runs = tmp_path / "runs"
    rt = make_rt()
    s = run_evaluation(rt, dataset(tmp_path), mode="retrieval", run_id="r1", runs_dir=runs)
    out = runs / "r1"
    assert {p.name for p in out.iterdir()} == {
        "config.yaml",
        "raw.jsonl",
        "metrics.json",
        "meta.json",
    }
    assert s.processed == 3 and s.errors == 0
    rows = read_raw(out)
    assert [r["id"] for r in rows] == ["dev-001", "dev-002", "dev-003"]
    assert rows[0]["provider_usage"]["embedding"]["api_calls"] == 1
    assert rows[0]["ranked"] and "retrieval_metrics" in rows[0]
    assert "retrieval_metrics" not in rows[2]  # unanswerable: no retrieval metrics
    metrics = json.loads((out / "metrics.json").read_text())
    assert metrics["retrieval"]["n"] == 2  # answerable only
    assert metrics["retrieval"]["document"]["hit@20"] == {"k": 2, "n": 2, "rate": 1.0}
    meta = json.loads((out / "meta.json").read_text())
    assert meta["pipeline"]["corpus_commit"] == "c1"
    assert meta["dataset"]["sha256"] == "sha-1" and meta["complete"] is True
    assert meta["identity"]["mode"] == "retrieval" and meta["final"] is False
    assert {"git_sha", "git_dirty", "config_fingerprint", "llm_model"} <= set(meta["pipeline"])


def test_full_mode_error_rows_are_kept_and_resume_skips_done(tmp_path, make_rt):
    runs = tmp_path / "runs"
    boom = UpstreamError("gemini", "unavailable", "503 high demand", 503)
    rt = make_rt(llm=FakeLLM(error=boom))
    s1 = run_evaluation(
        rt,
        dataset(tmp_path),
        mode="full",
        run_id="f1",
        runs_dir=runs,
        judge=FakeJudge(),
        max_consecutive_errors=0,
    )
    rt.close()
    assert s1.errors == 3 and sorted(s1.remaining_errors) == ["dev-001", "dev-002", "dev-003"]
    rows = read_raw(runs / "f1")
    assert all(r["error"]["kind"] == "unavailable" for r in rows)
    m1 = json.loads((runs / "f1" / "metrics.json").read_text())
    assert m1["generation"]["upstream_error"] == {"k": 3, "n": 3}
    assert m1["generation"]["refusal_accuracy"]["n"] == 0  # errors are not refusals

    llm = FakeLLM(LLMAnswer(status="answered", answer="Sizes go up [1].", citations=[1]))
    judge = FakeJudge()
    rt = make_rt(llm=llm)
    s2 = run_evaluation(rt, dataset(tmp_path), mode="full", run_id="f1", runs_dir=runs, judge=judge)
    rt.close()
    assert s2.processed == 3 and s2.errors == 0
    rows = read_raw(runs / "f1")
    assert len(rows) == 6  # error rows stay in raw
    assert [r["attempt"] for r in rows[3:]] == [2, 2, 2]
    assert "Documentation excerpts" in judge.calls[0]["context"]  # judge saw the real context

    # third call: everything is done -> nothing processed, no LLM call
    llm3 = FakeLLM()
    rt = make_rt(llm=llm3)
    s3 = run_evaluation(
        rt, dataset(tmp_path), mode="full", run_id="f1", runs_dir=runs, judge=FakeJudge()
    )
    rt.close()
    assert s3.processed == 0 and s3.skipped == 3 and llm3.calls == 0

    m = json.loads((runs / "f1" / "metrics.json").read_text())
    g = m["generation"]
    assert g["upstream_error"]["k"] == 0
    assert g["refusal_accuracy_answerable"] == {"k": 2, "n": 2, "rate": 1.0}
    assert g["refusal_accuracy_unanswerable"]["k"] == 0  # answered an unanswerable question
    assert g["must_include_terms"]["k"] == 2
    assert g["judge_correctness"]["n"] == 3
    meta = json.loads((runs / "f1" / "meta.json").read_text())
    assert len(meta["errors"]) == 3 and len(meta["invocations"]) == 3 and meta["complete"]


def test_stop_after_consecutive_errors_and_judge_error_is_an_item_error(tmp_path, make_rt):
    runs = tmp_path / "runs"
    rt = make_rt()
    err = UpstreamError("gemini", "rate_limited", "quota", 429)
    s = run_evaluation(
        rt,
        dataset(tmp_path),
        mode="full",
        run_id="j1",
        runs_dir=runs,
        judge=FakeJudge(error=err),
        max_consecutive_errors=2,
    )
    assert s.stopped_early and s.processed == 2
    rows = read_raw(runs / "j1")
    assert rows[0]["error"]["stage"] == "judge" and rows[0]["answer"]["status"] == "answered"
    meta = json.loads((runs / "j1" / "meta.json").read_text())
    assert meta["not_run"] == ["dev-003"] and meta["complete"] is False


def test_resume_with_other_settings_is_refused(tmp_path, make_rt):
    runs = tmp_path / "runs"
    rt = make_rt()
    run_evaluation(rt, dataset(tmp_path), mode="retrieval", run_id="m1", runs_dir=runs, limit=1)
    with pytest.raises(RunMismatchError):
        run_evaluation(
            rt, dataset(tmp_path), mode="full", run_id="m1", runs_dir=runs, judge=FakeJudge()
        )


def test_resume_rejects_generator_prompt_drift(tmp_path, make_rt, monkeypatch):
    rt = make_rt()
    run_evaluation(rt, dataset(tmp_path), mode="retrieval", run_id="r1", runs_dir=tmp_path, limit=1)
    metadata = rt.run_metadata()
    metadata["prompt_sha256"] = "changed"
    monkeypatch.setattr(rt, "run_metadata", lambda: metadata)
    with pytest.raises(RunMismatchError, match="prompt_sha256"):
        run_evaluation(rt, dataset(tmp_path), mode="retrieval", run_id="r1", runs_dir=tmp_path)


def test_split_guard_and_snapshot_guard(tmp_path, make_rt):
    rt = make_rt()
    with pytest.raises(SplitGuardError):
        run_evaluation(
            rt, dataset(tmp_path, "test"), mode="retrieval", run_id="t", runs_dir=tmp_path
        )
    other = Dataset(
        "tiny", "dev", tmp_path / "x", "s", [ITEMS[0].model_copy(update={"corpus_commit": "zz"})]
    )
    with pytest.raises(RagError, match="gold labels would not match"):
        run_evaluation(rt, other, mode="retrieval", run_id="t2", runs_dir=tmp_path)


def test_cli_refuses_test_without_final_before_any_work(capsys):
    assert cli.main(["evaluate", "--split", "test", "--mode", "full"]) == 2
    assert "--final" in capsys.readouterr().err


def test_judge_input_and_verdict_parsing():
    p = load_judge_prompt("v1")
    text = render_judge_input(
        p, question="Q {answer}", expected_answer="E", must_include=["a"], context="C", answer="A"
    )
    assert "Q {answer}" in text and "<assistant_answer>\nA\n" in text and "- a" in text
    v = parse_verdict('{"reason": "fine", "correctness": 5, "faithfulness": 3}')
    assert (v.correctness, v.faithfulness) == (5, 3)
    with pytest.raises(UpstreamError):
        parse_verdict('{"reason": "x", "correctness": 7, "faithfulness": 3}')
    with pytest.raises(UpstreamError):
        parse_verdict("not json")
