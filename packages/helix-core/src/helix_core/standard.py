"""Portable Agent Memory — the open interchange standard (v2 plan §8, "USB for AI memory").

A vendor-neutral, human-readable JSON format any tool can read or write to move an agent's memory
between systems. The encrypted `.dna` strand is the *secure container*; this is the *open record
format* it carries. Three conformance levels:

  * **core**     — well-formed records with the required fields (id, type, content, created_at,
                   provenance). Anyone can produce/consume this.
  * **signed**   — every record carries a verifiable signature and the bundle has a Merkle
                   integrity root (tamper-evident, attributable).
  * **encrypted** — delivered inside a `.dna` container (XChaCha20 + Ed25519). Out of scope for
                   this JSON validator; the `.dna` codec is the reference implementation.

`validate()` is pure stdlib so other implementations can vendor it directly.
"""

from __future__ import annotations

from .models import MemoryType

FORMAT = "portable-agent-memory"
STANDARD_VERSION = "1.0"
VALID_TYPES = {t.value for t in MemoryType}
_REQUIRED = ("id", "type", "content", "created_at", "provenance")


def record(m, *, include_signature: bool = True) -> dict:
    """Serialize a Memory into a portable record (the open schema)."""
    r = {
        "id": m.id,
        "type": m.type.value,
        "content": m.content,
        "scope": m.scope,
        "confidence": round(m.confidence, 3),
        "importance": round(m.importance, 3),
        "valid_from": m.valid_from.isoformat() if m.valid_from else None,
        "valid_to": m.valid_to.isoformat() if m.valid_to else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "provenance": [
            {"agent": p.agent, "extractor": p.extractor, "origin": p.origin.value}
            for p in m.provenance
        ],
    }
    if include_signature and m.attributes.get("_sig"):
        r["signature"] = {
            "scheme": m.attributes.get("_sigscheme"),
            "signer": m.attributes.get("_signer"),
            "sig": m.attributes.get("_sig"),
        }
    return r


def build_bundle(
    memories, edges=None, *, generator: str, created_at: str, merkle_root=None
) -> dict:
    """Assemble a conformant interchange bundle (a plain dict, ready to serialize as JSON)."""
    doc: dict = {
        "format": FORMAT,
        "version": STANDARD_VERSION,
        "generator": generator,
        "created_at": created_at,
        "memories": [record(m) for m in memories],
    }
    if edges:
        doc["edges"] = [{"from": e.from_id, "to": e.to_id, "relation": e.relation} for e in edges]
    if merkle_root:
        doc["integrity"] = {"algo": "blake2b", "merkle_root": merkle_root}
    return doc


def validate(doc: dict) -> dict:
    """Check a document against the standard. Returns {valid, level, errors, count}.

    Pure stdlib — safe for any third-party implementation to reuse.
    """
    errors: list[str] = []
    if not isinstance(doc, dict):
        return {"valid": False, "level": None, "errors": ["document is not an object"], "count": 0}
    if doc.get("format") != FORMAT:
        errors.append(f"format must be '{FORMAT}'")
    if not isinstance(doc.get("version"), str):
        errors.append("missing string 'version'")
    mems = doc.get("memories")
    if not isinstance(mems, list):
        errors.append("'memories' must be a list")
        mems = []
    for i, m in enumerate(mems):
        if not isinstance(m, dict):
            errors.append(f"memory[{i}] is not an object")
            continue
        for key in _REQUIRED:
            if key not in m or m[key] in (None, ""):
                errors.append(f"memory[{i}] missing required '{key}'")
        if m.get("type") not in VALID_TYPES:
            errors.append(f"memory[{i}] has unknown type '{m.get('type')}'")
        c = m.get("confidence")
        if c is not None and not (isinstance(c, (int, float)) and 0.0 <= c <= 1.0):
            errors.append(f"memory[{i}] confidence out of range")
        if not isinstance(m.get("provenance", []), list):
            errors.append(f"memory[{i}] provenance must be a list")
    if errors:
        return {"valid": False, "level": None, "errors": errors, "count": len(mems)}
    signed = bool(mems) and all(m.get("signature") for m in mems) and bool(doc.get("integrity"))
    return {
        "valid": True,
        "level": "signed" if signed else "core",
        "errors": [],
        "count": len(mems),
    }
