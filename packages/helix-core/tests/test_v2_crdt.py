"""Wave B — CRDT-style mergeable memory: Lamport LWW + add-wins (v2 plan §3.3). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.crdt import merge_memories, stamp
from helix_core.engine import Engine
from helix_core.models import Cognitive, Memory, MemoryType, utcnow
from helix_core.stores import SqliteStore


def _mem(mid, content, *, clock=0, replica="", scope="global") -> Memory:
    now = utcnow()
    m = Memory(
        id=mid,
        type=MemoryType.FACT,
        content=content,
        scope=scope,
        cognitive=Cognitive.SEMANTIC,
        valid_from=now,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )
    if clock or replica:
        stamp(m, clock, replica)
    return m


def test_merge_memories_higher_clock_wins():
    local = _mem("x", "We use SQLite", clock=1, replica="a")
    incoming = _mem("x", "We use Postgres", clock=2, replica="b")
    winner, changed = merge_memories(local, incoming)
    assert winner.content == "We use Postgres" and changed
    # Symmetric: order doesn't matter for convergence.
    winner2, _ = merge_memories(incoming, local)
    assert winner2.content == "We use Postgres"


def test_merge_memories_unions_provenance_and_maxes_scores():
    local = _mem("x", "v", clock=2, replica="a")
    local.importance, local.confidence = 0.9, 0.4
    incoming = _mem("x", "v", clock=1, replica="b")
    incoming.importance, incoming.confidence = 0.3, 0.8
    winner, _ = merge_memories(local, incoming)
    assert winner.importance == 0.9 and winner.confidence == 0.8


def _replica_with(mid, content, clock, embedder, path) -> None:
    store = SqliteStore(path)
    store.ensure_embedding_space(embedder.model, embedder.dim)
    m = _mem(mid, content, clock=clock, replica="b")
    store.upsert_memory(m, embedder.embed([content])[0])
    store.close()


def test_merge_replica_lww_and_add_wins(tmp_path):
    a = Engine(Config(home=tmp_path / "a"))
    a.remember("We use SQLite for storage", scope="global")
    mid = a.list_memories()[0].id

    bpath = tmp_path / "b.helix.db"
    store = SqliteStore(bpath)
    store.ensure_embedding_space(a.embedder.model, a.embedder.dim)
    # same id, newer clock -> should win LWW
    store.upsert_memory(
        _mem(mid, "We use Postgres for storage", clock=99, replica="b"),
        a.embedder.embed(["We use Postgres for storage"])[0],
    )
    # a fact only in B -> add-wins
    store.upsert_memory(
        _mem("only_b", "We deploy on Fly.io", clock=5, replica="b"),
        a.embedder.embed(["We deploy on Fly.io"])[0],
    )
    store.close()

    res = a.merge_replica(bpath)
    assert res["merged"] == 1 and res["added"] == 1
    assert a.store.get_memory(mid).content == "We use Postgres for storage"
    assert a.store.get_memory("only_b") is not None
    a.close()


def test_merge_replica_respects_tombstones(tmp_path):
    a = Engine(Config(home=tmp_path / "a"))
    a.remember("Temporary spike note", scope="global")
    mid = a.list_memories()[0].id
    content = a.store.get_memory(mid).content
    a.erase(mid)  # tombstoned

    bpath = tmp_path / "b.helix.db"
    _replica_with(mid, content, 50, a.embedder, bpath)
    res = a.merge_replica(bpath)
    assert res["added"] == 0  # erased fact is not resurrected
    assert a.store.get_memory(mid) is None
    a.close()
