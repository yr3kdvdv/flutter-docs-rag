"""Qdrant collections: one collection per embedding model+dims and chunking strategy.

Embedded (local) mode allows one process per storage folder (verified, audit B2):
opening it twice raises RuntimeError, which we turn into StorageLockedError.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from qdrant_client import QdrantClient, models

from flutter_rag.errors import IndexNotReadyError, StorageLockedError, UpstreamError
from flutter_rag.grabber.manifest import write_atomic
from flutter_rag.preprocessing.chunking import Chunk

PAYLOAD_SOURCE = "flutter-docs"


def open_qdrant(url: str | None, path: Path) -> QdrantClient:
    if url:
        try:
            client = QdrantClient(url=url, timeout=10)
            client.get_collections()
            return client
        except Exception as exc:  # noqa: BLE001 - any connection failure
            raise UpstreamError("qdrant", "unavailable", type(exc).__name__) from exc
    path.mkdir(parents=True, exist_ok=True)
    try:
        return QdrantClient(path=str(path))
    except RuntimeError as exc:
        if "already accessed" in str(exc):
            raise StorageLockedError(str(path)) from exc
        raise


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str, dims: int, state_dir: Path):
        self.client = client
        self.collection = collection
        self.dims = dims
        self._state_path = state_dir / f"{collection}.json"

    # ---- index state: which version of each document is indexed -------------
    def load_state(self) -> dict[str, str]:
        if not self._state_path.exists() or not self.exists():
            return {}
        return json.loads(self._state_path.read_text())

    def save_state(self, state: dict[str, str]) -> None:
        write_atomic(self._state_path, json.dumps(state, indent=1, sort_keys=True) + "\n")

    # ---- collection ---------------------------------------------------------
    def exists(self) -> bool:
        return self.client.collection_exists(self.collection)

    def ensure(self) -> None:
        if not self.exists():
            self.client.create_collection(
                self.collection,
                vectors_config=models.VectorParams(size=self.dims, distance=models.Distance.COSINE),
            )
        info = self.client.get_collection(self.collection)
        size = info.config.params.vectors.size
        if size != self.dims:
            raise IndexNotReadyError(
                f"collection {self.collection} has dim {size}, config expects {self.dims}"
            )

    def count(self) -> int:
        return self.client.count(self.collection, exact=True).count if self.exists() else 0

    def delete_document(self, document_id: str) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]], extra_payload: dict) -> None:
        points = [
            models.PointStruct(
                id=c.chunk_id,
                vector=v,
                payload={
                    "source": PAYLOAD_SOURCE,
                    **asdict(c),
                    "section": c.section,
                    "source_url": c.source_url,
                    **extra_payload,
                },
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
        if points:
            self.client.upsert(self.collection, points=points)

    def search(self, vector: list[float], limit: int) -> list[tuple[dict, float]]:
        if not self.exists():
            raise IndexNotReadyError(
                f"коллекция {self.collection} не создана — сначала `flutter-rag ingest`"
            )
        res = self.client.query_points(
            self.collection, query=vector, limit=limit, with_payload=True
        )
        return [(p.payload, p.score) for p in res.points]
