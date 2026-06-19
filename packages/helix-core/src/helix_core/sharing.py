"""Scoped, redacted, attributable sharing (v2 plan §3.1 / §3.2).

A **share bundle** is a portable, human-readable JSON selection of facts a user chooses to hand
to a teammate or another agent. It is:

  * **Scoped** — only facts in the chosen scope are included; PERSONAL facts (identity, or anything
    tagged `_visibility: personal`) are never shared by default.
  * **Redacted-on-share** — content is re-run through secret + PII redaction before it leaves.
  * **Attributable** — each fact carries a `contributor` and a content `fingerprint`, so the
    receiver can see who distilled it and detect tampering. (Whole-bundle Ed25519 signing rides on
    the `.dna` codec; this layer adds per-fact provenance + integrity at $0.)

On import, facts from an **untrusted** contributor are quarantined (staged, not retrievable) until
the user reviews them — defending against memory poisoning (PoisonedRAG/MINJA). Trust is
trust-on-first-use: once a contributor is approved, their later facts import directly.
"""

from __future__ import annotations

from .models import Memory, MemoryType
from .redaction import redact

VIS_ORDER = {"personal": 0, "team": 1, "public": 2}


def visibility_of(mem: Memory) -> str:
    """A fact's share sensitivity. Identity facts default to personal; others to team."""
    v = mem.attributes.get("_visibility")
    if v in VIS_ORDER:
        return str(v)
    return "personal" if mem.type == MemoryType.IDENTITY else "team"


def select_for_share(
    memories: list[Memory], *, scope: str | None = None, include_personal: bool = False
) -> list[Memory]:
    """Pick the facts eligible to share: in-scope, non-hub, and not personal (unless opted in)."""
    out: list[Memory] = []
    for m in memories:
        if m.attributes.get("_hub"):
            continue
        if not include_personal and visibility_of(m) == "personal":
            continue
        if scope and not (m.scope == scope or m.scope.startswith(scope + ":")):
            continue
        out.append(m)
    return out


def _fingerprint(content: str, mtype: str) -> str:
    import hashlib

    return hashlib.blake2b(
        f"{mtype}|{content.strip().lower()}".encode(), digest_size=16
    ).hexdigest()


def build_bundle(
    memories: list[Memory],
    *,
    contributor: str,
    scope: str | None = None,
    pii: bool = True,
    seed: bytes | None = None,
) -> dict:
    """Build a redacted, attributable share bundle (a plain dict, ready to serialize as JSON).

    When `seed` is given, each fact is also signed (Ed25519 if the crypto extra is installed,
    else a local MAC) so a recipient can verify authenticity — not just integrity — on import.
    """
    facts = []
    for m in select_for_share(memories, scope=scope):
        clean = redact(m.content, pii=pii)
        entry = {
            "type": m.type.value,
            "content": clean,
            "scope": m.scope,
            "confidence": m.confidence,
            "importance": m.importance,
            "visibility": visibility_of(m),
            "contributor": contributor,
            "fingerprint": _fingerprint(clean, m.type.value),
        }
        if seed is not None:
            from .factsign import fact_payload, sign, signer_id

            scheme, signer = signer_id(seed)
            _, sig = sign(seed, fact_payload(m.type.value, clean))
            entry["scheme"] = scheme
            entry["signer"] = signer
            entry["sig"] = sig
        facts.append(entry)
    return {"helix_share": 1, "contributor": contributor, "scope": scope, "facts": facts}


def verify_bundle(bundle: dict) -> tuple[list[dict], list[dict]]:
    """Split a bundle's facts into (valid, tampered) by re-checking each fingerprint."""
    valid: list[dict] = []
    tampered: list[dict] = []
    for f in bundle.get("facts", []):
        expected = _fingerprint(f.get("content", ""), f.get("type", "fact"))
        (valid if expected == f.get("fingerprint") else tampered).append(f)
    return valid, tampered


def verify_signatures(facts: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split facts into (ok, bad_signature) by checking each Ed25519 signature.

    Local-MAC signatures can't be verified cross-party (they're symmetric), so they pass through
    here and are still covered by the fingerprint check; only a *failed* Ed25519 signature is a
    hard reject (an authenticity violation).
    """
    from .factsign import fact_payload, verify

    ok: list[dict] = []
    bad: list[dict] = []
    for f in facts:
        scheme, sig = f.get("scheme"), f.get("sig")
        if scheme == "ed25519" and sig:
            payload = fact_payload(f.get("type", "fact"), f.get("content", ""))
            (ok if verify(scheme, f.get("signer", ""), payload, sig) else bad).append(f)
        else:
            ok.append(f)
    return ok, bad
