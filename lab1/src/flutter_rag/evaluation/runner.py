"""Experiment runner (docs/contracts/stage05.md §5.3).

`flutter-rag evaluate --config <yaml> --split dev [--final] --mode retrieval|full [--run-id ID]`

- one Langfuse trace per item, named eval.retrieval / eval.full, session id = run_id, with the
  per-item scores attached to the trace;
- output: experiments/runs/<run_id>/{config.yaml, raw.jsonl, metrics.json, meta.json};
- raw.jsonl is append-only: every attempt is a row, error rows stay. A rerun with the same
  --run-id skips items that already have a row without error (quota, 503) and retries the rest;
- metrics use the last successful row of each item; items that only failed are reported as
  errors and are not mixed with refusals;
- the test split is opened only with --final (N03), recorded in meta.

Full mode runs the same code path as `pipeline.ask` (`_ask_inner`) inside the eval trace, so the
answer is produced exactly like in the service; the LLM is wrapped only to record the excerpts it
received, which the judge needs for faithfulness.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from flutter_rag.config import LAB1_DIR
from flutter_rag.errors import RagError, UpstreamError
from flutter_rag.evaluation import metrics as M
from flutter_rag.evaluation.dataset import Dataset, QAItem
from flutter_rag.evaluation.judge import Judge
from flutter_rag.observability import git_revision

RUNS_DIR = LAB1_DIR / "experiments" / "runs"
MODES = ("retrieval", "full")
SCORE_K = 5  # the K whose retrieval scores are attached to each Langfuse trace


class RunMismatchError(RagError):
    """--run-id points to a run made with another config, dataset, split or mode."""


@dataclass
class RunSummary:
    run_id: str
    out_dir: Path
    processed: int
    skipped: int
    errors: int
    remaining_errors: list[str] = field(default_factory=list)
    stopped_early: bool = False
    trace_ids: dict[str, str | None] = field(default_factory=dict)


def default_run_id(config_id: str, mode: str, split: str) -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{config_id}-{mode}-{split}"


class _RecordingLLM:
    """Delegates to the real LLM and keeps the user text (numbered excerpts + question)."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.model_id = getattr(inner, "model_id", None)
        self.last_user_text: str | None = None

    def generate(self, prompt, user_text):
        self.last_user_text = user_text
        return self.inner.generate(prompt, user_text)


@contextmanager
def _session(tracer, run_id: str) -> Iterator[None]:
    if not tracer.enabled:
        yield
        return
    from langfuse import propagate_attributes

    with propagate_attributes(session_id=run_id):
        yield


def _score(root: Any, name: str, value: float | None, comment: str | None = None) -> None:
    if value is None or not hasattr(root, "score_trace"):
        return
    try:
        root.score_trace(name=name, value=float(value), data_type="NUMERIC", comment=comment)
    except Exception:  # noqa: BLE001 - scores must not break the run
        pass


def _read_raw(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def run_evaluation(
    rt,
    dataset: Dataset,
    *,
    mode: str,
    run_id: str,
    final: bool = False,
    judge: Judge | None = None,
    runs_dir: Path = RUNS_DIR,
    config_path: str | None = None,
    limit: int | None = None,
    max_consecutive_errors: int = 3,
) -> RunSummary:
    if mode not in MODES:
        raise RagError(f"unknown mode {mode!r}; expected one of {MODES}")
    if dataset.split == "test" and not final:  # second guard; load_split has the first
        from flutter_rag.evaluation.dataset import SplitGuardError

        raise SplitGuardError("the test split needs --final (N03)")
    if mode == "full" and judge is None:
        raise RagError("full mode needs a judge")

    run_meta = rt.run_metadata()
    if run_meta.get("corpus_commit") is None:
        raise RagError(
            f"no manifest for corpus {rt.cfg.corpus.name!r} in {rt.data_dir}: run ingest first"
        )
    stale = [i.id for i in dataset.items if i.corpus_commit != run_meta["corpus_commit"]]
    if stale:
        raise RagError(
            f"dataset labelled on {dataset.items[0].corpus_commit[:12]}, index is on "
            f"{run_meta['corpus_commit'][:12]}: gold labels would not match ({len(stale)} items)"
        )

    out = runs_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    raw_path, meta_path = out / "raw.jsonl", out / "meta.json"
    identity = {
        "mode": mode,
        "split": dataset.split,
        "final": final,
        "dataset_version": dataset.version,
        "dataset_sha256": dataset.sha256,
        "config_fingerprint": run_meta["config_fingerprint"],
        "git_sha": run_meta["git_sha"],
        "git_dirty": run_meta["git_dirty"],
        "corpus_commit": run_meta["corpus_commit"],
        "prompt_sha256": run_meta["prompt_sha256"],
        "judge_model": judge.model_id if judge else None,
        "judge_prompt_sha256": judge.prompt.sha256[:16] if judge else None,
    }
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
    if meta is not None:
        previous = {**meta["pipeline"], **meta["identity"]}
        diff = {k: (previous.get(k), v) for k, v in identity.items() if previous.get(k) != v}
        if diff:
            raise RunMismatchError(f"run {run_id} exists with different settings: {diff}")
    else:
        if raw_path.exists() and raw_path.stat().st_size:
            raise RunMismatchError(f"run {run_id} has raw attempts without provenance")
        (out / "config.yaml").write_text(
            yaml.safe_dump(rt.cfg.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        )
        meta = {
            "run_id": run_id,
            "identity": identity,
            "created_at": _now(),
            "config_path": config_path,
            "dataset": {
                "version": dataset.version,
                "split": dataset.split,
                "path": str(dataset.path.relative_to(LAB1_DIR))
                if dataset.path.is_relative_to(LAB1_DIR)
                else str(dataset.path),
                "sha256": dataset.sha256,
                "items": len(dataset.items),
                "statuses": _count(i.status for i in dataset.items),
            },
            "final": final,
            "pipeline": run_meta,
            "judge": (
                {
                    "model": judge.model_id,
                    "prompt_version": f"{judge.prompt.name}/{judge.prompt.version}",
                    "prompt_sha256": judge.prompt.sha256[:16],
                    "temperature": 0.0,
                }
                if judge
                else None
            ),
            "langfuse": {"enabled": rt.tracer.enabled, "session_id": run_id},
            "complete": False,
            "invocations": [],
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    rows = _read_raw(raw_path)
    done = {r["id"] for r in rows if r.get("error") is None}
    attempts = _count(r["id"] for r in rows)
    invocation = {"started_at": _now(), **git_revision(), "processed": 0, "skipped": 0}

    if mode == "full":
        rt.llm = _RecordingLLM(rt.llm)
    todo = [i for i in dataset.items if i.id not in done]
    invocation["skipped"] = len(dataset.items) - len(todo)
    if limit is not None:
        todo = todo[:limit]

    summary = RunSummary(run_id, out, 0, invocation["skipped"], 0)
    consecutive = 0
    for item in todo:
        row = _run_item(rt, item, mode=mode, run_id=run_id, judge=judge, base_meta=run_meta)
        row["attempt"] = attempts.get(item.id, 0) + 1
        _append(raw_path, row)
        rows.append(row)
        summary.processed += 1
        summary.trace_ids[item.id] = row.get("trace_id")
        if row["error"] is not None:
            summary.errors += 1
            consecutive += 1
            if max_consecutive_errors and consecutive >= max_consecutive_errors:
                summary.stopped_early = True  # quota / outage: leave the rest for --run-id resume
                break
        else:
            consecutive = 0
    rt.tracer.flush()

    invocation.update(
        finished_at=_now(),
        processed=summary.processed,
        errors=summary.errors,
        stopped_early=summary.stopped_early,
    )
    meta["invocations"].append(invocation)
    metrics, latest = compute_metrics(rows, dataset, mode)
    summary.remaining_errors = sorted(i for i, r in latest.items() if r["error"] is not None)
    missing = [i.id for i in dataset.items if i.id not in latest]
    meta.update(
        updated_at=_now(),
        complete=not summary.remaining_errors and not missing,
        not_run=missing,
        remaining_errors=summary.remaining_errors,
        errors=[
            {"id": r["id"], "attempt": r["attempt"], **r["error"]} for r in rows if r.get("error")
        ],
        trace_ids={i: r.get("trace_id") for i, r in sorted(latest.items())},
        all_trace_ids=[r.get("trace_id") for r in rows if r.get("trace_id")],
    )
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n")
    return summary


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _provider_stats(rt) -> dict:
    providers = {"embedding": rt.embedder, "rerank": rt.reranker}
    return {
        stage: asdict(stats)
        for stage, provider in providers.items()
        if (stats := getattr(provider, "stats", None)) is not None
    }


def _run_item(rt, item: QAItem, *, mode: str, run_id: str, judge, base_meta: dict) -> dict:
    from flutter_rag.pipeline import Answer, _ask_inner, _candidate_row, search

    t0 = time.monotonic()
    before = _provider_stats(rt)
    row: dict[str, Any] = {
        "id": item.id,
        "run_id": run_id,
        "mode": mode,
        "started_at": _now(),
        "type": item.type,
        "language": item.language,
        "answerable": item.answerable,
        "question": item.question,
        "error": None,
    }
    metadata = {
        **base_meta,
        "run_id": run_id,
        "item_id": item.id,
        "dataset_version": item.dataset_version,
        "split": item.split,
        "question_type": item.type,
    }
    lat: dict[str, float] = {}
    with (
        _session(rt.tracer, run_id),
        rt.tracer.trace(
            f"eval.{mode}",
            input={"id": item.id, "question": item.question},
            metadata=metadata,
            tags=["eval", mode, item.split],
        ) as root,
    ):
        row["trace_id"] = rt.tracer.current_trace_id()
        try:
            if mode == "retrieval":
                found = search(rt, item.question, lat)
                row["retrieved"] = [_candidate_row(c) for c in found.retrieved]
                row["ranked"] = [_candidate_row(c) for c in found.ranked]
                row["context_chunk_ids"] = [i.candidate.chunk.chunk_id for i in found.context]
                row["context_tokens_est"] = sum(
                    i.candidate.chunk.token_count for i in found.context
                )
                row["dropped"] = found.dropped
            else:
                answer = Answer(
                    status="upstream_error", question=item.question, text=None, sources=[]
                )
                rt.llm.last_user_text = None
                try:
                    _ask_inner(rt, item.question, answer, lat)
                except UpstreamError as err:
                    answer.status, answer.error = "upstream_error", err.to_dict()
                row["ranked"] = answer.ranked
                row["retrieved"] = answer.retrieved
                row["answer"] = {
                    "status": answer.status,
                    "text": answer.text,
                    "sources": [asdict(s) for s in answer.sources],
                    "warnings": answer.warnings,
                    "usage": answer.usage,
                }
                if answer.status == "upstream_error":
                    row["error"] = {"stage": "answer", **(answer.error or {})}
                else:
                    row["generation"] = _generation(item, answer)
                    if answer.status == "answered":
                        row["judge"] = _judge(rt, judge, item, answer)
                        row["generation"]["judge"] = {
                            k: row["judge"][k] for k in ("correctness", "faithfulness")
                        }
            if item.answerable and row["error"] is None:
                row["retrieval_metrics"] = M.retrieval_item_metrics(
                    row["ranked"], item.gold_sections, item.gold_documents
                )
        except UpstreamError as err:
            row["error"] = {"stage": "judge" if mode == "full" else "retrieval", **err.to_dict()}
        row["provider_usage"] = {
            stage: {key: round(value - before[stage][key], 4) for key, value in totals.items()}
            for stage, totals in _provider_stats(rt).items()
        }
        row["latency_ms"] = {**lat, "total": round((time.monotonic() - t0) * 1000, 1)}

        if row["error"] is not None:
            root.update(level="ERROR", status_message=row["error"].get("message"))
        else:
            _attach_scores(root, row)
        root.update(
            output={
                k: row.get(k)
                for k in ("error", "retrieval_metrics", "generation", "judge")
                if row.get(k) is not None
            }
            | ({"answer": row["answer"]["text"]} if row.get("answer") else {})
        )
    return row


def _generation(item: QAItem, answer) -> dict:
    cited = [s.chunk_id for s in answer.sources]
    return {
        "status": answer.status,
        "answerable": item.answerable,
        "refusal_correct": M.refusal_correct(item.answerable, answer.status),
        "citations": M.citation_matches(
            cited, answer.ranked, item.gold_sections, item.gold_documents
        ),
        "must_include": M.must_include_found(answer.text, item.must_include)
        if answer.status == "answered"
        else [False] * len(item.must_include),
        "code_present": M.code_present(
            answer.text if answer.status == "answered" else None, item.expected_code
        ),
    }


def _judge(rt, judge: Judge, item: QAItem, answer) -> dict:
    context = rt.llm.last_user_text or ""
    with rt.tracer.observe(
        "judge",
        as_type="generation",
        model=judge.model_id,
        input={"question": item.question, "answer": answer.text},
        model_parameters={"temperature": 0.0},
        metadata={
            "prompt": f"{judge.prompt.name}/{judge.prompt.version}",
            "prompt_sha256": judge.prompt.sha256,
        },
    ) as gen:
        res = judge.judge(
            question=item.question,
            expected_answer=item.expected_answer,
            must_include=item.must_include,
            context=context,
            answer=answer.text or "",
        )
        gen.update(output=res.raw_text, usage_details=res.usage)
    return {
        "correctness": res.correctness,
        "faithfulness": res.faithfulness,
        "reason": res.reason,
        "model": res.model,
        "model_version": res.model_version,
        "usage": res.usage,
    }


def _attach_scores(root: Any, row: dict) -> None:
    rm = row.get("retrieval_metrics")
    if rm:
        for level, short in (("section", "sec"), ("document", "doc")):
            _score(root, f"{short}_hit@{SCORE_K}", rm[level][f"hit@{SCORE_K}"])
            _score(root, f"{short}_recall@{SCORE_K}", rm[level][f"recall@{SCORE_K}"])
            _score(root, f"{short}_mrr", rm[level]["mrr"])
    gen = row.get("generation")
    if gen:
        _score(root, "refusal_correct", 1.0 if gen["refusal_correct"] else 0.0)
        if gen["code_present"] is not None:
            _score(root, "expected_code_present", 1.0 if gen["code_present"] else 0.0)
        if gen["must_include"]:
            _score(root, "must_include", sum(gen["must_include"]) / len(gen["must_include"]))
    j = row.get("judge")
    if j:
        _score(root, "judge_correctness", j["correctness"], j["reason"])
        _score(root, "judge_faithfulness", j["faithfulness"], j["reason"])


def compute_metrics(rows: list[dict], dataset: Dataset, mode: str) -> tuple[dict, dict[str, dict]]:
    """Metrics over the latest successful row per item (else its latest error row)."""
    latest: dict[str, dict] = {}
    for r in rows:
        prev = latest.get(r["id"])
        if prev is None or r.get("error") is None or prev.get("error") is not None:
            latest[r["id"]] = r
    items = {i.id: i for i in dataset.items}
    ok = [r for i, r in latest.items() if r.get("error") is None and i in items]
    answerable = [r for r in ok if items[r["id"]].answerable]
    out: dict[str, Any] = {
        "run_id": rows[0]["run_id"] if rows else None,
        "mode": mode,
        "split": dataset.split,
        "dataset_version": dataset.version,
        "items": len(dataset.items),
        "completed": len(ok),
        "errors": sorted(i for i, r in latest.items() if r.get("error") is not None),
        "not_run": sorted(set(items) - set(latest)),
        "attempts": len(rows),
        "retrieval": M.aggregate_retrieval([r["retrieval_metrics"] for r in answerable]),
        "by_type": {},
    }
    for t in sorted({i.type for i in dataset.items if i.answerable}):
        group = [r for r in answerable if items[r["id"]].type == t]
        if group:
            out["by_type"][t] = M.aggregate_retrieval([r["retrieval_metrics"] for r in group])
    if mode == "full":
        gen_rows = [r["generation"] for r in ok]
        gen_rows += [
            {"status": "upstream_error", "answerable": items[i].answerable}
            for i, r in latest.items()
            if r.get("error") is not None and r["error"].get("stage") == "answer"
        ]
        out["generation"] = M.aggregate_generation(gen_rows)
    return out, latest
