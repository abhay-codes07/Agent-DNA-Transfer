"""Wave B — retention/TTL purge (§4.1) + complexity-gated deep recall (§2.5). Offline / $0."""

from __future__ import annotations

from datetime import timedelta

from helix_core.config import Config
from helix_core.engine import Engine, _is_multi_hop
from helix_core.models import Status, utcnow


def test_purge_deletes_aged_out_and_tombstones(tmp_path):
    eng = Engine(Config(home=tmp_path))
    eng.remember("An old throwaway note", scope="project:x")
    mid = eng.list_memories()[0].id
    eng.forget(mid)
    # Backdate the forgotten memory well past the retention window.
    m = eng.store.get_memory(mid)
    m.updated_at = utcnow() - timedelta(days=400)
    with eng.store.tx():
        eng.store.upsert_memory(m)
    res = eng.purge(retention_days=365)
    assert res["purged"] == 1
    assert eng.store.get_memory(mid) is None
    assert eng.store.tombstone_count() == 1
    assert any(e["action"] == "purge" for e in eng.audit_log())
    eng.close()


def test_purge_keeps_recent_archived(tmp_path):
    eng = Engine(Config(home=tmp_path))
    eng.remember("A recent note", scope="project:x")
    mid = eng.list_memories()[0].id
    m = eng.store.get_memory(mid)
    m.status = Status.ARCHIVED
    with eng.store.tx():
        eng.store.upsert_memory(m)
    assert eng.purge(retention_days=365)["purged"] == 0  # too young to purge
    eng.close()


def test_multi_hop_detection():
    assert _is_multi_hop("how do billing and auth relate")
    assert _is_multi_hop("Postgres versus MySQL")
    assert not _is_multi_hop("database")


def test_deep_recall_bridges_two_hops(tmp_path):
    eng = Engine(Config(home=tmp_path))
    eng.remember("The billing service uses Postgres", scope="project:billing")
    eng.remember("Postgres is tuned with pgbouncer pooling", scope="project:billing")
    eng.remember("pgbouncer runs as a sidecar container", scope="project:billing")
    mems = eng.list_memories(scope="project:billing")
    by = {m.content[:20]: m.id for m in mems}
    a = next(i for k, i in by.items() if k.startswith("The billing"))
    b = next(i for k, i in by.items() if k.startswith("Postgres is tuned"))
    c = next(i for k, i in by.items() if k.startswith("pgbouncer runs"))
    eng.relate(a, b, "related_to")
    eng.relate(b, c, "related_to")
    deep = {
        h.memory.id for h in eng.recall("billing service", scope="project:billing", k=10, deep=True)
    }
    assert c in deep  # two hops away, reachable only with deep expansion
    eng.close()
