"""`.dna` strand codec (docs/DNA_FORMAT.md, ADR-008/019).

Read/write/sign/encrypt/verify a portable strand. A `.dna` is a zip containing:
  - manifest.json   (plaintext metadata + integrity root)
  - manifest.sig    (detached Ed25519 signature over the manifest's signing bytes)
  - strand.db.enc   (the SQLite strand, encrypted with XChaCha20-Poly1305)

Encryption uses wrap-don't-encrypt: a random data key encrypts the DB and is itself wrapped by
the passphrase-derived KEK (Argon2id). Integrity is a BLAKE2b Merkle root over row fingerprints;
the signature covers the whole manifest, so any tampering is detectable. Fails closed on a bad
signature, hash mismatch, wrong passphrase, or incompatible format.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import crypto
from .manifest import Manifest

M_MANIFEST = "manifest.json"
M_SIG = "manifest.sig"
M_DB = "strand.db.enc"
SUPPORTED_FORMAT_VERSION = 1


def export_dna(store, out_path: Path, *, passphrase: str, identity_path: Path,
               label: str = "") -> Manifest:
    out_path = Path(out_path)
    db_bytes = _snapshot_bytes(store)

    leaves = [crypto.blake2b_hex(fp.encode("utf-8")) for fp in store.fingerprints()]
    merkle = crypto.merkle_root(leaves)

    data_key = crypto.random_bytes(crypto.KEY_BYTES)
    salt = crypto.random_bytes(crypto.SALT_BYTES)
    ops, mem = crypto.argon2_params()
    kek = crypto.derive_key(passphrase, salt, ops, mem)
    wrap_nonce, wrapped_key = crypto.encrypt(kek, data_key)  # wrap the data key (small, single AEAD)
    db_ct = crypto.encrypt_stream(data_key, db_bytes)  # chunked, truncation-resistant (ADR-032)

    seed = crypto.load_or_create_identity(identity_path)
    pubkey = crypto.public_key_hex(seed)

    prev = store.get_meta("export_root")
    manifest = Manifest(
        strand_id=store.get_meta("strand_id") or _ensure_strand_id(store),
        version=store.get_version() + 1,
        created_at=datetime.now(timezone.utc).isoformat(),
        created_by_pubkey=pubkey,
        created_by_label=label,
        schema_version=int(store.get_meta("schema_version") or 1),
        embedding_provider=store.get_meta("embedding_provider") or "local",
        embedding_model=store.get_meta("embedding_model") or "",
        embedding_dim=int(store.get_meta("embedding_dim") or 0),
        count_memories=_user_count(store),
        count_edges=_edge_count(store),
        kdf_ops=ops, kdf_mem=mem,
        salt=salt.hex(), wrap_nonce=wrap_nonce.hex(), wrapped_key=wrapped_key.hex(),
        db_nonce="", enc_mode="stream",
        merkle_root=merkle, db_sha256=crypto.sha256_hex(db_ct),
        parents=[prev] if prev else [],
    )
    signature = crypto.sign(seed, manifest.signing_bytes())

    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(M_MANIFEST, manifest.to_json())
        z.writestr(M_SIG, signature)
        z.writestr(M_DB, db_ct)
    tmp.replace(out_path)  # atomic

    store.set_meta("export_root", merkle)
    store.bump_version()
    return manifest


def read_manifest(path: Path) -> tuple[Manifest, bytes, bytes]:
    with zipfile.ZipFile(path, "r") as z:
        manifest = Manifest.from_dict(json.loads(z.read(M_MANIFEST)))
        sig = z.read(M_SIG)
        db_ct = z.read(M_DB)
    return manifest, sig, db_ct


def verify_dna(path: Path) -> dict:
    """Verify signature + ciphertext hash WITHOUT decrypting (no passphrase needed)."""
    manifest, sig, db_ct = read_manifest(path)
    return {
        "signature_valid": crypto.verify(manifest.created_by_pubkey, manifest.signing_bytes(), sig),
        "db_hash_valid": crypto.sha256_hex(db_ct) == manifest.db_sha256,
        "pubkey": manifest.created_by_pubkey,
        "manifest": manifest,
    }


def import_dna(path: Path, dest_db_path: Path, *, passphrase: str,
               require_signature: bool = True) -> Manifest:
    manifest, sig, db_ct = read_manifest(path)
    if manifest.format_version > SUPPORTED_FORMAT_VERSION:
        raise ValueError(f"strand format v{manifest.format_version} is newer than supported "
                         f"v{SUPPORTED_FORMAT_VERSION}; upgrade Helix to import it")
    if require_signature and not crypto.verify(manifest.created_by_pubkey,
                                               manifest.signing_bytes(), sig):
        raise ValueError("invalid signature — refusing to import (tampered or untrusted strand)")
    if crypto.sha256_hex(db_ct) != manifest.db_sha256:
        raise ValueError("ciphertext hash mismatch — strand is corrupt or tampered")

    ops, mem = manifest.kdf_ops, manifest.kdf_mem
    kek = crypto.derive_key(passphrase, bytes.fromhex(manifest.salt), ops, mem)
    data_key = crypto.decrypt(kek, bytes.fromhex(manifest.wrap_nonce),
                              bytes.fromhex(manifest.wrapped_key))
    if manifest.enc_mode == "stream":
        db_bytes = crypto.decrypt_stream(data_key, db_ct)
    else:  # legacy single-blob AEAD
        db_bytes = crypto.decrypt(data_key, bytes.fromhex(manifest.db_nonce), db_ct)

    dest_db_path = Path(dest_db_path)
    dest_db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_db_path.with_suffix(dest_db_path.suffix + ".tmp")
    tmp.write_bytes(db_bytes)
    tmp.replace(dest_db_path)
    return manifest


# --- helpers ---

def _snapshot_bytes(store) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        snap = Path(d) / "snapshot.db"
        store.backup_to(snap)
        return snap.read_bytes()


def _edge_count(store) -> int:
    return int(store.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])


def _user_count(store) -> int:
    """Active memories the user thinks of as theirs (excludes connector hub nodes)."""
    return sum(1 for m in store.all_memories(limit=10**9) if not m.attributes.get("_hub"))


def _ensure_strand_id(store) -> str:
    sid = store.get_meta("strand_id")
    if not sid:
        from ..ids import new_id

        sid = new_id("strand")
        store.set_meta("strand_id", sid)
    return sid
