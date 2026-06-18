"""Store-interface conformance (ADR-018). The Postgres backend is integration-tested only when
HELIX_TEST_PG_DSN points at a real Postgres+pgvector (skipped otherwise)."""

from __future__ import annotations

import os

import pytest

from helix_core.stores import SqliteStore, Store


def test_sqlite_store_satisfies_the_store_protocol(tmp_path):
    s = SqliteStore(tmp_path / "s.helix.db")
    try:
        assert isinstance(s, Store)  # the default backend implements the swappable interface
    finally:
        s.close()


@pytest.mark.skipif(
    not os.environ.get("HELIX_TEST_PG_DSN"),
    reason="set HELIX_TEST_PG_DSN to a Postgres+pgvector DSN to run this",
)
def test_pgvector_store_roundtrip():
    from helix_core.embed import HashingEmbedder
    from helix_core.models import Memory, MemoryType
    from helix_core.stores import PgVectorStore

    e = HashingEmbedder()
    s = PgVectorStore(os.environ["HELIX_TEST_PG_DSN"])
    try:
        assert isinstance(s, Store)
        s.ensure_embedding_space(e.model, e.dim)
        m = Memory(id="t1", type=MemoryType.FACT, content="the postgres backend works")
        with s.tx():
            s.upsert_memory(m, e.embed([m.content])[0])
        assert s.get_memory("t1").content == m.content
        hits = s.vector_search(e.embed(["postgres backend"])[0], 5)
        assert hits and hits[0][0] == "t1"
    finally:
        s.close()
