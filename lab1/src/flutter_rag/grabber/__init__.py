"""Incremental grabber: fetch Flutter docs from flutter/website.

One snapshot = one commit SHA. Change detection uses git blob SHAs from a single
tree listing, so only new/changed files are downloaded. Raw files are stored by
blob SHA (content-addressed), so re-runs never duplicate data.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from flutter_rag.errors import RagError, UpstreamError
from flutter_rag.grabber.github import GitHubClient, TreeEntry
from flutter_rag.grabber.manifest import (
    DocEntry,
    Manifest,
    ManifestDiff,
    diff_manifests,
    write_atomic,
)
from flutter_rag.preprocessing.frontmatter import split_front_matter
from flutter_rag.runconfig import (
    DOCS_CONTENT_ROOT,
    DOCS_INCLUDES_ROOT,
    DOCS_SITE_URL,
    CorpusConfig,
)

RENDER_RE = re.compile(r"\{%-?\s*render\s+[\"']([^\"']+)[\"']")
MAX_RENDER_DEPTH = 3


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Glob with `**` (any depth, including zero dirs), `*` and `?`, matched on full path."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def select_paths(paths: list[str], corpus: CorpusConfig) -> list[str]:
    inc = [glob_to_regex(p) for p in corpus.include]
    exc = [glob_to_regex(p) for p in corpus.exclude]
    selected = [
        p for p in paths if any(r.match(p) for r in inc) and not any(r.match(p) for r in exc)
    ]
    if corpus.pages:
        wanted = {DOCS_CONTENT_ROOT + p + ".md" for p in corpus.pages}
        missing = wanted - set(selected)
        if missing:
            raise RagError(f"pages not found or excluded in snapshot: {sorted(missing)}")
        selected = [p for p in selected if p in wanted]
    return sorted(selected)


def document_id_for(path: str) -> str:
    return path.removeprefix(DOCS_CONTENT_ROOT).removesuffix(".md")


def url_for(document_id: str) -> str:
    """content/<p>.md -> https://docs.flutter.dev/<p>; index.md -> its directory."""
    if document_id == "index":
        return DOCS_SITE_URL
    if document_id.endswith("/index"):
        document_id = document_id.removesuffix("/index")
    return DOCS_SITE_URL + document_id


@dataclass
class RawStore:
    root: Path

    def path(self, blob_sha: str) -> Path:
        return self.root / "blobs" / f"{blob_sha}.md"

    def has(self, blob_sha: str) -> bool:
        return self.path(blob_sha).exists()

    def read(self, blob_sha: str) -> str:
        return self.path(blob_sha).read_text(encoding="utf-8")

    def write(self, blob_sha: str, text: str) -> None:
        write_atomic(self.path(blob_sha), text)


@dataclass
class GrabResult:
    manifest: Manifest
    diff: ManifestDiff
    downloaded: int
    failed: list[str] = field(default_factory=list)
    github_requests: int = 0


def manifest_dir(data_dir: Path, config_id: str) -> Path:
    return data_dir / "manifests" / config_id


def load_latest_manifest(data_dir: Path, config_id: str) -> Manifest | None:
    p = manifest_dir(data_dir, config_id) / "latest.json"
    return Manifest.from_json(p.read_text()) if p.exists() else None


def _skip_reason(front: dict, rules: dict[str, object]) -> str | None:
    for key, value in rules.items():
        if front.get(key) == value:
            return f"front matter {key}: {value}"
    return None


def grab(
    corpus: CorpusConfig,
    config_id: str,
    data_dir: Path,
    client: GitHubClient,
) -> GrabResult:
    store = RawStore(data_dir / "raw")
    commit = client.resolve_commit(corpus.ref)
    tree = {e.path: e for e in client.list_tree(commit)}
    selected = select_paths(list(tree), corpus)

    downloaded = 0
    failed: list[str] = []

    def ensure(entries: list[TreeEntry]) -> None:
        nonlocal downloaded
        todo = [e for e in {e.blob_sha: e for e in entries}.values() if not store.has(e.blob_sha)]

        def fetch(e: TreeEntry) -> tuple[TreeEntry, str | Exception]:
            try:
                return e, client.fetch_raw(commit, e.path)
            except UpstreamError as exc:
                return e, exc

        with ThreadPoolExecutor(max_workers=corpus.download_concurrency) as pool:
            for entry, result in pool.map(fetch, todo):
                if isinstance(result, Exception):
                    failed.append(entry.path)
                else:
                    store.write(entry.blob_sha, result)
                    downloaded += 1

    ensure([tree[p] for p in selected])

    docs: dict[str, DocEntry] = {}
    for path in selected:
        entry = tree[path]
        doc_id = document_id_for(path)
        doc = DocEntry(doc_id, path, url_for(doc_id), entry.blob_sha)
        docs[doc_id] = doc
        if path in failed:
            doc.status, doc.reason = "failed", "download failed after retries"
            continue
        text = store.read(entry.blob_sha)
        front, _ = split_front_matter(text)
        reason = _skip_reason(front, corpus.skip_front_matter)
        if reason:
            doc.status, doc.reason = "skipped", reason
            continue
        # Resolve {% render %} fragments transitively (they live in _includes/).
        pending, depth = RENDER_RE.findall(text), 0
        while pending and depth < MAX_RENDER_DEPTH:
            entries = []
            for target in pending:
                inc_path = DOCS_INCLUDES_ROOT + target
                if inc_path in tree and inc_path not in doc.includes:
                    doc.includes[inc_path] = tree[inc_path].blob_sha
                    entries.append(tree[inc_path])
            ensure(entries)
            pending = [
                t
                for e in entries
                if store.has(e.blob_sha)
                for t in RENDER_RE.findall(store.read(e.blob_sha))
            ]
            depth += 1

    manifest = Manifest(
        repo=corpus.repo,
        commit_sha=commit,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        config_id=config_id,
        documents=docs,
    )
    previous = load_latest_manifest(data_dir, config_id)
    diff = diff_manifests(previous, manifest)
    if previous and previous.commit_sha == commit and previous.documents == docs:
        # Nothing changed: keep the existing manifest byte-for-byte (no churn in Git).
        return GrabResult(previous, diff, downloaded, failed, client.requests)
    mdir = manifest_dir(data_dir, config_id)
    write_atomic(mdir / f"{commit}.json", manifest.to_json())
    write_atomic(mdir / "latest.json", manifest.to_json())
    return GrabResult(manifest, diff, downloaded, failed, client.requests)
