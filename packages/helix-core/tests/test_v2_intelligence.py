"""Wave A — memory-intelligence tests (conflict surfacing, staleness, tighter packing).

All offline / $0: deterministic unit-level checks that don't depend on embedder thresholds.
"""

from __future__ import annotations

from helix_core.config import Config
from helix_core.consolidate import _flag_conflict
from helix_core.engine import Engine
from helix_core.models import Cognitive, Hit, Memory, MemoryType, utcnow
from helix_core.retrieve import pack_context
from helix_core.staleness import flag_stale_dependents, key_entities
from helix_core.stores import SqliteStore


def _mem(mid: str, content: str, scope: str = "project:db") -> Memory:
    now = utcnow()
    return Memory(
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


# --- staleness ---


def test_key_entities_picks_distinctive_subjects():
    ents = key_entities("We use SQLite for the storage layer")
    assert "sqlite" in ents
    assert "we" not in ents and "use" not in ents and "storage" not in ents


def test_flag_stale_dependents_marks_dropped_subject(tmp_path):
    store = SqliteStore(tmp_path / "s.db")
    old = _mem("old1", "We use SQLite for storage")
    dep = _mem("dep1", "SQLite WAL mode is enabled for speed")
    keep = _mem("keep1", "All API errors use RFC-7807")
    for m in (old, dep, keep):
        store.upsert_memory(m, [0.0])
    flagged = flag_stale_dependents(store, old, "We use Postgres for storage", utcnow())
    assert "dep1" in flagged
    assert "keep1" not in flagged
    assert store.get_memory("dep1").attributes.get("_stale_suspected") is True
    store.close()


# --- conflict surfacing ---


def test_conflict_edge_surfaces_in_api(tmp_path):
    eng = Engine(Config(home=tmp_path))
    a, b = _mem("a1", "Deploys are frozen on Fridays"), _mem("b1", "Deploys are allowed any day")
    with eng.store.tx():
        eng.store.upsert_memory(a, [0.0])
        eng.store.upsert_memory(b, [0.0])
        _flag_conflict(eng.store, "a1", "b1", 0.7)
    pairs = eng.conflicts()
    assert len(pairs) == 1
    contents = {pairs[0]["a"]["content"], pairs[0]["b"]["content"]}
    assert "Deploys are frozen on Fridays" in contents
    queue = eng.review_queue()
    assert any(item["kind"] == "conflict" for item in queue)
    eng.close()


def test_review_queue_prioritizes_stale_then_resolve(tmp_path):
    eng = Engine(Config(home=tmp_path))
    stale = _mem("s1", "SQLite WAL mode is enabled")
    stale.attributes["_stale_suspected"] = True
    stale.attributes["_stale_reason"] = "references 'sqlite'"
    with eng.store.tx():
        eng.store.upsert_memory(stale, [0.0])
    q = eng.review_queue()
    assert q and q[0]["kind"] == "stale"
    # Keeping it clears the flag.
    eng.resolve_stale("s1", keep=True)
    assert eng.store.get_memory("s1").attributes.get("_stale_suspected") is None
    assert not any(i["id"] == "s1" for i in eng.review_queue())
    eng.close()


# --- tighter packing ---


def test_pack_context_drops_marginal_tail():
    hits = [
        Hit(memory=_mem("h1", "alpha alpha alpha decision"), score=1.0),
        Hit(memory=_mem("h2", "beta beta beta convention"), score=0.9),
        Hit(memory=_mem("h3", "gamma gamma gamma noise"), score=0.05),
    ]
    block = pack_context(hits, budget_tokens=1000, min_ratio=0.22)
    assert "alpha" in block and "beta" in block
    assert "gamma" not in block  # below the relevance floor


def test_pack_context_dedups_near_duplicates():
    hits = [
        Hit(memory=_mem("d1", "we use postgres for the billing service"), score=1.0),
        Hit(memory=_mem("d2", "we use postgres for the billing service"), score=0.95),
    ]
    block = pack_context(hits)
    assert block.count("postgres") == 1
