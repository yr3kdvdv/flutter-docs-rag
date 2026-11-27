"""Qdrant collections: one collection per embedding model+dims and chunking strategy.

Embedded (local) mode allows one process per storage folder (verified, audit B2):
opening it twice raises RuntimeError, which we turn into StorageLockedError.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from fcntl import LOCK_EX, flock
from pathlib import Path

from httpx import TimeoutException, TransportError
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from flutter_rag.errors import IndexNotReadyError, StorageLockedError, UpstreamError
from flutter_rag.grabber.manifest import write_atomic
from flutter_rag.preprocessing.chunking import Chunk

PAYLOAD_SOURCE = "flutter-docs"
SNAPSHOT_KEY = "flutter_rag_snapshot"


def _qdrant_call[**P, T](operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        return operation(*args, **kwargs)
    except UnexpectedResponse as exc:
        raise UpstreamError(
            "qdrant", "unavailable", "collection request failed", exc.status_code
        ) from exc
    except (ResponseHandlingException, TransportError) as exc:
        cause = exc.source if isinstance(exc, ResponseHandlingException) else exc
        kind = "timeout" if isinstance(cause, TimeoutException) else "unavailable"
        raise UpstreamError("qdrant", kind, type(cause).__name__) from exc


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

    @contextmanager
    def ingest_lock(self) -> Iterator[None]:
        """Serialize writers that share this collection and its local progress files."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        with self._state_path.with_suffix(".lock").open("a") as lock:
            flock(lock, LOCK_EX)
            yield

    # ---- index state: which version of each document is indexed -------------
    def load_state(self) -> dict[str, str]:
        if not self._state_path.exists() or not self.exists():
            return {}
        return json.loads(self._state_path.read_text())

    def save_state(self, state: dict[str, str]) -> None:
        write_atomic(self._state_path, json.dumps(state, indent=1, sort_keys=True) + "\n")

    # ---- collection ---------------------------------------------------------
    def exists(self) -> bool:
        return _qdrant_call(self.client.collection_exists, self.collection)

    def ensure(self) -> None:
        if not self.exists():
            _qdrant_call(
                self.client.create_collection,
                self.collection,
                vectors_config=models.VectorParams(size=self.dims, distance=models.Distance.COSINE),
            )
        info = _qdrant_call(self.client.get_collection, self.collection)
        size = info.config.params.vectors.size
        if size != self.dims:
            raise IndexNotReadyError(
                f"collection {self.collection} has dim {size}, config expects {self.dims}"
            )

    def count(self) -> int:
        return (
            _qdrant_call(self.client.count, self.collection, exact=True).count
            if self.exists()
            else 0
        )

    def read_snapshot(self) -> dict | None:
        info = _qdrant_call(self.client.get_collection, self.collection)
        return (info.config.metadata or {}).get(SNAPSHOT_KEY)

    def write_snapshot(self, snapshot: dict) -> None:
        if (
            not _qdrant_call(
                self.client.update_collection, self.collection, metadata={SNAPSHOT_KEY: snapshot}
            )
            or self.read_snapshot() != snapshot
        ):
            raise UpstreamError("qdrant", "unavailable", "snapshot metadata was not saved")

    def source_points(self) -> Iterator[tuple[str, dict]]:
        """Read enough payload to verify a collection written before snapshot metadata."""
        offset = None
        while True:
            points, offset = _qdrant_call(
                self.client.scroll,
                self.collection,
                offset=offset,
                limit=256,
                with_payload=["source", "document_id", "blob_sha", "source_commit", "content_hash"],
                with_vectors=False,
            )
            for point in points:
                yield str(point.id), point.payload or {}
            if offset is None:
                return

    def delete_document(self, document_id: str) -> None:
        _qdrant_call(
            self.client.delete,
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
            _qdrant_call(self.client.upsert, self.collection, points=points)

    def search(self, vector: list[float], limit: int) -> list[tuple[dict, float]]:
        if not self.exists():
            raise IndexNotReadyError(
                f"коллекция {self.collection} не создана — сначала `flutter-rag ingest`"
            )
        res = _qdrant_call(
            self.client.query_points, self.collection, query=vector, limit=limit, with_payload=True
        )
        return [(p.payload, p.score) for p in res.points]
