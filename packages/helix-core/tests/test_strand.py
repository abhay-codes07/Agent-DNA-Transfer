"""Phase 4 tests: the portable .dna strand (export/import/verify/merge/diff/history).

Requires PyNaCl (the .dna crypto backend); skipped if unavailable.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

pytest.importorskip("nacl")

from helix_core.config import Config  # noqa: E402
from helix_core.engine import Engine  # noqa: E402

PW = "correct horse battery staple"


def _engine(home: Path, strand: str = "default") -> Engine:
    return Engine(Config(home=home, strand=strand))


def test_export_import_roundtrip_preserves_recall(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("We chose Postgres over Mongo for billing.", scope="project:billing")
    eng.remember("All API errors use RFC-7807.", scope="project:billing")
    out = tmp_path / "brain.dna"
    m = eng.export_strand(str(out), passphrase=PW, label="laptop")
    assert out.exists()
    assert m.count_memories == 2
    assert m.created_by_pubkey and m.merkle_root
    eng.close()

    home2 = tmp_path / "home2"
    eng2 = _engine(home2)  # default strand; import writes a *different* file
    res = eng2.import_strand(str(out), passphrase=PW, as_strand="imported")
    assert res["manifest"].count_memories == 2
    eng2.close()

    eng3 = _engine(home2, strand="imported")
    hits = eng3.recall("which database for billing", scope="project:billing")
    assert any("postgres" in h.memory.content.lower() for h in hits)
    eng3.close()


def test_verify_reports_valid_signature_and_integrity(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("important durable fact about the project", scope="project:x")
    out = tmp_path / "b.dna"
    eng.export_strand(str(out), passphrase=PW)
    v = eng.verify_strand(str(out))
    assert v["signature_valid"] is True
    assert v["db_hash_valid"] is True
    eng.close()


def test_tampered_ciphertext_is_detected(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("a fact worth protecting", scope="g")
    src = tmp_path / "ok.dna"
    eng.export_strand(str(src), passphrase=PW)

    bad = tmp_path / "tampered.dna"
    with zipfile.ZipFile(src) as z:
        manifest, sig, ct = z.read("manifest.json"), z.read("manifest.sig"), bytearray(z.read("strand.db.enc"))
    ct[10] ^= 0xFF  # flip a byte of the encrypted DB
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", manifest)
        z.writestr("manifest.sig", sig)
        z.writestr("strand.db.enc", bytes(ct))

    v = eng.verify_strand(str(bad))
    assert v["db_hash_valid"] is False  # integrity check catches the tamper
    with pytest.raises(ValueError):
        eng.import_strand(str(bad), passphrase=PW, as_strand="nope")
    eng.close()


def test_wrong_passphrase_fails(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("secret project detail", scope="project:x")
    out = tmp_path / "b.dna"
    eng.export_strand(str(out), passphrase=PW)
    eng.close()

    eng2 = _engine(tmp_path / "h2")
    with pytest.raises(RuntimeError):  # DecryptionError
        eng2.import_strand(str(out), passphrase="not the passphrase", as_strand="x")
    eng2.close()


def test_merge_dedups_and_adds(tmp_path):
    a = _engine(tmp_path / "a")
    a.remember("We use Postgres for billing.", scope="project:billing")
    a.remember("We use Kafka for events.", scope="project:billing")
    out = tmp_path / "a.dna"
    a.export_strand(str(out), passphrase=PW)
    a.close()

    b = _engine(tmp_path / "b")
    b.remember("We use Postgres for billing.", scope="project:billing")  # duplicate of a's
    b.remember("We deploy on Fridays.", scope="project:billing")  # unique to b
    res = b.merge_strand(str(out), passphrase=PW)
    assert res["merged"]["ADD"] >= 1  # Kafka was new
    contents = [m.content.lower() for m in b.list_memories()]
    assert any("kafka" in c for c in contents)  # merged in
    assert sum("postgres" in c for c in contents) == 1  # not duplicated
    b.close()


def test_diff_reports_changes(tmp_path):
    a = _engine(tmp_path / "a")
    a.remember("Shared fact about deploys.", scope="g")
    a.remember("Only-in-A fact.", scope="g")
    out = tmp_path / "a.dna"
    a.export_strand(str(out), passphrase=PW)
    a.close()

    b = _engine(tmp_path / "b")
    b.remember("Shared fact about deploys.", scope="g")
    b.remember("Only-in-B fact.", scope="g")
    d = b.diff_strand(str(out), passphrase=PW)
    assert d["added"] >= 1 and d["removed"] >= 1 and d["common"] >= 1
    b.close()


def test_history_records_ops(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("a durable fact", scope="g")
    assert any(r["op"] == "add" for r in eng.history())
    eng.close()
