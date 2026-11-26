"""fixed and paragraph strategies, section_ids for all strategies (contracts/stage05.md §2)."""

import re

import pytest

from flutter_rag.preprocessing.chunking import (
    chunk_document,
    document_section_ids,
    estimate_tokens,
)
from flutter_rag.runconfig import ChunkingConfig


def _prose(n: int, tag: str) -> str:
    return "\n".join(f"{tag} line {i} has some words to fill the window nicely." for i in range(n))


BODY = (
    "Intro paragraph before any heading.\n\n"
    "## Alpha\n\n"
    f"{_prose(30, 'alpha')}\n\n"
    "### Beta {:#beta-id}\n\n"
    "Short beta paragraph.\n\n"
    "```dart\nvoid main() {\n  runApp(const MyApp());\n}\n```\n\n"
    "## Alpha\n\n"
    f"{_prose(30, 'gamma')}\n"
)


def _chunks(body: str = BODY, **cfg):
    return chunk_document(
        document_id="doc", title="T", url="u", body=body, cfg=ChunkingConfig(**cfg)
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text)


@pytest.mark.parametrize("max_tokens", [64, 128, 256])
def test_fixed_windows_respect_size_and_lose_no_text(max_tokens):
    chunks = _chunks(strategy="fixed", max_tokens=max_tokens)
    assert len(chunks) > 1
    for c in chunks:
        assert estimate_tokens(c.text) <= max_tokens
    # overlap 0: windows are consecutive, so they concatenate back to the body
    assert _norm("".join(c.text for c in chunks)) == _norm(BODY)


def test_fixed_cuts_on_line_boundaries_ignoring_headings():
    chunks = _chunks(strategy="fixed", max_tokens=128)
    body_lines = set(BODY.split("\n"))
    for c in chunks:
        assert all(line in body_lines for line in c.text.split("\n"))
    # structure is ignored: some window holds a heading line after other text
    assert any("\n## Alpha" in c.text or "\n### Beta" in c.text for c in chunks)


def test_fixed_overlap_step():
    plain = _chunks(strategy="fixed", max_tokens=128)
    over = _chunks(strategy="fixed", max_tokens=128, overlap=0.25)
    assert len(over) > len(plain)
    step_chars = int(128 * 0.75) * 4
    starts = [BODY.index(c.text) for c in over]
    assert starts == sorted(starts)
    for prev, nxt, c in zip(starts, starts[1:], over, strict=False):
        assert nxt >= prev + step_chars  # advanced by at least the step ...
        assert nxt <= prev + len(c.text) + 2  # ... and never past the end of the window
    for a, b in zip(over, over[1:], strict=False):
        assert set(a.text.split("\n")) & set(b.text.split("\n"))  # windows really overlap


def test_fixed_long_line_cut_on_words_and_reassembles():
    line = " ".join(f"word{i}" for i in range(400))  # ~2400 chars on one line
    body = f"## Long\n\n{line}\n"
    chunks = _chunks(body, strategy="fixed", max_tokens=64)
    assert len(chunks) > 5
    for c in chunks:
        assert estimate_tokens(c.text) <= 64
        assert not re.search(r"word\d+word", c.text)
    assert _norm("".join(c.text for c in chunks)) == _norm(body)
    assert all(c.section_ids == ["doc#long"] for c in chunks)


def test_fixed_marks_cut_code_and_keeps_it_verbatim():
    code = "\n".join(f"  final v{i} = compute({i}); // padding" for i in range(60))
    body = f"Text.\n\n```dart\n{code}\n```\n\nAfter.\n"
    chunks = _chunks(body, strategy="fixed", max_tokens=128)
    with_code = [c for c in chunks if c.has_code]
    assert len(with_code) > 1 and all(c.code_split for c in with_code)
    assert "".join(c.text for c in chunks).count("final v") == 60
    assert sum(c.text.count("```") for c in chunks) == 2  # not re-fenced (naive baseline)
    small = _chunks(body, strategy="fixed", max_tokens=1024)
    assert len(small) == 1 and small[0].has_code and not small[0].code_split


def test_section_ids_for_chunk_spanning_several_headings():
    body = "Intro text.\n\n## One\n\nA.\n\n### Two\n\nB.\n\n## One\n\nC.\n"
    for strategy in ("fixed", "paragraph"):
        (chunk,) = _chunks(body, strategy=strategy, max_tokens=512)
        assert chunk.section_ids == ["doc#", "doc#one", "doc#two", "doc#one-1"], strategy
        assert chunk.section_path == [] and chunk.anchor is None
        assert chunk.embed_text.startswith("Page: T\n\n")
    assert document_section_ids("doc", body) == ["doc#", "doc#one", "doc#two", "doc#one-1"]


def test_section_ids_first_section_drives_path_and_header():
    chunks = _chunks(strategy="paragraph", max_tokens=512)
    spanning = [c for c in chunks if len(c.section_ids) > 1]
    assert spanning
    for c in chunks:
        assert c.section_ids[0] == f"doc#{c.anchor or ''}"
        header = "Page: T" + (f" > {c.section}" if c.section_path else "")
        assert c.embed_text == f"{header}\n\n{c.text}"
    beta = [c for c in chunks if "doc#beta-id" in c.section_ids]
    assert beta and all("{:" not in c.text for c in beta)


def test_intro_section_id_and_section_strategy_has_one_id():
    chunks = _chunks(strategy="section", max_tokens=128)
    assert chunks[0].section_ids == ["doc#"]
    assert all(len(c.section_ids) == 1 for c in chunks)
    assert all(c.section_ids == [f"doc#{c.anchor or ''}"] for c in chunks)
    ids = {s for c in chunks for s in c.section_ids}
    assert ids == {"doc#", "doc#alpha", "doc#beta-id", "doc#alpha-1"}
    for strategy in ("fixed", "paragraph"):
        other = {s for c in _chunks(strategy=strategy, max_tokens=128) for s in c.section_ids}
        assert other == ids, strategy  # same ids, whatever the strategy


def test_heading_inside_code_is_not_a_section():
    body = "## Real\n\n```bash\n# not a heading\necho hi\n```\n"
    for strategy in ("section", "fixed", "paragraph"):
        (chunk,) = _chunks(body, strategy=strategy, max_tokens=512)
        assert chunk.section_ids == ["doc#real"], strategy


def test_paragraph_keeps_short_paragraphs_and_code_whole():
    paras = [f"Paragraph {i}. " + "Some filler words here. " * 8 for i in range(12)]
    code = "```dart\n" + "\n".join(f"print({i});" for i in range(15)) + "\n```"
    body = "\n\n".join([*paras[:6], code, *paras[6:]]) + "\n"
    chunks = _chunks(body, strategy="paragraph", max_tokens=128)
    assert len(chunks) > 3
    pieces = [x for c in chunks for x in c.text.split("\n\n")]
    assert pieces == [p.strip() for p in [*paras[:6], code, *paras[6:]]]
    (with_code,) = [c for c in chunks if c.has_code]
    assert code in with_code.text and not with_code.code_split
    for c in chunks:
        assert estimate_tokens(c.text) <= 128 + 2  # "\n\n" separators are not budgeted


def test_paragraph_does_not_end_on_a_dangling_heading():
    filler = "Filler sentence for the budget. " * 12
    body = f"{filler}\n\n{filler}\n\n## Next\n\n{filler}\n"
    chunks = _chunks(body, strategy="paragraph", max_tokens=200)
    for c in chunks:
        assert not c.text.rstrip().endswith("## Next")
    nxt = [c for c in chunks if "## Next" in c.text]
    assert nxt and nxt[0].text.startswith("## Next\n\n") and nxt[0].anchor == "next"


def test_paragraph_long_code_is_split_and_refenced():
    code = "\n".join(f"  final value{i} = compute({i}); // padding text" for i in range(60))
    body = f"## Code\n\nIntro.\n\n```dart\n{code}\n```\n\nOutro.\n"
    chunks = _chunks(body, strategy="paragraph", max_tokens=200, code_soft_cap_tokens=300)
    split = [c for c in chunks if c.code_split]
    assert len(split) > 1
    for c in split:
        fenced = c.text[c.text.index("```dart") :]
        assert fenced.startswith("```dart\n") and fenced.endswith("\n```")
        assert c.section_ids == ["doc#code"]
    assert "".join(c.text for c in chunks).count("final value") == 60
    # under the soft cap the block stays whole even above max_tokens (same rule as section)
    whole = _chunks(body, strategy="paragraph", max_tokens=200, code_soft_cap_tokens=1024)
    assert not any(c.code_split for c in whole)
    assert any(f"```dart\n{code}\n```" in c.text for c in whole)


def test_paragraph_long_prose_split_by_sentences():
    long = " ".join(f"Sentence number {i} is here." for i in range(120))
    chunks = _chunks(f"## P\n\n{long}\n", strategy="paragraph", max_tokens=100)
    assert len(chunks) > 3
    assert all(c.text.rstrip().endswith(".") for c in chunks)
    assert _norm("".join(c.text for c in chunks)) == _norm(f"## P{long}")


@pytest.mark.parametrize(
    "cfg",
    [
        {"strategy": "section", "max_tokens": 128},
        {"strategy": "fixed", "max_tokens": 128},
        {"strategy": "fixed", "max_tokens": 128, "overlap": 0.15},
        {"strategy": "paragraph", "max_tokens": 128},
    ],
)
def test_all_strategies_are_deterministic(cfg):
    a, b = _chunks(**cfg), _chunks(**cfg)
    assert [(c.chunk_id, c.content_hash, c.section_ids) for c in a] == [
        (c.chunk_id, c.content_hash, c.section_ids) for c in b
    ]
    strategy_id = ChunkingConfig(**cfg).strategy_id
    assert all(c.strategy_id == strategy_id for c in a)
    assert [c.ordinal for c in a] == list(range(len(a)))
    assert all(c.token_count == estimate_tokens(c.embed_text) for c in a)
    assert len({c.chunk_id for c in a}) == len(a)


def test_empty_body_gives_no_chunks():
    for strategy in ("section", "fixed", "paragraph"):
        assert _chunks("\n\n", strategy=strategy, max_tokens=128) == []
