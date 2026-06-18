"""Phase 6 tests: the Python SDK has parity with the engine/CLI/MCP surface. Offline."""

from __future__ import annotations

import pytest

from helix_core.config import Config
from helix_sdk import Helix


def _helix(home) -> Helix:
    return Helix(Config(home=home))


def test_sdk_memory_parity(tmp_path):
    with _helix(tmp_path) as mem:
        r = mem.remember("We use Postgres for the billing service.", scope="project:billing")
        assert r[0].op == "ADD"
        mid = r[0].memory_id

        hits = mem.recall("billing database", scope="project:billing")
        assert any("postgres" in h.memory.content.lower() for h in hits)

        assert mem.context(scope="project:billing")
        assert any(m.id == mid for m in mem.list())
        assert mem.get(mid).content

        edited = mem.edit(mid, content="We use MySQL for the billing service.")
        assert "MySQL" in edited.content

        assert any(o["op"] == "edit" for o in mem.history())
        assert mem.stats()["embedding_dim"] > 0
        assert mem.forget(mid) == [mid]


def test_sdk_transfer_roundtrip(tmp_path):
    pytest.importorskip("nacl")
    a = _helix(tmp_path / "a")
    a.remember("Shared decision: adopt trunk-based development.", scope="g")
    out = tmp_path / "x.dna"
    a.export(str(out), passphrase="sdk-pass")
    assert a.verify(str(out))["signature_valid"] is True
    a.close()

    b = _helix(tmp_path / "b")
    res = b.import_(str(out), passphrase="sdk-pass", as_strand="imp")
    assert res["manifest"].count_memories == 1
    b.close()
