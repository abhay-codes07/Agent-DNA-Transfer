"""Wave B — propose/review governance, handoff, and tamper-evident audit log (§3.4/§3.5)."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine


def _eng(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


def test_propose_then_approve_flows_through_audit(tmp_path):
    eng = _eng(tmp_path)
    pid = eng.propose("We will adopt trunk-based development", scope="project:eng")
    # Proposed facts are staged, not active/retrievable.
    assert eng.list_memories() == []
    assert any(p["id"] == pid for p in eng.review_incoming())
    eng.approve_incoming(pid)
    assert any("trunk-based" in m.content for m in eng.list_memories())
    actions = [e["action"] for e in eng.audit_log()]
    assert "propose" in actions and "approve" in actions
    eng.close()


def test_audit_chain_detects_tampering(tmp_path):
    eng = _eng(tmp_path)
    pid = eng.propose("fact one")
    eng.approve_incoming(pid)
    assert eng.verify_audit() is True
    # Tamper with a row directly under the hood.
    eng.store.conn.execute("UPDATE audit SET action='forged' WHERE seq=1")
    eng.store.conn.commit()
    assert eng.verify_audit() is False
    eng.close()


def test_handoff_copies_facts_to_another_scope(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("We use NATS for events", scope="project:alpha")
    src = eng.list_memories(scope="project:alpha")[0]
    res = eng.handoff([src.id], "project:beta")
    assert res["handed_off"] == 1
    assert any("NATS" in m.content for m in eng.list_memories(scope="project:beta"))
    actions = [e["action"] for e in eng.audit_log()]
    assert "handoff" in actions
    eng.close()


def test_erase_is_audited(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("Temporary note about the spike", scope="project:x")
    mid = eng.list_memories()[0].id
    eng.erase(mid)
    assert any(e["action"] == "erase" for e in eng.audit_log())
    assert eng.verify_audit() is True
    eng.close()
