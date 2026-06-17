"""`.dna` strand codec (docs/DNA_FORMAT.md, ADR-008).

Read/write/sign/encrypt/verify a portable strand; diff/merge/rollback. All mutations are
transactional (temp-write + atomic rename) so a crash never yields a partial strand.

Crypto: XChaCha20-Poly1305 (encrypt) + Ed25519 (sign manifest) + Argon2id (KDF) + BLAKE3
(content addressing / Merkle integrity). Implemented in Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Manifest:
    format: str = "helix.dna"
    format_version: int = 1
    strand_id: str = ""
    version: int = 0
    schema_version: int = 1
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    counts: dict[str, int] = field(default_factory=dict)
    merkle_root: str = ""
    parents: list[str] = field(default_factory=list)


def export_dna(strand_db: Path, out: Path, *, passphrase: str | None) -> Manifest:
    """Snapshot -> hash -> manifest -> sign -> encrypt -> archive (atomic)."""
    raise NotImplementedError("Phase 4")


def import_dna(dna: Path, *, passphrase: str | None) -> Path:
    """Verify signature -> check compat -> decrypt -> return opened strand path.

    Fails closed on bad signature or incompatible format (docs/SECURITY_MODEL.md §6).
    """
    raise NotImplementedError("Phase 4")


def verify(dna: Path) -> bool:
    """Verify the Ed25519 signature and Merkle integrity without decrypting content."""
    raise NotImplementedError("Phase 4")
