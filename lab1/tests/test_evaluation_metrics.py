"""Evaluation metrics on hand-computed examples (pure functions, no providers)."""

import pytest

from flutter_rag.evaluation import metrics as M


def row(doc, *sections, cid=None):
    return {
        "document_id": doc,
        "section_ids": list(sections),
        "chunk_id": cid or f"{doc}|{sections}",
    }


# gold: a#x and b#y (docs a, b). Ranked list of 5:
#   1 c#z      no
#   2 a#x      section hit (a#x), doc hit (a)
#   3 a#w      doc hit only
#   4 b#q,b#y  section hit (b#y), doc hit (b)
#   5 d#       no
RANKED = [row("c", "c#z"), row("a", "a#x"), row("a", "a#w"), row("b", "b#q", "b#y"), row("d", "d#")]
GOLD_S, GOLD_D = ["a#x", "b#y"], ["a", "b"]


def test_section_level_by_hand():
    m = M.retrieval_item_metrics(RANKED, GOLD_S, GOLD_D)["section"]
    assert m["hit@1"] == 0 and m["hit@3"] == 1
    assert m["recall@1"] == 0 and m["recall@3"] == 0.5 and m["recall@5"] == 1.0
    assert m["precision@1"] == 0 and m["precision@3"] == pytest.approx(1 / 3)
    assert m["precision@5"] == pytest.approx(2 / 5)
    assert m["precision@20"] == pytest.approx(2 / 20)  # denominator is K, not list length
    assert m["mrr"] == 0.5 and m["mrr@1"] == 0 and m["mrr@3"] == 0.5
    assert m["first_rank"] == 2


def test_document_level_by_hand():
    m = M.retrieval_item_metrics(RANKED, GOLD_S, GOLD_D)["document"]
    assert m["hit@1"] == 0 and m["hit@3"] == 1
    assert m["recall@3"] == 0.5 and m["recall@5"] == 1.0
    assert m["precision@5"] == pytest.approx(3 / 5)
    assert m["mrr"] == 0.5


def test_no_match_and_empty_list():
    m = M.retrieval_item_metrics([row("z", "z#")], ["a#x"], ["a"])
    assert m["section"]["mrr"] == 0 and m["section"]["hit@20"] == 0
    e = M.retrieval_item_metrics([], ["a#x"], ["a"])
    assert e["document"]["recall@5"] == 0 and e["document"]["precision@5"] == 0
    with pytest.raises(ValueError):
        M.retrieval_item_metrics(RANKED, [], [])


def test_aggregate_reports_absolute_numbers():
    a = M.retrieval_item_metrics(RANKED, GOLD_S, GOLD_D)
    b = M.retrieval_item_metrics([row("a", "a#x")], ["a#x"], ["a"])
    agg = M.aggregate_retrieval([a, b])
    s = agg["section"]
    assert s["hit@1"] == {"k": 1, "n": 2, "rate": 0.5}
    assert s["recall@5"]["micro"] == {"k": 3, "n": 3, "rate": 1.0}
    assert s["recall@3"]["micro"]["k"] == 2  # item a: 1 of 2, item b: 1 of 1
    assert s["recall@3"]["macro"] == pytest.approx((0.5 + 1.0) / 2)
    assert s["mrr"] == pytest.approx((0.5 + 1.0) / 2)


def test_refusal_and_upstream_error_are_separate():
    assert M.refusal_correct(True, "answered") is True
    assert M.refusal_correct(True, "insufficient_context") is False
    assert M.refusal_correct(False, "insufficient_context") is True
    assert M.refusal_correct(False, "answered") is False
    assert M.refusal_correct(True, "upstream_error") is None


def test_citations_must_include_and_code():
    c = M.citation_matches([RANKED[1]["chunk_id"], RANKED[2]["chunk_id"]], RANKED, GOLD_S, GOLD_D)
    assert c == {"cited": 2, "gold_section": 1, "gold_document": 2}
    assert M.must_include_found(
        "Use usePathUrlStrategy() before runApp", ["usepathurlstrategy", "base href"]
    ) == [True, False]
    assert M.code_present("call\n  usePathUrlStrategy( );", "usePathUrlStrategy();") is True
    assert M.code_present("nothing", "usePathUrlStrategy();") is False
    assert M.code_present("x", None) is None


def test_aggregate_generation_counts():
    def g(status, answerable, refusal, cited=0, sec=0, must=(), code=None, judge=None):
        return {
            "status": status,
            "answerable": answerable,
            "refusal_correct": refusal,
            "citations": {"cited": cited, "gold_section": sec, "gold_document": sec},
            "must_include": list(must),
            "code_present": code,
            "judge": judge,
        }

    rows = [
        g(
            "answered",
            True,
            True,
            cited=2,
            sec=1,
            must=[True, False],
            code=True,
            judge={"correctness": 4, "faithfulness": 5},
        ),
        g("insufficient_context", True, False, must=[False]),
        g("insufficient_context", False, True),
        g("answered", False, False, judge={"correctness": 1, "faithfulness": 1}),
        {"status": "upstream_error", "answerable": True},
    ]
    out = M.aggregate_generation(rows)
    assert out["upstream_error"] == {"k": 1, "n": 5}
    assert (
        out["refusal_accuracy_answerable"]["k"] == 1
        and out["refusal_accuracy_answerable"]["n"] == 2
    )
    assert (
        out["refusal_accuracy_unanswerable"]["k"] == 1
        and out["refusal_accuracy_unanswerable"]["n"] == 2
    )
    assert (
        out["citation_precision_section"]["k"] == 1 and out["citation_precision_section"]["n"] == 2
    )
    assert out["must_include_terms"]["k"] == 1 and out["must_include_terms"]["n"] == 3
    assert out["must_include_all"]["k"] == 0
    assert out["expected_code_present"] == {"k": 1, "n": 1, "rate": 1.0}
    assert (
        out["judge_correctness"]["mean"] == 4 and out["judge_correctness"]["distribution"]["4"] == 1
    )
    assert out["judge_correctness"]["n"] == 1
