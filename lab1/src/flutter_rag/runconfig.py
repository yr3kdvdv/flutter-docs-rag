"""Experiment/run configuration loaded from YAML (lab1/configs/*.yaml).

Secrets never live here; they come from flutter_rag.config.Settings.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from flutter_rag.config import LAB1_DIR

DOCS_CONTENT_ROOT = "sites/docs/src/content/"
DOCS_INCLUDES_ROOT = "sites/docs/src/_includes/"
DOCS_SITE_URL = "https://docs.flutter.dev/"


class CorpusConfig(BaseModel):
    name: str = "full"  # part of the collection name: different corpora never share an index
    repo: str = "flutter/website"
    ref: str = "main"
    include: list[str] = Field(default_factory=lambda: [DOCS_CONTENT_ROOT + "**/*.md"])
    exclude: list[str] = Field(default_factory=list)
    # Optional explicit subset (paths relative to the content root, without .md).
    # Used by the vertical slice; empty means "everything matched by include".
    pages: list[str] = Field(default_factory=list)
    skip_front_matter: dict[str, object] = Field(default_factory=dict)
    download_concurrency: int = 8


class ChunkingConfig(BaseModel):
    strategy: Literal["section"] = "section"
    max_tokens: int = 512
    overlap: float = 0.0
    code_soft_cap_tokens: int = 1024

    @property
    def strategy_id(self) -> str:
        return f"{self.strategy}-{self.max_tokens}-o{int(self.overlap * 100)}"


class EmbeddingConfig(BaseModel):
    provider: Literal["gemini"] = "gemini"
    model: str = "gemini-embedding-001"
    dimensions: int = 768
    batch_size: int = 50
    max_rpm: int | None = None
    max_tpm: int | None = None
    timeout_s: float = 20.0

    @property
    def slug(self) -> str:
        return f"{self.model}-{self.dimensions}".replace(".", "_")


class RetrievalConfig(BaseModel):
    top_k: int = 20


class FilteringConfig(BaseModel):
    min_score: float | None = None
    dedupe: Literal["content_hash"] = "content_hash"
    min_chars: int = 80
    max_chunks: int = 8


class RerankingConfig(BaseModel):
    enabled: bool = False
    provider: str = "voyage"
    model: str = "rerank-2.5"
    top_n: int = 5


class GenerationConfig(BaseModel):
    provider: Literal["gemini"] = "gemini"
    model: str
    prompt_name: str = "answer"
    prompt_version: str = "v1"
    max_context_tokens: int = 6000
    max_output_tokens: int = 1024
    temperature: float = 0.0
    timeout_s: float = 60.0


class RunConfig(BaseModel):
    config_id: str
    corpus: CorpusConfig = Field(default_factory=CorpusConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    filtering: FilteringConfig = Field(default_factory=FilteringConfig)
    reranking: RerankingConfig = Field(default_factory=RerankingConfig)
    generation: GenerationConfig

    @property
    def collection_name(self) -> str:
        return f"flutter__{self.corpus.name}__{self.embedding.slug}__{self.chunking.strategy_id}"

    def fingerprint(self) -> str:
        """Short hash of the full config, recorded in traces and run metadata."""
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()[:12]


def load_run_config(path: str | Path) -> RunConfig:
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = LAB1_DIR / path
    return RunConfig.model_validate(yaml.safe_load(path.read_text()))
