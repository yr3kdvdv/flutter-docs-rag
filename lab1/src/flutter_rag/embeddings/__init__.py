"""Embedding providers behind one interface (document vs query embeddings).

Providers translate the unified EmbeddingTask into SDK-specific arguments (audit M3).
`CachedEmbedder` adds a persistent cache keyed by (model, dims, task, text hash), so
re-ingesting unchanged chunks never calls the API again.
"""

from __future__ import annotations

import hashlib
import sqlite3
import struct
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

EmbeddingTask = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    model_id: str
    dimensions: int

    def embed(self, texts: Sequence[str], task: EmbeddingTask) -> list[list[float]]: ...


@dataclass
class EmbedStats:
    api_calls: int = 0
    texts_sent: int = 0
    est_tokens_sent: int = 0
    cache_hits: int = 0
    retries: int = 0
    limiter_wait_s: float = 0.0


class EmbeddingCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, dims INTEGER, vec BLOB)"
        )
        self._lock = threading.Lock()

    @staticmethod
    def key(model: str, dims: int, task: str, text: str) -> str:
        return hashlib.sha256(f"{model}|{dims}|{task}|{text}".encode()).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        with self._lock:
            for i in range(0, len(keys), 500):
                part = keys[i : i + 500]
                q = f"SELECT key, dims, vec FROM emb WHERE key IN ({','.join('?' * len(part))})"
                for k, dims, blob in self._db.execute(q, part):
                    out[k] = list(struct.unpack(f"{dims}f", blob))
        return out

    def put_many(self, items: dict[str, list[float]]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO emb VALUES (?, ?, ?)",
                [(k, len(v), struct.pack(f"{len(v)}f", *v)) for k, v in items.items()],
            )
            self._db.commit()

    def close(self) -> None:
        self._db.close()


class CachedEmbedder:
    def __init__(self, provider: EmbeddingProvider, cache: EmbeddingCache):
        self.provider = provider
        self.cache = cache
        self.model_id = provider.model_id
        self.dimensions = provider.dimensions

    @property
    def stats(self) -> EmbedStats:
        return self.provider.stats  # type: ignore[attr-defined]

    def embed(self, texts: Sequence[str], task: EmbeddingTask) -> list[list[float]]:
        keys = [EmbeddingCache.key(self.model_id, self.dimensions, task, t) for t in texts]
        found = self.cache.get_many(keys)
        missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in found]
        if hasattr(self.provider, "stats"):
            self.provider.stats.cache_hits += len(texts) - len(missing)
        if missing:
            uniq = dict(missing)
            vecs = self.provider.embed(list(uniq.values()), task)
            new = dict(zip(uniq.keys(), vecs, strict=True))
            self.cache.put_many(new)
            found.update(new)
        return [found[k] for k in keys]
