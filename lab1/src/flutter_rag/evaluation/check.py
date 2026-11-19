"""`flutter-rag dataset-check`: validate the dataset against the corpus snapshot (§5.1).

Checks: schema of every row, 15/30 split sizes and 3/6 items per type, ru/en balance per type,
unique ids, no test question repeated in dev, corpus commit == manifest commit, gold documents
exist (status ok), every gold section is a real section id of the cleaned document, every
supporting excerpt is a verbatim substring of the cleaned text, and for unanswerable items the
`absent_terms` from notes really have no hit in any cleaned ok document.

Pages are cleaned exactly like `pipeline.ingest` (same include resolver over manifest includes).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from flutter_rag.evaluation.dataset import (
    DATASETS_DIR,
    DEFAULT_DATASET,
    PER_TYPE,
    QUESTION_TYPES,
    QAItem,
    dataset_dir,
    file_sha256,
    parse_lines,
)
from flutter_rag.grabber import RawStore
from flutter_rag.grabber.manifest import Manifest
from flutter_rag.preprocessing.chunking import _scan, document_section_ids
from flutter_rag.preprocessing.chunking import section_id as make_section_id
from flutter_rag.preprocessing.clean import CleanDoc, clean_markdown
from flutter_rag.runconfig import DOCS_INCLUDES_ROOT


def clean_document(manifest: Manifest, raw: RawStore, document_id: str) -> CleanDoc:
    """The cleaned page exactly as ingest indexes it (resolver copied from pipeline.ingest)."""
    doc = manifest.documents[document_id]

    def resolve(target: str) -> str | None:
        sha = doc.includes.get(DOCS_INCLUDES_ROOT + target)
        return raw.read(sha) if sha and raw.has(sha) else None

    return clean_markdown(raw.read(doc.blob_sha), resolve)


@dataclass
class CheckReport:
    dataset: str
    manifest_commit: str
    files: dict[str, str] = field(default_factory=dict)  # split -> sha256
    counts: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    checked_excerpts: int = 0
    checked_sections: int = 0
    checked_absent_terms: int = 0
    statuses: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _norm(question: str) -> str:
    return " ".join(question.lower().split())


def check_dataset(
    manifest: Manifest,
    raw: RawStore,
    *,
    version: str = DEFAULT_DATASET,
    root: Path = DATASETS_DIR,
    expected_sizes: dict[str, int] | None = None,
) -> CheckReport:
    """Validate both splits; returns every problem found instead of stopping at the first."""
    per_type = expected_sizes or PER_TYPE
    report = CheckReport(version, manifest.commit_sha)
    items: dict[str, list[QAItem]] = {}
    for split in ("dev", "test"):
        path = dataset_dir(version, root) / f"{split}.jsonl"
        if not path.exists():
            report.errors.append(f"missing file {path}")
            items[split] = []
            continue
        report.files[split] = file_sha256(path)
        rows, errors = parse_lines(path)
        report.errors.extend(errors)
        for it in rows:
            if it.split != split:
                report.errors.append(f"{it.id}: split {it.split!r} in {split}.jsonl")
            if it.dataset_version != version:
                report.errors.append(f"{it.id}: dataset_version {it.dataset_version!r}")
        items[split] = rows

    _check_distribution(items, per_type, report)
    all_items = items["dev"] + items["test"]
    report.statuses = dict(Counter(i.status for i in all_items))

    ids = Counter(i.id for i in all_items)
    report.errors.extend(f"duplicate id {k}" for k, n in ids.items() if n > 1)
    dev_questions = {_norm(i.question) for i in items["dev"]}
    report.errors.extend(
        f"{i.id}: test question also present in dev"
        for i in items["test"]
        if _norm(i.question) in dev_questions
    )

    cleaned: dict[str, CleanDoc] = {}
    sections: dict[str, set[str]] = {}

    def page(doc_id: str) -> CleanDoc | None:
        if doc_id not in cleaned:
            entry = manifest.documents.get(doc_id)
            if entry is None or entry.status != "ok":
                return None
            if not raw.has(entry.blob_sha):
                return None
            cleaned[doc_id] = clean_document(manifest, raw, doc_id)
            sections[doc_id] = set(document_section_ids(doc_id, cleaned[doc_id].body))
        return cleaned[doc_id]

    for it in all_items:
        if it.corpus_commit != manifest.commit_sha:
            report.errors.append(
                f"{it.id}: corpus_commit {it.corpus_commit[:12]} != manifest "
                f"{manifest.commit_sha[:12]}"
            )
        for doc_id in it.gold_documents:
            if page(doc_id) is None:
                entry = manifest.documents.get(doc_id)
                why = "not in manifest" if entry is None else f"status {entry.status}"
                report.errors.append(f"{it.id}: gold document {doc_id!r} unavailable ({why})")
        for sid in it.gold_sections:
            doc_id = sid.split("#", 1)[0]
            if page(doc_id) is None:
                continue
            report.checked_sections += 1
            if sid not in sections[doc_id]:
                report.errors.append(f"{it.id}: section {sid!r} is not a section of {doc_id}")
        for ex in it.supporting_excerpts:
            doc = page(ex.section_id.split("#", 1)[0])
            if doc is None:
                continue
            report.checked_excerpts += 1
            if ex.text not in doc.body:
                report.errors.append(
                    f"{it.id}: excerpt is not verbatim in {ex.section_id.split('#', 1)[0]}: "
                    f"{ex.text[:60]!r}"
                )
            elif not _excerpt_in_section(ex.section_id, ex.text, doc.body):
                report.errors.append(
                    f"{it.id}: excerpt {ex.text[:40]!r} is not inside section {ex.section_id!r}"
                )

    unanswerable = [i for i in all_items if not i.answerable]
    if unanswerable:
        corpus = _all_ok_texts(manifest, raw, page)
        for it in unanswerable:
            terms = it.absent_terms
            if not terms:
                report.errors.append(f"{it.id}: unanswerable item without absent_terms in notes")
            for term in terms:
                report.checked_absent_terms += 1
                hits = [d for d, text in corpus.items() if term.lower() in text]
                if hits:
                    report.errors.append(
                        f"{it.id}: absent term {term!r} found in {len(hits)} docs: {hits[:3]}"
                    )
    return report


def _excerpt_in_section(section_id: str, text: str, body: str) -> bool:
    """True if one occurrence of the excerpt lies in the lines of the given section."""
    doc_id = section_id.split("#", 1)[0]
    secs, lines, _ = _scan(body)
    chunks: dict[str, list[str]] = {}
    for ln in lines:
        chunks.setdefault(make_section_id(doc_id, secs[ln.sec].anchor), []).append(ln.text)
    return text in "\n".join(chunks.get(section_id, []))


def _all_ok_texts(manifest: Manifest, raw: RawStore, page) -> dict[str, str]:
    out: dict[str, str] = {}
    for doc_id, entry in manifest.documents.items():
        if entry.status == "ok":
            doc = page(doc_id)
            if doc is not None:
                out[doc_id] = f"{doc.title}\n{doc.body}".lower()
    return out


def _check_distribution(
    items: dict[str, list[QAItem]], per_type: dict[str, int], report: CheckReport
) -> None:
    for split, rows in items.items():
        table: dict[str, dict[str, int]] = {}
        for t in QUESTION_TYPES:
            of_type = [i for i in rows if i.type == t]
            table[t] = {
                "ru": sum(i.language == "ru" for i in of_type),
                "en": sum(i.language == "en" for i in of_type),
            }
            if len(of_type) != per_type[split]:
                report.errors.append(
                    f"{split}: {len(of_type)} items of type {t}, expected {per_type[split]}"
                )
        report.counts[split] = table
        expected_total = per_type[split] * len(QUESTION_TYPES)
        if len(rows) != expected_total:
            report.errors.append(f"{split}: {len(rows)} items, expected {expected_total}")
    for t in QUESTION_TYPES:
        ru = sum(report.counts[s][t]["ru"] for s in report.counts)
        en = sum(report.counts[s][t]["en"] for s in report.counts)
        if abs(ru - en) > 1:
            report.errors.append(f"type {t}: language split ru={ru} en={en} is not balanced")
