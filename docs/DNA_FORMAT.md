# Helix — The `.dna` Strand Format

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD §7](TSD.md) · [Security](SECURITY_MODEL.md) · [ADR-008](../DECISIONS.md)

The `.dna` strand is the portable artifact that makes "take your memory anywhere" real. It is
**signed**, **encrypted**, **versioned**, and **mergeable** — a memory you can move like a
file and version like code, without a server or a blockchain.

---

## 1. Container

A `.dna` file is a single archive (tar, optionally zstd-compressed) containing:

```
my-brain.dna
├── manifest.json        # plaintext metadata + integrity root (signed)
├── manifest.sig         # detached Ed25519 signature over manifest.json
└── strand.db.enc        # the SQLite strand, encrypted (XChaCha20-Poly1305)
```

`manifest.json` is plaintext so a recipient can inspect *what* a strand is (schema, model,
counts, author key) and verify integrity **before** decrypting anything.

## 2. Manifest

```jsonc
{
  "format": "helix.dna",
  "format_version": 1,
  "strand_id": "01J...",            // stable identity across versions
  "version": 7,                      // monotonically increasing
  "created_at": "2026-06-18T...Z",
  "created_by": {
    "pubkey": "ed25519:base64...",   // author's signing public key
    "label": "abhay@laptop"
  },
  "schema_version": 1,               // memory-model schema
  "embedding": {                     // pin the embedding space
    "provider": "local",
    "model": "BAAI/bge-small-en-v1.5",
    "dim": 384,
    "normalized": true
  },
  "counts": { "memories": 1243, "edges": 880 },
  "encryption": {
    "cipher": "xchacha20poly1305",
    "kdf": "argon2id",
    "kdf_params": { "mem_kib": 65536, "iters": 3, "parallelism": 1, "salt": "base64..." },
    "nonce": "base64..."
  },
  "integrity": {
    "merkle_root": "blake3:hex...",  // root over per-row hashes (see §5)
    "db_sha256": "hex..."            // hash of the ciphertext blob
  },
  "history_head": "blake3:hex...",   // head of the op-history chain
  "parents": ["blake3:..."]          // prior version hash(es); enables diff/merge/rollback
}
```

The signature (`manifest.sig`) covers the **entire** manifest, including the integrity root,
so any tampering with content or metadata is detectable.

## 3. Encryption

- **Cipher:** XChaCha20-Poly1305 (AEAD) over `strand.db`.
- **Key derivation:** Argon2id from the user's passphrase (`HELIX_PASSPHRASE`), or the strand
  key is wrapped by a device-keychain key when no passphrase is used.
- **Nonces:** random 192-bit (XChaCha) per encryption; stored in the manifest.
- **Threat posture:** the disk/USB/cloud-drive holding the `.dna` is treated as untrusted; the
  plaintext strand exists only in memory on a trusted device. See [Security Model](SECURITY_MODEL.md).

## 4. Signing & verification

- Each user has an **Ed25519 identity keypair** (generated on `helix init`, stored in the OS
  keychain / `helix-identity/`, never committed, never inside a strand).
- `export` signs the manifest; `import` **verifies** the signature against the embedded
  pubkey and warns/blocks on mismatch or on an untrusted author (for shared strands).
- This gives Walrus-style verifiable integrity **without** a blockchain or network.

## 5. Integrity & content addressing

- Each memory/edge row hashes to a stable digest (BLAKE3 over canonicalized fields).
- A Merkle tree over those digests yields `merkle_root`, recorded and signed.
- Two strands can be **diffed cheaply** by comparing subtrees instead of full contents — the
  basis for fast `diff`/`merge` and for detecting exactly which facts changed.

## 6. Versioning & history

- `version` increments on every committed change; `parents` records prior version hash(es).
- An append-only `history` table logs operations (op type, affected ids, before/after hashes,
  provenance), chained via `history_head`.
- This enables:
  - `helix log` — the evolution of your memory, git-style.
  - `helix diff vA vB` — what changed between versions/strands.
  - `helix rollback <version>` — restore a prior state (e.g., undo a wrong learning).

## 7. Transfer operations

### export / clone
Snapshot `strand.db` → compute row/Merkle hashes → write manifest → sign → encrypt → archive.
Atomic (temp file + rename); never overwrites the source strand.

### import
1. Read `manifest.json`; check `format_version`/`schema_version` compatibility.
2. **Verify `manifest.sig`.** Reject on failure (fail closed).
3. Decrypt `strand.db.enc` (passphrase/keychain).
4. If `embedding` space differs from the importing install, **re-embed** content into the
   local space (tracked operation) rather than mixing vector spaces.
5. Open as a new local strand (or stage for merge).

### merge (`A ⊕ B`)
The hard, valuable operation — and it reuses the same engine as everyday learning:
1. Align nodes/edges by content hash + semantic match.
2. Run **consolidation** over the union (ADD/UPDATE/NOOP) and **conflict resolution** on
   contradictions (recency > confidence > provenance, optional LLM tie-break) — see
   [TSD §6.3/§6.6](TSD.md).
3. Preserve **both** provenances; never silently drop a contributor's fact.
4. Enforce the **redaction invariant**: secrets are never present to merge in the first place.
5. Produce a new `version` with both `parents` (reversible via rollback).

Merge is conflict-aware and reversible by construction; "two facts meet" has exactly one code
path whether they meet over time (one user) or at once (two users/teammates).

### rollback
Restore a prior `version` from `history`; the rollback is itself a new version (you can undo
an undo). No history is destroyed.

## 8. Compatibility rules

| Situation | Behavior |
|---|---|
| Newer `format_version` than installed | Refuse with upgrade guidance (fail closed) |
| Older `format_version` | Migrate forward on import |
| Different `schema_version` | Run schema migration |
| Different embedding space | Re-embed locally (tracked); never mix dims silently |
| Signature invalid / author untrusted | Block import (or warn for explicitly trusted shares) |

## 9. Why not a blockchain / decentralized store (for v1)

Walrus achieves portability + verifiability via decentralized, verifiable storage. Helix gets
the same *user-facing* guarantees — portable, integrity-verified, owner-controlled — with a
**signed encrypted file**: simpler, free, offline, and zero-infra. A decentralized/verifiable
backend remains a *pluggable option* for users who want it ([ADR-010](../DECISIONS.md)), not a
requirement for everyone.
