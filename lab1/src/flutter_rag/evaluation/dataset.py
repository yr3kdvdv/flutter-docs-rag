"""Evaluation dataset schema, loader and split guard (docs/contracts/stage05.md §5.1).

The dataset lives in lab1/evaluation/datasets/<version>/{dev,test}.jsonl, outside the corpus:
the corpus is only GitHub flutter/website (check N04 in tests).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from flutter_rag.config import LAB1_DIR
from flutter_rag.errors import RagError

DATASETS_DIR = LAB1_DIR / "evaluation" / "datasets"
DEFAULT_DATASET = "flutter-qa-v1"

Split = Literal["dev", "test"]
QuestionType = Literal["factoid", "multi_doc", "lookup", "contextual", "unanswerable"]
QUESTION_TYPES: tuple[str, ...] = ("factoid", "multi_doc", "lookup", "contextual", "unanswerable")
Language = Literal["ru", "en"]
Status = Literal["draft", "agent_checked", "verified"]

# Planned size of flutter-qa-v1 (contract §5.1): 5 types x (3 dev + 6 test).
PER_TYPE = {"dev": 3, "test": 6}

# Unanswerable items record the terms that were searched for in `notes`:
#   absent_terms: ["term", ...]
ABSENT_TERMS_RE = re.compile(r"absent_terms:\s*(\[[^\]]*\])")


class SplitGuardError(RagError):
    """The final test split is opened without --final (N03)."""


class DatasetError(RagError):
    pass


class Excerpt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    text: str = Field(min_length=1)


class QAItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    split: Split
    dataset_version: str
    type: QuestionType
    language: Language
    question: str = Field(min_length=5)
    answerable: bool
    expected_answer: str = Field(min_length=1)
    must_include: list[str] = Field(default_factory=list)
    expected_code: str | None = None
    gold_documents: list[str] = Field(default_factory=list)
    gold_sections: list[str] = Field(default_factory=list)
    supporting_excerpts: list[Excerpt] = Field(default_factory=list)
    corpus_commit: str
    status: Status
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self):
        if not self.id.startswith(f"{self.split}-"):
            raise ValueError(f"id {self.id!r} must start with '{self.split}-'")
        if self.answerable != (self.type != "unanswerable"):
            raise ValueError("answerable must be false exactly for type 'unanswerable'")
        if not self.answerable:
            if self.gold_documents or self.gold_sections or self.supporting_excerpts:
                raise ValueError("unanswerable items have empty gold and excerpts")
            if self.expected_code or self.must_include:
                raise ValueError("unanswerable items have no must_include / expected_code")
            return self
        if not (self.gold_documents and self.gold_sections and self.supporting_excerpts):
            raise ValueError("answerable items need gold_documents, gold_sections and excerpts")
        if self.type == "multi_doc" and len(set(self.gold_documents)) < 2:
            raise ValueError("multi_doc needs >= 2 different gold_documents")
        for sid in self.gold_sections:
            if "#" not in sid:
                raise ValueError(f"section id {sid!r} must look like '<document_id>#<anchor>'")
            if sid.split("#", 1)[0] not in self.gold_documents:
                raise ValueError(f"section {sid!r} belongs to no gold document")
        for e in self.supporting_excerpts:
            if e.section_id not in self.gold_sections:
                raise ValueError(f"excerpt section {e.section_id!r} is not in gold_sections")
        return self

    @property
    def absent_terms(self) -> list[str]:
        m = ABSENT_TERMS_RE.search(self.notes)
        return json.loads(m.group(1)) if m else []


@dataclass
class Dataset:
    version: str
    split: str
    path: Path
    sha256: str
    items: list[QAItem]


def dataset_dir(version: str = DEFAULT_DATASET, root: Path = DATASETS_DIR) -> Path:
    return root / version


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_lines(path: Path) -> tuple[list[QAItem], list[str]]:
    """Every valid item and one error message per invalid line (the validator reports all)."""
    items: list[QAItem] = []
    errors: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(QAItem.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            first = str(exc).splitlines()
            errors.append(f"{path.name}:{n}: {' '.join(first[:3])[:300]}")
    return items, errors


def load_split(
    split: str,
    *,
    version: str = DEFAULT_DATASET,
    final: bool = False,
    root: Path = DATASETS_DIR,
) -> Dataset:
    """Load one split. The test split needs final=True (no tuning on test, N03)."""
    if split not in PER_TYPE:
        raise DatasetError(f"unknown split {split!r}; expected dev or test")
    if split == "test" and not final:
        raise SplitGuardError(
            "the test split is the final hold-out: run it only with --final, after the "
            "configuration has been chosen on dev (N03)"
        )
    path = dataset_dir(version, root) / f"{split}.jsonl"
    if not path.exists():
        raise DatasetError(f"dataset file not found: {path}")
    items, errors = parse_lines(path)
    if errors:
        raise DatasetError("invalid dataset rows:\n" + "\n".join(errors))
    wrong = [i.id for i in items if i.split != split or i.dataset_version != version]
    if wrong:
        raise DatasetError(f"rows with a wrong split or dataset_version in {path}: {wrong}")
    return Dataset(version, split, path, file_sha256(path), items)
