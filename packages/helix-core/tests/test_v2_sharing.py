"""Wave A — scoped redacted sharing + quarantine on import (v2 plan §3.1/§3.2). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.models import Cognitive, Memory, MemoryType, utcnow


def _mem(mid, content, *, mtype=MemoryType.FACT, scope="project:billing", vis=None) -> Memory:
    now = utcnow()
    attrs = {"_visibility": vis} if vis else {}
    return Memory(
        id=mid,
        type=mtype,
        content=content,
        scope=scope,
        cognitive=Cognitive.SEMANTIC,
        attributes=attrs,
        valid_from=now,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )


def _seed(eng, mems):
    with eng.store.tx():
        for m in mems:
            eng.store.upsert_memory(m, eng.embedder.embed([m.content])[0])


def test_export_share_excludes_personal_and_redacts(tmp_path):
    eng = Engine(Config(home=tmp_path, strand="alice"))
    secret = "deploy key is " + "".join(["sk-", "A" * 26])
    _seed(
        eng,
        [
            _mem("f1", "We use Postgres for billing"),
            _mem("id1", "My name is Alice", mtype=MemoryType.IDENTITY, scope="global"),
            _mem("f2", secret),
        ],
    )
    out = eng.export_share(tmp_path / "share.json", scope="project:billing")
    import json

    bundle = json.loads((tmp_path / "share.json").read_text())
    contents = [f["content"] for f in bundle["facts"]]
    assert "We use Postgres for billing" in contents
    assert all("Alice" not in c for c in contents)  # personal identity fact not shared
    assert all("sk-AAA" not in c for c in contents)  # secret redacted on the way out
    assert out["facts"] == len(bundle["facts"])
    eng.close()


def test_import_quarantines_untrusted_then_approve(tmp_path):
    src = Engine(Config(home=tmp_path, strand="alice"))
    _seed(src, [_mem("f1", "Events flow through NATS not Kafka")])
    src.export_share(tmp_path / "s.json", scope="project:billing", contributor="alice")
    src.close()

    dst = Engine(Config(home=tmp_path / "dst", strand="bob"))
    res = dst.import_share(tmp_path / "s.json", trust=False)
    assert res["quarantined"] == 1 and res["added"] == 0
    assert dst.list_memories() == []  # quarantined facts are not active/retrievable
    pending = dst.review_incoming()
    assert len(pending) == 1 and pending[0]["from"] == "alice"
    dst.approve_incoming(pending[0]["id"])
    assert any("NATS" in m.content for m in dst.list_memories())
    dst.close()


def test_import_trusted_contributor_adds_directly(tmp_path):
    src = Engine(Config(home=tmp_path, strand="alice"))
    _seed(src, [_mem("f1", "All API errors use RFC-7807")])
    src.export_share(tmp_path / "s.json", contributor="alice")
    src.close()

    dst = Engine(Config(home=tmp_path / "dst", strand="bob"))
    res = dst.import_share(tmp_path / "s.json", trust=True)
    assert res["added"] == 1 and res["quarantined"] == 0
    assert any("RFC-7807" in m.content for m in dst.list_memories())
    # Trust persists: a second bundle from the same contributor imports directly.
    res2 = dst.import_share(tmp_path / "s.json", trust=False)
    assert res2["quarantined"] == 0
    dst.close()


def test_tampered_fact_is_dropped(tmp_path):
    src = Engine(Config(home=tmp_path, strand="alice"))
    _seed(src, [_mem("f1", "We deploy on Fly.io")])
    src.export_share(tmp_path / "s.json", contributor="alice")
    src.close()
    import json

    bundle = json.loads((tmp_path / "s.json").read_text())
    bundle["facts"][0]["content"] = "We deploy on AWS"  # mutate without fixing the fingerprint

    dst = Engine(Config(home=tmp_path / "dst", strand="bob"))
    res = dst.import_share(bundle, trust=True)
    assert res["tampered"] == 1 and res["added"] == 0
    dst.close()


def test_rejected_incoming_is_tombstoned(tmp_path):
    src = Engine(Config(home=tmp_path, strand="alice"))
    _seed(src, [_mem("f1", "Staging resets every night")])
    src.export_share(tmp_path / "s.json", contributor="alice")
    src.close()

    dst = Engine(Config(home=tmp_path / "dst", strand="bob"))
    dst.import_share(tmp_path / "s.json", trust=False)
    pid = dst.review_incoming()[0]["id"]
    assert dst.reject_incoming(pid) is True
    assert dst.store.get_memory(pid) is None
    assert dst.store.tombstone_count() == 1  # won't be re-staged on a future share
    assert dst.review_incoming() == []
    dst.close()
