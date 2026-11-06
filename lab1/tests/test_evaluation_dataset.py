"""Dataset schema, split guard (N03), validator and corpus isolation (N04). Offline."""

import json

import pytest
from fakes import blob

from flutter_rag.config import LAB1_DIR, REPO_ROOT
from flutter_rag.evaluation.check import check_dataset
from flutter_rag.evaluation.dataset import (
    DATASETS_DIR,
    QAItem,
    SplitGuardError,
    load_split,
)
from flutter_rag.grabber import RawStore, glob_to_regex
from flutter_rag.grabber.manifest import DocEntry, Manifest
from flutter_rag.runconfig import load_run_config

LAYOUT = """---
title: Understanding constraints
---
## The rule

Constraints go down. Sizes go up. Parent sets position.

## Center

Center lets its child be any size up to the screen size.
"""
RELOAD = """---
title: Hot reload
---
## How to perform a hot reload

Hot reload keeps the app state.
"""
COMMIT = "c" * 40
TYPES = ["factoid", "multi_doc", "lookup", "contextual", "unanswerable"]


def make_item(split, n, type_, lang, **over):
    base = {
        "id": f"{split}-{n:03d}",
        "split": split,
        "dataset_version": "tiny",
        "type": type_,
        "language": lang,
        "question": f"Question {split} {n} about {type_}?",
        "answerable": True,
        "expected_answer": "answer",
        "must_include": [],
        "expected_code": None,
        "gold_documents": ["ui/layout"],
        "gold_sections": ["ui/layout#the-rule"],
        "supporting_excerpts": [{"section_id": "ui/layout#the-rule", "text": "Sizes go up."}],
        "corpus_commit": COMMIT,
        "status": "draft",
        "notes": "",
    }
    if type_ == "multi_doc":
        base.update(
            gold_documents=["ui/layout", "tools/reload"],
            gold_sections=["ui/layout#center", "tools/reload#how-to-perform-a-hot-reload"],
            supporting_excerpts=[
                {"section_id": "ui/layout#center", "text": "Center lets its child"},
                {
                    "section_id": "tools/reload#how-to-perform-a-hot-reload",
                    "text": "keeps the app state",
                },
            ],
        )
    if type_ == "unanswerable":
        base.update(
            answerable=False,
            gold_documents=[],
            gold_sections=[],
            supporting_excerpts=[],
            notes='absent_terms: ["harmonyos", "appgallery"]',
        )
    base.update(over)
    return base


def write_dataset(root, dev, test):
    d = root / "tiny"
    d.mkdir(parents=True, exist_ok=True)
    for split, rows in (("dev", dev), ("test", test)):
        (d / f"{split}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return root


def tiny_rows():
    dev = [make_item("dev", i + 1, t, "ru") for i, t in enumerate(TYPES)]
    test = [make_item("test", i + 1, t, "en") for i, t in enumerate(TYPES)]
    return dev, test


@pytest.fixture
def corpus(tmp_path):
    raw = RawStore(tmp_path / "raw")
    docs = {}
    for doc_id, text in (("ui/layout", LAYOUT), ("tools/reload", RELOAD)):
        raw.write(blob(text), text)
        docs[doc_id] = DocEntry(doc_id, f"sites/docs/src/content/{doc_id}.md", "u", blob(text))
    return Manifest("flutter/website", COMMIT, "t", "test", docs), raw


SIZES = {"dev": 1, "test": 1}


def test_valid_tiny_dataset_passes(tmp_path, corpus):
    root = write_dataset(tmp_path / "ds", *tiny_rows())
    r = check_dataset(*corpus, version="tiny", root=root, expected_sizes=SIZES)
    assert r.ok, r.errors
    assert r.checked_excerpts == 10 and r.checked_absent_terms == 4


def test_check_catches_non_verbatim_excerpt_and_wrong_section(tmp_path, corpus):
    dev, test = tiny_rows()
    dev[0]["supporting_excerpts"][0]["text"] = "Sizes go UP."  # paraphrase, not verbatim
    dev[2]["gold_sections"] = ["ui/layout#the-rules"]  # not an anchor of the page
    dev[2]["supporting_excerpts"][0]["section_id"] = "ui/layout#the-rules"
    root = write_dataset(tmp_path / "ds", dev, test)
    r = check_dataset(*corpus, version="tiny", root=root, expected_sizes=SIZES)
    joined = "\n".join(r.errors)
    assert "dev-001: excerpt is not verbatim" in joined
    assert "dev-003: section 'ui/layout#the-rules' is not a section of ui/layout" in joined


def test_check_catches_excerpt_in_wrong_section_absent_term_and_leak(tmp_path, corpus):
    dev, test = tiny_rows()
    dev[3]["supporting_excerpts"][0]["text"] = "Center lets its child"  # lives in #center
    dev[4]["notes"] = 'absent_terms: ["hot reload"]'  # present in the corpus
    test[0]["question"] = dev[0]["question"]  # test question leaked into dev
    root = write_dataset(tmp_path / "ds", dev, test)
    joined = "\n".join(
        check_dataset(*corpus, version="tiny", root=root, expected_sizes=SIZES).errors
    )
    assert "dev-004: excerpt 'Center lets its child' is not inside section" in joined
    assert "dev-005: absent term 'hot reload' found in 1 docs" in joined
    assert "test-001: test question also present in dev" in joined


def test_check_catches_distribution_commit_and_language(tmp_path, corpus):
    dev, test = tiny_rows()
    test[1]["language"] = "ru"
    dev[1]["language"] = "ru"
    dev.append(make_item("dev", 9, "lookup", "en"))
    test[0]["corpus_commit"] = "d" * 40
    root = write_dataset(tmp_path / "ds", dev, test)
    joined = "\n".join(
        check_dataset(*corpus, version="tiny", root=root, expected_sizes=SIZES).errors
    )
    assert "dev: 2 items of type lookup, expected 1" in joined
    assert "type multi_doc: language split ru=2 en=0" in joined
    assert "test-001: corpus_commit" in joined


def test_schema_rules():
    ok = make_item("dev", 1, "multi_doc", "en")
    QAItem.model_validate(ok)
    with pytest.raises(ValueError, match="multi_doc needs"):
        QAItem.model_validate(
            {
                **ok,
                "gold_documents": ["ui/layout"],
                "gold_sections": ["ui/layout#center"],
                "supporting_excerpts": [{"section_id": "ui/layout#center", "text": "x"}],
            }
        )
    with pytest.raises(ValueError, match="unanswerable"):
        QAItem.model_validate(
            {**make_item("dev", 1, "unanswerable", "en"), "gold_documents": ["a"]}
        )
    with pytest.raises(ValueError, match="must start with"):
        QAItem.model_validate({**ok, "id": "test-001"})
    with pytest.raises(ValueError):
        QAItem.model_validate({**ok, "status": "approved"})


def test_split_guard_n03(tmp_path):
    root = write_dataset(tmp_path / "ds", *tiny_rows())
    with pytest.raises(SplitGuardError):
        load_split("test", version="tiny", root=root)
    assert len(load_split("test", version="tiny", root=root, final=True).items) == 5
    ds = load_split("dev", version="tiny", root=root)
    assert ds.sha256 and len(ds.items) == 5


def test_real_dataset_shape():
    """The committed flutter-qa-v1 parses and has 15/30 items; all are draft until checked."""
    dev = load_split("dev")
    test = load_split("test", final=True)
    assert len(dev.items) == 15 and len(test.items) == 30
    assert {i.status for i in dev.items + test.items} == {"draft"}
    assert not {i.id for i in dev.items} & {i.id for i in test.items}


def test_n04_corpus_include_cannot_match_evaluation_files():
    """No corpus include pattern of any config can pick up the dataset (answers never leak)."""
    eval_files = [p for p in (LAB1_DIR / "evaluation").rglob("*") if p.is_file()]
    assert any(p.suffix == ".jsonl" for p in eval_files)
    assert DATASETS_DIR.is_relative_to(LAB1_DIR / "evaluation")
    candidates = set()
    for p in eval_files:
        candidates |= {
            str(p.relative_to(REPO_ROOT)),
            str(p.relative_to(LAB1_DIR)),
            "lab1/evaluation/" + str(p.relative_to(LAB1_DIR / "evaluation")),
        }
    configs = sorted((LAB1_DIR / "configs").glob("*.yaml"))
    assert configs
    for cfg_path in configs:
        cfg = load_run_config(cfg_path)
        assert cfg.corpus.repo == "flutter/website", cfg_path.name
        for pattern in cfg.corpus.include:
            rx = glob_to_regex(pattern)
            leaked = [c for c in candidates if rx.match(c)]
            assert not leaked, (cfg_path.name, pattern, leaked)
