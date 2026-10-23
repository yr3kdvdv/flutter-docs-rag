"""Section-aware chunking with provenance (docs/architecture.md §4, D10).

- Sections are delimited by Markdown headings; a chunk never crosses a heading.
- Blocks (paragraphs, lists, code) are packed up to `max_tokens`.
- A fenced code block is never split while it is <= `code_soft_cap_tokens`;
  a longer one is split on line boundaries and every piece is re-fenced with its
  language, flagged `code_split`.
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


def _parse_sections(body: str) -> list[_Section]:
    sections = [_Section([], None)]
    stack: list[tuple[int, str, str]] = []  # (level, heading text, anchor)
    seen_slugs: dict[str, int] = {}
    for is_code, seg in split_fences(body):
        if is_code:
            sections[-1].blocks.append(_Block(seg, True))
            continue
        para: list[str] = []
        for line in seg.split("\n"):
            m = HEADING_RE.match(line)
            if m:
                _flush_para(sections[-1], para)
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
            elif not line.strip():
                _flush_para(sections[-1], para)
            else:
                para.append(line)
        _flush_para(sections[-1], para)
    return [s for s in sections if s.blocks]


def _flush_para(section: _Section, para: list[str]) -> None:
    if any(x.strip() for x in para):
        section.blocks.append(_Block("\n".join(para).strip(), False))
    para.clear()


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

    def emit(section: _Section, blocks: list[_Block]) -> None:
        text = "\n\n".join(b.text for b in blocks).strip()
        if not text:
            return
        path = section.path
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
                anchor=section.anchor,
                text=text,
                embed_text=embed_text,
                has_code=any(b.is_code for b in blocks),
                code_split=any(b.code_split for b in blocks),
                token_count=estimate_tokens(embed_text),
                content_hash=hashlib.sha256(embed_text.encode()).hexdigest(),
            )
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
    return chunks
