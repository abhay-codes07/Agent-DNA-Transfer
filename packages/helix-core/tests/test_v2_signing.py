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


def test_share_bundle_carries_signatures(tmp_path):
    eng = _eng(tmp_path)
    import json

    eng.export_share(tmp_path / "s.json", scope="project:billing", contributor="alice")
    bundle = json.loads((tmp_path / "s.json").read_text())
    for f in bundle["facts"]:
        assert {"sig", "signer", "scheme"} <= set(f)
        assert f["scheme"] in ("ed25519", "local-mac")
    eng.close()


def test_import_drops_facts_with_a_forged_signature(tmp_path):
    src = _eng(tmp_path / "src")
    import json

    src.export_share(tmp_path / "s.json", contributor="alice")
    src.close()
    bundle = json.loads((tmp_path / "s.json").read_text())
    # Corrupt a signature WITHOUT touching content (so the fingerprint still passes).
    sig = bundle["facts"][0]["sig"]
    bundle["facts"][0]["sig"] = ("0" if sig[0] != "0" else "1") + sig[1:]

    dst = Engine(Config(home=tmp_path / "dst", strand="bob"))
    res = dst.import_share(bundle, trust=True)
    if factsign.have_crypto():
        # Ed25519 is cross-party verifiable -> the forged signature is caught and dropped.
        assert res["forged"] == 1
        assert res["added"] == len(bundle["facts"]) - 1
    else:
        # local-MAC isn't cross-party verifiable -> not rejected here (fingerprint still guards).
        assert res["forged"] == 0
    dst.close()


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
