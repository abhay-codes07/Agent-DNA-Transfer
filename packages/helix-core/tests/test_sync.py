"""Phase 7 tests: optional encrypted team sync (bring-your-own-storage).

Requires PyNaCl (the .dna backend); skipped if unavailable. Offline.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nacl")

from helix_core.config import Config  # noqa: E402
from helix_core.engine import Engine  # noqa: E402
from helix_core.sync import LocalDirBackend, S3Backend, backend_from_uri  # noqa: E402

PW = "team-shared-passphrase"


def _engine(home):
    return Engine(Config(home=home))


def test_push_then_pull_merges_memory_across_machines(tmp_path):
    shared = tmp_path / "shared"
    a = _engine(tmp_path / "a")
    a.remember("We use Postgres for the billing service.", scope="project:billing")
    a.remember("We deploy on Fridays only.", scope="project:billing")
    a.push(str(shared), passphrase=PW, name="team.dna")
    a.close()

    b = _engine(tmp_path / "b")
    b.remember("We use Postgres for the billing service.", scope="project:billing")  # duplicate
    res = b.pull(str(shared), passphrase=PW, name="team.dna")
    assert res["mode"] == "merge"
    assert res["merged"]["ADD"] >= 1  # the Fridays fact was new

    contents = [m.content.lower() for m in b.list_memories()]
    assert any("fridays" in c for c in contents)  # came from A
    assert sum("postgres" in c for c in contents) == 1  # deduped, not duplicated
    b.close()


def test_pushed_file_is_encrypted_at_rest(tmp_path):
    shared = tmp_path / "shared"
    a = _engine(tmp_path / "a")
    a.remember("SECRETMARKER about the deploy process", scope="g")
    a.push(str(shared), passphrase=PW, name="team.dna")
    a.close()
    data = (shared / "team.dna").read_bytes()
    assert b"SECRETMARKER" not in data  # the backend only ever sees ciphertext


def test_pull_missing_strand_raises(tmp_path):
    b = _engine(tmp_path / "b")
    with pytest.raises(ValueError):
        b.pull(str(tmp_path / "empty-dir"), passphrase=PW, name="nope.dna")
    b.close()


def test_backend_selection(tmp_path):
    assert isinstance(backend_from_uri(str(tmp_path / "d")), LocalDirBackend)
    s3 = backend_from_uri("s3://bucket/prefix")
    assert isinstance(s3, S3Backend)
    with pytest.raises(NotImplementedError):
        s3.put("x.dna", b"data")


def test_local_dir_backend_roundtrip(tmp_path):
    backend = LocalDirBackend(tmp_path / "store")
    backend.put("a.dna", b"hello")
    assert backend.get("a.dna") == b"hello"
    assert backend.get("missing.dna") is None
    assert "a.dna" in backend.list()
