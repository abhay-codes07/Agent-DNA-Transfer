"""Wave B — per-fact signing for merge anti-tamper (v2 plan §4.4). Offline / $0.

Exercises the sign -> verify -> tamper-detect flow. Works with the stdlib local-MAC fallback
when the crypto extra isn't installed, and with real Ed25519 when it is.
"""

from __future__ import annotations

from helix_core import factsign
from helix_core.config import Config
from helix_core.engine import Engine


def _eng(tmp_path) -> Engine:
    eng = Engine(Config(home=tmp_path))
    eng.remember("We use Postgres for billing", scope="project:billing")
    eng.remember("All API errors use RFC-7807", scope="project:billing")
    return eng


def test_sign_then_verify_roundtrip(tmp_path):
    eng = _eng(tmp_path)
    res = eng.sign_facts()
    assert res["signed"] >= 2
    assert res["scheme"] in ("ed25519", "local-mac")
    v = eng.verify_facts()
    assert v["verified"] >= 2 and v["tampered"] == []
    # Signing is idempotent (already-signed facts are skipped).
    assert eng.sign_facts()["signed"] == 0
    eng.close()


def test_tampering_breaks_signature(tmp_path):
    eng = _eng(tmp_path)
    eng.sign_facts()
    target = eng.list_memories()[0]
    target.content = "We use MySQL for billing"  # mutate content, keep the old signature
    with eng.store.tx():
        eng.store.upsert_memory(target)
    v = eng.verify_facts()
    assert target.id in v["tampered"]
    eng.close()


def test_factsign_roundtrip_either_scheme():
    seed = b"\x01" * 32
    scheme, signer = factsign.signer_id(seed)
    s_scheme, sig = factsign.sign(seed, factsign.fact_payload("fact", "hello world"))
    assert s_scheme == scheme
    assert factsign.verify(
        scheme, signer, factsign.fact_payload("fact", "hello world"), sig, seed=seed
    )
    # A different payload fails.
    assert not factsign.verify(
        scheme, signer, factsign.fact_payload("fact", "goodbye"), sig, seed=seed
    )
