"""Per-fact signing for merge anti-tamper (v2 plan §4.4).

The whole `.dna` strand is already Ed25519-signed, but a *whole-strand* signature can't be
verified once facts are recombined across strands during a merge. Per-fact signatures let a
recipient verify or reject each incoming fact individually, and detect any mutation.

Two schemes, chosen automatically:
  * **ed25519** — a real asymmetric signature (via the strand crypto / PyNaCl) when the crypto
    extra is installed. Cross-party verifiable: anyone with the signer's public key can check it.
  * **local-mac** — a stdlib keyed BLAKE2b MAC fallback so the sign→verify→tamper flow works at
    $0 with no dependencies. Self-verifiable only (needs the local seed), so it gives integrity
    for your own strand but not cross-party authenticity.

A fact stores `_sig`, `_signer`, and `_sigscheme` in its attributes.
"""

from __future__ import annotations

import hashlib


def have_crypto() -> bool:
    try:
        import nacl.signing  # noqa: F401

        return True
    except Exception:
        return False


def fact_payload(mtype: str, content: str) -> bytes:
    """The canonical bytes a fact signature commits to (type + normalized content)."""
    return f"{mtype}|{content.strip()}".encode("utf-8")


def signer_id(seed: bytes) -> tuple[str, str]:
    """Return (scheme, signer_id): the Ed25519 public key, or a short local key id."""
    if have_crypto():
        from .strand.crypto import public_key_hex

        return "ed25519", public_key_hex(seed)
    return "local-mac", hashlib.blake2b(seed, digest_size=8).hexdigest()


def sign(seed: bytes, payload: bytes) -> tuple[str, str]:
    """Sign a payload. Returns (scheme, signature_hex)."""
    if have_crypto():
        from .strand.crypto import sign as ed_sign

        return "ed25519", ed_sign(seed, payload).hex()
    return "local-mac", hashlib.blake2b(payload, key=seed[:32], digest_size=32).hexdigest()


def verify(
    scheme: str, signer: str, payload: bytes, signature: str, *, seed: bytes | None = None
) -> bool:
    """Verify a fact signature. `seed` is required only for the local-mac (symmetric) fallback."""
    if scheme == "ed25519":
        if not have_crypto():
            return False
        from .strand.crypto import verify as ed_verify

        try:
            return ed_verify(signer, payload, bytes.fromhex(signature))
        except Exception:
            return False
    if scheme == "local-mac":
        if seed is None:
            return False
        expect = hashlib.blake2b(payload, key=seed[:32], digest_size=32).hexdigest()
        return expect == signature
    return False
