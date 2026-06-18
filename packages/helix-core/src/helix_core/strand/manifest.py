"""The `.dna` manifest (docs/DNA_FORMAT.md §2).

Plaintext metadata describing a strand: schema/embedding space, counts, the encryption
parameters, and the integrity root. It is Ed25519-signed (the signature covers exactly
`signing_bytes()`), so any tampering with content *or* metadata is detectable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Manifest:
    strand_id: str
    version: int
    created_at: str
    created_by_pubkey: str
    created_by_label: str
    schema_version: int
    embedding_provider: str
    embedding_model: str
    embedding_dim: int
    count_memories: int
    count_edges: int
    # encryption parameters (all hex-encoded byte fields)
    kdf_ops: int
    kdf_mem: int
    salt: str
    wrap_nonce: str
    wrapped_key: str
    db_nonce: str
    # integrity
    merkle_root: str
    db_sha256: str
    parents: list[str] = field(default_factory=list)
    format: str = "helix.dna"
    format_version: int = 1
    cipher: str = "xchacha20poly1305-ietf"
    kdf: str = "argon2id"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    def signing_bytes(self) -> bytes:
        """Canonical bytes the Ed25519 signature is computed over (excludes the signature)."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
