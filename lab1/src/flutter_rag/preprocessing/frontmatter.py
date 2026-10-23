from __future__ import annotations

import re

import yaml

FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def split_front_matter(text: str) -> tuple[dict, str]:
    """Return (front matter dict, body). Invalid YAML yields an empty dict."""
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), text[m.end() :]
