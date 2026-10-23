"""Corpus manifest: which file of which commit is in the snapshot, and how it changed."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

DocStatus = Literal["ok", "skipped", "failed"]


@dataclass
class DocEntry:
    document_id: str  # path under the content root without ".md", e.g. "ui/layout/constraints"
    path: str  # full repo path
    url: str
    blob_sha: str
    status: DocStatus = "ok"
    reason: str | None = None  # why skipped/failed
    includes: dict[str, str] = field(default_factory=dict)  # render target path -> blob sha


@dataclass
class Manifest:
    repo: str
    commit_sha: str
    created_at: str
    config_id: str
    documents: dict[str, DocEntry]

    def to_json(self) -> str:
        data = asdict(self)
        data["documents"] = {k: asdict(v) for k, v in sorted(self.documents.items())}
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        data = json.loads(text)
        data["documents"] = {k: DocEntry(**v) for k, v in data["documents"].items()}
        return cls(**data)

    def version_key(self, document_id: str) -> str:
        """Changes when the page or any fragment it renders changes."""
        doc = self.documents[document_id]
        parts = [doc.blob_sha, *(f"{p}={s}" for p, s in sorted(doc.includes.items()))]
        return "|".join(parts)


@dataclass
class ManifestDiff:
    added: list[str]
    modified: list[str]
    deleted: list[str]
    unchanged: list[str]


def diff_manifests(old: Manifest | None, new: Manifest) -> ManifestDiff:
    new_ok = {k for k, v in new.documents.items() if v.status == "ok"}
    old_ok = {k for k, v in old.documents.items() if v.status == "ok"} if old else set()
    added = sorted(new_ok - old_ok)
    deleted = sorted(old_ok - new_ok)
    both = new_ok & old_ok
    modified = sorted(k for k in both if old.version_key(k) != new.version_key(k))
    unchanged = sorted(both - set(modified))
    return ManifestDiff(added, modified, deleted, unchanged)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.replace(tmp, path)
