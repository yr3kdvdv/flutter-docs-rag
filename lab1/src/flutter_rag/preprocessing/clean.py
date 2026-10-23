"""Clean Flutter-website Markdown into plain Markdown suitable for chunking.

Rules (docs/architecture.md §3.1 step 6):
- fenced code blocks are copied verbatim (only prose is rewritten);
- {% render %} fragments are inlined, {% comment %} blocks dropped, other Liquid tags removed;
- <Tab name="X"> becomes a "X:" line so code samples in different languages stay labelled;
- HTML tags, images, embeds and code-excerpt directives are removed, link text is kept;
- admonitions (:::note) become plain labelled paragraphs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from flutter_rag.preprocessing.frontmatter import split_front_matter

FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
RENDER_TAG_RE = re.compile(r"\{%-?\s*render\s+[\"']([^\"']+)[\"'][^%]*-?%\}")
COMMENT_RE = re.compile(r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", re.S)
LIQUID_TAG_RE = re.compile(r"\{%-?.*?-?%\}", re.S)
LIQUID_VAR_RE = re.compile(r"\{\{.*?\}\}")
CODE_EXCERPT_RE = re.compile(r"<\?code-excerpt.*?\?>", re.S)
TAB_OPEN_RE = re.compile(r"<Tab\s+name=[\"']([^\"']+)[\"'][^>]*>")
COMPONENT_RE = re.compile(r"</?(?:Tabs|Tab|YouTubeEmbed|DashImage|SampleAppPage)\b[^>]*>")
HTML_TAG_RE = re.compile(r"</?[a-z][a-z0-9-]*(?:\s[^<>]*)?/?>")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
REF_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
REF_DEF_RE = re.compile(r"^\s*\[[^\]]+\]:\s*\S+.*$", re.M)
ADMONITION_OPEN_RE = re.compile(r"^:::\s*([\w-]+)\s*(.*)$")
KRAMDOWN_ATTR_LINE_RE = re.compile(r"^\s*\{:[^}]*\}\s*$")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")

ADMONITION_LABELS = {
    "note": "Note",
    "tip": "Tip",
    "warning": "Warning",
    "important": "Important",
    "version-note": "Version note",
    "secondary": "",
}


@dataclass
class CleanDoc:
    title: str
    description: str
    body: str
    missing_renders: list[str]


IncludeResolver = Callable[[str], str | None]


def inline_renders(text: str, resolve: IncludeResolver, depth: int = 0) -> tuple[str, list[str]]:
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        target = m.group(1)
        included = resolve(target) if depth < 3 else None
        if included is None:
            missing.append(target)
            return ""
        _, body = split_front_matter(included)
        body, nested = inline_renders(body, resolve, depth + 1)
        missing.extend(nested)
        return body

    return RENDER_TAG_RE.sub(repl, text), missing


def _clean_prose_line(line: str) -> str:
    # Links first: their text is often inline code, e.g. [`Widget`](url).
    line = IMAGE_RE.sub("", line)
    line = INLINE_LINK_RE.sub(r"\1", line)
    line = REF_LINK_RE.sub(r"\1", line)
    # Then protect inline code spans: rewrite only the text between them.
    parts, last = [], 0
    for m in INLINE_CODE_RE.finditer(line):
        parts.append(_clean_text(line[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_clean_text(line[last:]))
    return "".join(parts)


def _clean_text(s: str) -> str:
    s = LIQUID_VAR_RE.sub("", s)
    s = TAB_OPEN_RE.sub(lambda m: f"\n{m.group(1)}:\n", s)
    s = COMPONENT_RE.sub("", s)
    s = HTML_TAG_RE.sub("", s)
    return s


def _clean_prose(block: str) -> str:
    block = CODE_EXCERPT_RE.sub("", block)
    block = HTML_COMMENT_RE.sub("", block)
    block = LIQUID_TAG_RE.sub("", block)
    block = REF_DEF_RE.sub("", block)
    out = []
    for line in block.split("\n"):
        if KRAMDOWN_ATTR_LINE_RE.match(line):
            continue
        m = ADMONITION_OPEN_RE.match(line.strip())
        if m:
            label = ADMONITION_LABELS.get(m.group(1), m.group(1).capitalize())
            heading = " ".join(x for x in (label, m.group(2).strip()) if x)
            out.append(f"{heading}:" if heading else "")
            continue
        if line.strip() == ":::":
            out.append("")
            continue
        out.append(_clean_prose_line(line).rstrip())
    return "\n".join(out)


def split_fences(text: str) -> list[tuple[bool, str]]:
    """Split into (is_code, text) segments; code segments include their fences."""
    segments: list[tuple[bool, str]] = []
    buf: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if fence is None and m:
            if buf:
                segments.append((False, "\n".join(buf)))
            buf, fence = [line], m.group(2)
        elif fence is not None:
            buf.append(line)
            if (
                m
                and m.group(2).startswith(fence[0])
                and len(m.group(2)) >= len(fence)
                and not m.group(3).strip()
            ):
                segments.append((True, "\n".join(buf)))
                buf, fence = [], None
        else:
            buf.append(line)
    if buf:
        segments.append((fence is not None, "\n".join(buf)))
    return segments


def clean_markdown(raw: str, resolve: IncludeResolver) -> CleanDoc:
    front, body = split_front_matter(raw)
    body = COMMENT_RE.sub("", body)
    body, missing = inline_renders(body, resolve)
    pieces = []
    for is_code, seg in split_fences(body):
        if is_code:
            lines = seg.split("\n")
            indent = len(lines[0]) - len(lines[0].lstrip())
            pieces.append("\n".join(ln[indent:] if ln[:indent].isspace() else ln for ln in lines))
        else:
            pieces.append(_clean_prose(seg))
    text = unicodedata.normalize("NFC", "\n".join(pieces))
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return CleanDoc(
        title=str(front.get("title", "")).strip(),
        description=str(front.get("description", "")).strip(),
        body=text,
        missing_renders=missing,
    )
