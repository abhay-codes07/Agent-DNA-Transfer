"""Wave B — change-as-event timeline (§1.4) and A-MEM auto-linking (§1.6). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.ids import edge_id
from helix_core.models import Edge, Memory, MemoryType, Status, utcnow


def _mem(mid, content, scope="project:db", status=Status.ACTIVE) -> Memory:
    now = utcnow()
    return Memory(
        id=mid,
        type=MemoryType.FACT,
        content=content,
        scope=scope,
        status=status,
        valid_from=now,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )


def test_changes_lists_supersession_transitions(tmp_path):
    eng = Engine(Config(home=tmp_path))
    old = _mem("old1", "We use SQLite", status=Status.SUPERSEDED)
    old.valid_to = utcnow()
    new = _mem("new1", "We use Postgres")
    with eng.store.tx():
        eng.store.upsert_memory(old, [0.0])
        eng.store.upsert_memory(new, [0.0])
        eng.store.add_edge(
            Edge(
                id=edge_id("new1", "supersedes", "old1"),
                from_id="new1",
                to_id="old1",
                relation="supersedes",
            )
        )
    rows = eng.changes()
    assert len(rows) == 1
    assert rows[0]["from"] == "We use SQLite" and rows[0]["to"] == "We use Postgres"
    assert "changed_at" in rows[0]
    eng.close()


def test_auto_link_off_by_default(tmp_path):
    eng = Engine(Config(home=tmp_path))  # auto_link defaults off
    eng.remember("We use Postgres for billing", scope="project:billing")
    eng.remember("We use Postgres for the data warehouse too", scope="project:billing")
    assert not eng.store.edges_by_relation("related_to")
    eng.close()


def test_auto_link_creates_related_edges_when_enabled(tmp_path):
    eng = Engine(Config(home=tmp_path, auto_link=True))
    eng.remember("We use Postgres for billing", scope="project:billing")
    eng.remember("We use Postgres for the data warehouse too", scope="project:billing")
    eng.remember("Postgres connection pooling uses pgbouncer", scope="project:billing")
    # Later additions should link to earlier semantically-near facts (capped, floor-gated).
    assert eng.store.edges_by_relation("related_to")
    eng.close()
