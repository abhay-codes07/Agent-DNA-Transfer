"""Crypto backend for the `.dna` strand (ADR-019, ADR-032, docs/DNA_FORMAT.md).

Primitives via PyNaCl/libsodium so the artifact matches the spec exactly:
  - XChaCha20-Poly1305 (AEAD, 192-bit nonce) for confidentiality+integrity
  - Argon2id for passphrase key derivation
  - Ed25519 detached signatures over the manifest for authenticity
  - BLAKE2b (stdlib) Merkle tree for content integrity / cheap diffing
    (BLAKE3 from ADR-019 is an optional future upgrade; not in the stdlib — see ADR-032)

Only `.dna` export/import need this; the always-on $0 memory loop stays dependency-free.
A clear error is raised if PyNaCl is unavailable.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

NONCE_BYTES = 24  # XChaCha20-Poly1305 IETF nonce
KEY_BYTES = 32
SALT_BYTES = 16


def _nacl():
    try:
        import nacl.bindings as bindings
        import nacl.exceptions as exceptions
        import nacl.pwhash as pwhash
        import nacl.signing as signing
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "the .dna strand needs PyNaCl for encryption/signing — `pip install pynacl`"
        ) from exc
    return bindings, pwhash, signing, exceptions


# --- key derivation (Argon2id) ---

def derive_key(passphrase: str, salt: bytes, ops: int, mem: int) -> bytes:
    _, pwhash, _, _ = _nacl()
    return pwhash.argon2id.kdf(KEY_BYTES, passphrase.encode("utf-8"), salt,
                               opslimit=ops, memlimit=mem)


def argon2_params() -> tuple[int, int]:
    """Interactive limits — fast enough for an interactive tool, still memory-hard."""
    _, pwhash, _, _ = _nacl()
    return pwhash.argon2id.OPSLIMIT_INTERACTIVE, pwhash.argon2id.MEMLIMIT_INTERACTIVE


def random_bytes(n: int) -> bytes:
    return os.urandom(n)


# --- AEAD (XChaCha20-Poly1305) ---

def encrypt(key: bytes, message: bytes, aad: bytes = b"") -> tuple[bytes, bytes]:
    bindings, _, _, _ = _nacl()
    nonce = os.urandom(NONCE_BYTES)
    ct = bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(message, aad, nonce, key)
    return nonce, ct


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes = b"") -> bytes:
    bindings, _, _, exceptions = _nacl()
    try:
        return bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(ciphertext, aad, nonce, key)
    except exceptions.CryptoError as exc:
        raise DecryptionError("decryption failed (wrong passphrase or tampered strand)") from exc


class DecryptionError(RuntimeError):
    pass


# --- Ed25519 identity / signing ---

def load_or_create_identity(path: Path) -> bytes:
    """Return the Ed25519 seed (32 bytes), generating + persisting it on first use."""
    if path.exists():
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    seed = os.urandom(32)
    path.write_text(seed.hex(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return seed


def public_key_hex(seed: bytes) -> str:
    _, _, signing, _ = _nacl()
    return signing.SigningKey(seed).verify_key.encode().hex()


def sign(seed: bytes, data: bytes) -> bytes:
    _, _, signing, _ = _nacl()
    return signing.SigningKey(seed).sign(data).signature


def verify(public_key_hex: str, data: bytes, signature: bytes) -> bool:
    _, _, signing, exceptions = _nacl()
    try:
        signing.VerifyKey(bytes.fromhex(public_key_hex)).verify(data, signature)
        return True
    except (exceptions.BadSignatureError, ValueError):
        return False


# --- hashing / Merkle (BLAKE2b) ---

def blake2b_hex(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_root(leaf_hexes: list[str]) -> str:
    """Order-independent BLAKE2b Merkle root over leaf digests (sorted for determinism)."""
    if not leaf_hexes:
        return blake2b_hex(b"")
    level = [bytes.fromhex(h) for h in sorted(leaf_hexes)]
    while len(level) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(level), 2):
            a = level[i]
            b = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(hashlib.blake2b(a + b, digest_size=32).digest())
        level = nxt
    return level[0].hex()
