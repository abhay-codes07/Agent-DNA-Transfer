"""Wave A — erasure cascade, tombstones, and DSAR export (v2 plan §4.1). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.ids import edge_id
from helix_core.models import Cognitive, Edge, Memory, MemoryType
from helix_core.stores.sqlite_store import content_fingerprint


def _eng(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


def test_erase_hard_deletes_and_tombstones(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("We deploy to production on Fridays.", scope="project:ops")
    target = eng.list_memories()[0]
    res = eng.erase(target.id)
    assert res["erased"] == 1
    assert eng.store.get_memory(target.id) is None
    assert all(m.id != target.id for m in eng.list_memories())
    assert eng.store.tombstone_count() == 1
    # The vector is gone too (no orphan embedding).
    assert eng.store.vector_search(eng.embedder.embed(["deploy"])[0], k=10) == [] or all(
        mid != target.id
        for mid, _ in eng.store.vector_search(eng.embedder.embed(["deploy"])[0], 10)
    )
    eng.close()


def test_tombstone_blocks_resurrection(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("Staging secrets rotate weekly.", scope="project:ops")
    m = eng.list_memories()[0]
    fp = content_fingerprint(m)
    eng.erase(m.id)
    # A would-be re-import of the same fact is recognized as tombstoned.
    incoming = Memory(
        id="x", type=m.type, content=m.content, scope=m.scope, cognitive=Cognitive.SEMANTIC
    )
    assert eng.store.is_tombstoned(content_fingerprint(incoming))
    assert eng.store.is_tombstoned(fp)
    eng.close()


def test_erase_flags_derived_dependents(tmp_path):
    eng = _eng(tmp_path)
    base = Memory(id="base1", type=MemoryType.FACT, content="We use SQLite", scope="global")
    derived = Memory(
        id="der1", type=MemoryType.FACT, content="Insight about storage", scope="global"
    )
    with eng.store.tx():
        eng.store.upsert_memory(base, [0.0])
        eng.store.upsert_memory(derived, [0.0])
        eng.store.add_edge(
            Edge(
                id=edge_id("der1", "derived_from", "base1"),
                from_id="der1",
                to_id="base1",
                relation="derived_from",
            )
        )
    res = eng.erase("base1")
    assert res["dependents_flagged"] == 1
    assert eng.store.get_memory("der1").attributes.get("_stale_suspected") is True
    eng.close()


def test_dsar_export_returns_facts_with_provenance(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("We chose Postgres for the billing service.", scope="project:billing")
    out = eng.export_subject("billing database")
    assert out["count"] >= 1
    assert all("provenance" in f for f in out["facts"])
    eng.close()


def test_capability_eval_scores_trust_metrics(tmp_path):
    from helix_core.eval import run_capability_eval

    res = run_capability_eval(home=tmp_path)
    assert res["secret_block_rate"] == 1.0  # no secret ever stored
    assert res["pii_block_rate"] == 1.0  # PII redacted
    assert res["stale_catch_rate"] == 1.0  # labeled staleness scenarios all correct
