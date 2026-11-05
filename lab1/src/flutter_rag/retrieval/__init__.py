"""Query embedding and Top-K vector search."""

from __future__ import annotations

from dataclasses import dataclass, fields

from flutter_rag.embeddings import EmbeddingProvider
from flutter_rag.preprocessing.chunking import Chunk
from flutter_rag.vectorstore import VectorStore

_CHUNK_FIELDS = {f.name for f in fields(Chunk)}


@dataclass
class Candidate:
    chunk: Chunk
    score: float
    rank: int  # 1-based rank from vector search


def chunk_from_payload(payload: dict) -> Chunk:
    return Chunk(**{k: v for k, v in payload.items() if k in _CHUNK_FIELDS})


def retrieve(
    question: str, embedder: EmbeddingProvider, store: VectorStore, top_k: int
) -> list[Candidate]:
    [vector] = embedder.embed([question], "query")
    hits = store.search(vector, top_k)
    return [
        Candidate(chunk_from_payload(p), score, rank)
        for rank, (p, score) in enumerate(hits, start=1)
    ]
