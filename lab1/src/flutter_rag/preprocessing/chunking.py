"""Chunking with provenance (docs/architecture.md §4, D10; docs/contracts/stage05.md §2).

Strategies (``ChunkingConfig.strategy``):

- ``section`` (stage 03 behaviour): sections are delimited by Markdown headings and a chunk never
  crosses a heading. Blocks (paragraphs, lists, code) are packed up to ``max_tokens``. A fenced
  code block is never split while it is <= ``code_soft_cap_tokens``; a longer one is split on
  line boundaries and every piece is re-fenced with its language, flagged ``code_split``. Long
  prose blocks are split by sentences. Heading lines are not part of the chunk text (they are in
  the ``embed_text`` header).
- ``fixed`` (naive baseline): windows of ``max_tokens`` over the whole cleaned body, ignoring
  headings and code fences. Windows are cut on line boundaries; a single line longer than the
  window is cut on word boundaries (a single word longer than the window - on characters). The
  window start advances by ``max_tokens * (1 - overlap)`` tokens, rounded to the next line
  boundary (never past the end of the previous window, so no text is skipped).
  Decision: code pieces are NOT re-fenced. The chunk text is the verbatim slice of the body
  (only leading/trailing whitespace stripped), so non-overlapping windows concatenate back to the
  body. A window that holds only part of a fenced block is flagged ``code_split``; its text may
  contain an unbalanced fence - this is the property of the baseline being measured.
- ``paragraph``: paragraphs (blank-line separated; a whole fenced code block is one paragraph;
  every heading line is its own paragraph) are packed up to ``max_tokens`` and may cross headings.
  Heading lines are kept in the text (without ``{:...}`` attributes). A heading is never left
  dangling at the end of a chunk: trailing headings move to the next chunk, so a chunk may exceed
  ``max_tokens`` by the size of the headings attached to its first paragraph. A paragraph longer
  than ``max_tokens`` is split exactly like in ``section`` (code <= soft cap kept whole, longer
  code by lines with re-fencing + ``code_split``, prose by sentences).

For every strategy ``section_ids`` lists every section the chunk text overlaps, in order of
appearance, as ``"<document_id>#<anchor>"`` (``"<document_id>#"`` before the first heading).
A heading line belongs to the section it opens. Anchors come from one parser (`_scan`) for all
strategies: ``slugify``, explicit ``{:#id}``, duplicates ``-1``, ``-2``. ``section_path`` and
``anchor`` (and the ``embed_text`` header) are those of the first section of the chunk.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from flutter_rag.preprocessing.clean import split_fences
from flutter_rag.runconfig import ChunkingConfig

CHUNK_NAMESPACE = uuid.UUID("6f1c3c1e-6a39-4bfb-9a43-6f2b1f0c7d11")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
HEADING_ATTR_RE = re.compile(r"\s*\{:([^}]*)\}\s*$")  # {:#id} or {:.no_toc}
HEADING_ID_RE = re.compile(r"#([\w-]+)")
FENCE_CLOSE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
WORD_RE = re.compile(r"\s*\S+\s*")


def estimate_tokens(text: str) -> int:
    """Approximation used for budgets: ~4 characters per token (assumption A-2)."""
    return max(1, (len(text) + 3) // 4)


def slugify(heading: str) -> str:
    """docs.flutter.dev heading ids (checked against live pages on 2026-10-23):
    "Provider.of" -> "provider-of", "Step 1: Add X.xml" -> "step-1-add-x-xml"."""
    s = heading.lower().replace("`", "").replace(".", " ")
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s.strip())
    return s.strip("-")


def section_id(document_id: str, anchor: str | None) -> str:
    return f"{document_id}#{anchor or ''}"


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    strategy_id: str
    ordinal: int
    title: str
    url: str
    section_path: list[str]
    anchor: str | None
    text: str
    embed_text: str
    has_code: bool
    code_split: bool
    token_count: int
    content_hash: str
    # Every section the chunk text overlaps, as "<document_id>#<anchor>" ("<document_id>#" for
    # text before the first heading). Stable across strategies: gold labels of the evaluation
    # dataset use the same IDs (docs/contracts/stage05.md §2).
    section_ids: list[str] = field(default_factory=list)

    @property
    def section(self) -> str:
        return " > ".join(self.section_path)

    @property
    def source_url(self) -> str:
        return f"{self.url}#{self.anchor}" if self.anchor else self.url


@dataclass
class _Block:
    text: str
    is_code: bool
    code_split: bool = False


@dataclass
class _Section:
    path: list[str]
    anchor: str | None
    blocks: list[_Block] = field(default_factory=list)


@dataclass
class _Line:
    text: str
    sec: int  # index into the section list of _scan
    code: int | None  # index of the fenced block this line belongs to (fences included)


@dataclass
class _Para:
    text: str
    sec: int
    is_code: bool
    is_heading: bool = False
    code_split: bool = False


def _scan(body: str) -> tuple[list[_Section], list[_Line], list[_Para]]:
    """Single parser for all strategies: sections (index 0 = text before the first heading),
    every body line with its section and code block, and paragraphs (headings included)."""
    sections = [_Section([], None)]
    lines: list[_Line] = []
    paras: list[_Para] = []
    stack: list[tuple[int, str, str]] = []  # (level, heading text, anchor)
    seen_slugs: dict[str, int] = {}
    n_code = 0
    para: list[str] = []

    def flush() -> None:
        if any(x.strip() for x in para):
            paras.append(_Para("\n".join(para).strip(), len(sections) - 1, False))
        para.clear()

    for is_code, seg in split_fences(body):
        if is_code:
            flush()
            sec = len(sections) - 1
            paras.append(_Para(seg, sec, True))
            lines.extend(_Line(x, sec, n_code) for x in seg.split("\n"))
            n_code += 1
            continue
        for line in seg.split("\n"):
            m = HEADING_RE.match(line)
            if m:
                flush()
                level, text = len(m.group(1)), m.group(2)
                attr = HEADING_ATTR_RE.search(text)
                explicit = HEADING_ID_RE.search(attr.group(1)) if attr else None
                text = HEADING_ATTR_RE.sub("", text).strip()
                if explicit:
                    anchor = explicit.group(1)
                else:  # duplicate headings get -1, -2 ... like on the site
                    base = slugify(text)
                    n = seen_slugs.get(base, 0)
                    seen_slugs[base] = n + 1
                    anchor = base if n == 0 else f"{base}-{n}"
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text, anchor))
                sections.append(_Section([h for _, h, _ in stack], anchor))
                sec = len(sections) - 1
                paras.append(_Para(f"{m.group(1)} {text}", sec, False, is_heading=True))
                lines.append(_Line(line, sec, None))
                continue
            lines.append(_Line(line, len(sections) - 1, None))
            if not line.strip():
                flush()
            else:
                para.append(line)
        flush()
    return sections, lines, paras


def _parse_sections(body: str) -> list[_Section]:
    sections, _, paras = _scan(body)
    out = [_Section(list(s.path), s.anchor) for s in sections]
    for p in paras:
        if not p.is_heading:
            out[p.sec].blocks.append(_Block(p.text, p.is_code))
    return [s for s in out if s.blocks]


def document_section_ids(document_id: str, body: str) -> list[str]:
    """All section ids of a cleaned body (intro "<document_id>#" only if it has text)."""
    sections, lines, _ = _scan(body)
    used = {ln.sec for ln in lines if ln.text.strip()}
    return [section_id(document_id, s.anchor) for i, s in enumerate(sections) if i in used]


def _split_code(block: str, max_tokens: int) -> list[str]:
    lines = block.split("\n")
    opening, body = lines[0], lines[1:-1]
    closing = lines[-1] if FENCE_CLOSE_RE.match(lines[-1]) else "```"
    pieces, cur = [], []
    budget = max_tokens - estimate_tokens(opening + closing)
    for line in body:
        if cur and estimate_tokens("\n".join([*cur, line])) > budget:
            pieces.append(cur)
            cur = []
        cur.append(line)
    if cur:
        pieces.append(cur)
    return ["\n".join([opening, *p, closing]) for p in pieces]


def _split_prose(text: str, max_tokens: int) -> list[str]:
    units = re.split(r"(?<=[.!?])\s+|\n", text)
    pieces, cur = [], ""
    for u in units:
        candidate = f"{cur} {u}".strip() if cur else u
        if cur and estimate_tokens(candidate) > max_tokens:
            pieces.append(cur)
            cur = u
        else:
            cur = candidate
    if cur:
        pieces.append(cur)
    return pieces


def _split_long_line(line: str, max_chars: int) -> list[str]:
    """Cut a line into pieces of <= max_chars on word boundaries; "".join(pieces) == line."""
    pieces, cur = [], ""
    for m in WORD_RE.finditer(line):
        word = m.group(0)
        while len(word) > max_chars:  # a single word longer than the window
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(word[:max_chars])
            word = word[max_chars:]
        if cur and len(cur) + len(word) > max_chars:
            pieces.append(cur)
            cur = ""
        cur += word
    if cur:
        pieces.append(cur)
    return pieces


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def chunk_document(
    *,
    document_id: str,
    title: str,
    url: str,
    body: str,
    cfg: ChunkingConfig,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    strategy_id = cfg.strategy_id

    def add(
        path: list[str],
        anchor: str | None,
        text: str,
        *,
        has_code: bool,
        code_split: bool,
        section_ids: list[str],
    ) -> None:
        text = text.strip()
        if not text:
            return
        header = f"Page: {title}" + (f" > {' > '.join(path)}" if path else "")
        embed_text = f"{header}\n\n{text}"
        ordinal = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=str(uuid.uuid5(CHUNK_NAMESPACE, f"{strategy_id}|{document_id}|{ordinal}")),
                document_id=document_id,
                strategy_id=strategy_id,
                ordinal=ordinal,
                title=title,
                url=url,
                section_path=list(path),
                anchor=anchor,
                text=text,
                embed_text=embed_text,
                has_code=has_code,
                code_split=code_split,
                token_count=estimate_tokens(embed_text),
                content_hash=hashlib.sha256(embed_text.encode()).hexdigest(),
                section_ids=section_ids,
            )
        )

    if cfg.strategy == "section":
        _chunk_sections(document_id, body, cfg, add)
    elif cfg.strategy == "fixed":
        _chunk_fixed(document_id, body, cfg, add)
    elif cfg.strategy == "paragraph":
        _chunk_paragraphs(document_id, body, cfg, add)
    else:  # pragma: no cover - ChunkingConfig validates the literal
        raise ValueError(f"unknown chunking strategy {cfg.strategy!r}")
    return chunks


def _chunk_sections(document_id, body, cfg: ChunkingConfig, add) -> None:
    def emit(section: _Section, blocks: list[_Block]) -> None:
        add(
            section.path,
            section.anchor,
            "\n\n".join(b.text for b in blocks),
            has_code=any(b.is_code for b in blocks),
            code_split=any(b.code_split for b in blocks),
            section_ids=[section_id(document_id, section.anchor)],
        )

    for section in _parse_sections(body):
        cur: list[_Block] = []
        cur_tokens = 0
        for block in section.blocks:
            tokens = estimate_tokens(block.text)
            if tokens > cfg.max_tokens:
                if cur:
                    emit(section, cur)
                    cur, cur_tokens = [], 0
                if block.is_code and tokens <= cfg.code_soft_cap_tokens:
                    emit(section, [block])
                elif block.is_code:
                    for piece in _split_code(block.text, cfg.max_tokens):
                        emit(section, [_Block(piece, True, code_split=True)])
                else:
                    for piece in _split_prose(block.text, cfg.max_tokens):
                        emit(section, [_Block(piece, False)])
                continue
            if cur and cur_tokens + tokens > cfg.max_tokens:
                emit(section, cur)
                cur, cur_tokens = [], 0
            cur.append(block)
            cur_tokens += tokens
        if cur:
            emit(section, cur)


@dataclass
class _Unit:
    text: str
    joiner: str  # "\n" before a new line, "" before the continuation of a cut line
    offset: int  # character offset of `text` in the body
    line: _Line


def _chunk_fixed(document_id, body, cfg: ChunkingConfig, add) -> None:
    sections, lines, _ = _scan(body)
    max_chars = cfg.max_tokens * 4  # estimate_tokens(t) <= max_tokens  <=>  len(t) <= max_chars
    step_chars = max(1, int(cfg.max_tokens * (1 - cfg.overlap))) * 4

    units: list[_Unit] = []
    offset = 0
    for ln in lines:
        pieces = _split_long_line(ln.text, max_chars) if len(ln.text) > max_chars else [ln.text]
        pos = offset
        for i, piece in enumerate(pieces):
            units.append(_Unit(piece, "\n" if i == 0 else "", pos, ln))
            pos += len(piece)
        offset += len(ln.text) + 1
    if units:
        units[0].joiner = ""

    block_span: dict[int, tuple[int, int]] = {}  # code block -> (first unit, last unit)
    for i, u in enumerate(units):
        if u.line.code is not None:
            first, _ = block_span.get(u.line.code, (i, i))
            block_span[u.line.code] = (first, i)

    s, n = 0, len(units)
    while s < n:
        e, length = s + 1, len(units[s].text)
        while e < n and length + len(units[e].joiner) + len(units[e].text) <= max_chars:
            length += len(units[e].joiner) + len(units[e].text)
            e += 1
        window = units[s:e]
        text = units[s].text + "".join(u.joiner + u.text for u in window[1:])
        content = [u for u in window if u.text.strip()]
        if content:
            first = sections[content[0].line.sec]
            blocks = _unique([u.line.code for u in content if u.line.code is not None])
            add(
                first.path,
                first.anchor,
                text,
                has_code=bool(blocks),
                code_split=any(block_span[b][0] < s or block_span[b][1] >= e for b in blocks),
                section_ids=_unique(
                    [section_id(document_id, sections[u.line.sec].anchor) for u in content]
                ),
            )
        if e >= n:
            break
        target = units[s].offset + step_chars
        s = next((i for i in range(s + 1, e) if units[i].offset >= target), e)


def _chunk_paragraphs(document_id, body, cfg: ChunkingConfig, add) -> None:
    sections, _, paras = _scan(body)

    def emit(group: list[_Para]) -> None:
        first = sections[group[0].sec]
        add(
            first.path,
            first.anchor,
            "\n\n".join(p.text for p in group),
            has_code=any(p.is_code for p in group),
            code_split=any(p.code_split for p in group),
            section_ids=_unique([section_id(document_id, sections[p.sec].anchor) for p in group]),
        )

    def take_trailing_headings(group: list[_Para]) -> list[_Para]:
        k = len(group)
        while k > 0 and group[k - 1].is_heading:
            k -= 1
        lead = group[k:]
        del group[k:]
        return lead

    cur: list[_Para] = []
    for p in paras:
        tokens = estimate_tokens(p.text)
        if tokens > cfg.max_tokens and not p.is_heading:
            lead = take_trailing_headings(cur)
            if cur:
                emit(cur)
            if p.is_code and tokens <= cfg.code_soft_cap_tokens:
                pieces = [p]
            elif p.is_code:
                pieces = [
                    _Para(x, p.sec, True, code_split=True)
                    for x in _split_code(p.text, cfg.max_tokens)
                ]
            else:
                pieces = [_Para(x, p.sec, False) for x in _split_prose(p.text, cfg.max_tokens)]
            emit([*lead, pieces[0]])
            for piece in pieces[1:]:
                emit([piece])
            cur = []
            continue
        if cur and sum(estimate_tokens(x.text) for x in cur) + tokens > cfg.max_tokens:
            lead = take_trailing_headings(cur)
            if cur:
                emit(cur)
            cur = lead  # headings stay with the paragraph they introduce
        cur.append(p)
    if cur:
        emit(cur)
