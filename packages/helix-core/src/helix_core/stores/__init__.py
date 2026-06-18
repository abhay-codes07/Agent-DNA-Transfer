"""Storage backends. Default = embedded SQLite (one file: vectors + graph + metadata).

`Store` is the swappable interface (ADR-018). `PgVectorStore` is an experimental Postgres
backend for large/shared strands (imports psycopg lazily on use).
"""

from .base import BlobStore, GraphStore, Store, VectorStore
from .sqlite_store import SqliteStore

__all__ = ["VectorStore", "GraphStore", "BlobStore", "Store", "SqliteStore", "PgVectorStore"]


def __getattr__(name: str):
    # Lazy: importing PgVectorStore doesn't import psycopg until it's instantiated.
    if name == "PgVectorStore":
        from .pgvector_store import PgVectorStore

        return PgVectorStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
