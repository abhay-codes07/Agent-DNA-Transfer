"""Store interfaces (TSD §5.3).

Keeping vector and graph behind Protocols lets us swap the default embedded SQLite store
for Postgres+pgvector (teams) or a decentralized backend (ADR-010) without touching callers.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models import Edge, Hit, Memory


@runtime_checkable
class VectorStore(Protocol):
    """ANN vector index. Default impl: sqlite-vec (the strand is one SQLite file)."""

    def upsert(self, id: str, embedding: list[float], payload: dict[str, Any]) -> None: ...

    def query(
        self, embedding: list[float], k: int, filters: dict[str, Any] | None = None
    ) -> list[Hit]: ...

    def delete(self, id: str) -> None: ...


@runtime_checkable
class GraphStore(Protocol):
    """Typed knowledge graph. Default impl: SQLite tables + NetworkX projections."""

    def add_node(self, node: Memory) -> None: ...

    def get_node(self, id: str) -> Memory | None: ...

    def add_edge(self, edge: Edge) -> None: ...

    def neighbors(self, id: str, depth: int = 1) -> list[Memory]: ...

    def all(self) -> list[Memory]: ...


@runtime_checkable
class BlobStore(Protocol):
    """Opaque content-addressed blobs (e.g., large provenance payloads)."""

    def put(self, data: bytes) -> str:  # returns content hash
        ...

    def get(self, digest: str) -> bytes | None: ...
