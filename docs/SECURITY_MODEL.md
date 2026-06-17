# Helix — Security & Privacy Model

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [SECURITY.md](../SECURITY.md) · [DNA Format](DNA_FORMAT.md) · [TSD](TSD.md)

Helix stores a developer's most sensitive asset — their accumulated context and decisions —
so security and privacy are foundational, not features. This document is the threat model and
the guarantees that follow from it.

---

## 1. Principles

1. **Local-first means private-by-default.** Nothing leaves the device unless the user opens a
   specific door (a key for cloud extraction, an export, an opt-in sync).
2. **The user owns the keys and the data.** Signing/encryption keys are generated and stored on
   the device; the user can export or destroy them.
3. **Distill, don't hoard.** Helix stores facts, not transcripts — less to leak.
4. **Redact before anything.** Secrets are scrubbed before storage *and* before any model call.
5. **Fail closed.** Tampered or incompatible strands are rejected, not "best-efforted."

## 2. Assets to protect

- The **plaintext memory graph** (personal/project facts).
- The **signing keypair** (Ed25519) and **encryption key**.
- **Provider API keys** (`GEMINI_API_KEY`, `OPENAI_API_KEY`).
- The **integrity/authenticity** of strands (no forging or silent tampering).

## 3. Trust boundaries

| Zone | Trust | Contents |
|---|---|---|
| Device memory (running Helix) | Trusted | plaintext strand, keys (transient), engine |
| Disk / USB / cloud drive holding `.dna` | **Untrusted** | encrypted strand + signed manifest |
| LLM / cloud-embedding provider | **Untrusted** | only redacted slices, only if user supplies a key |
| Optional team sync backend | **Untrusted** | encrypted strand; secrets never synced |
| A connected agent (via MCP) | **Semi-trusted** | can call the small MCP tool surface only |

## 4. Cryptography

- **Encryption at rest:** XChaCha20-Poly1305 (AEAD) over the strand DB.
- **Key derivation:** Argon2id from `HELIX_PASSPHRASE`, or strand key wrapped by the OS
  keychain when no passphrase is set.
- **Signing:** Ed25519 over the manifest (which includes the content Merkle root), verified on
  import. Gives verifiable integrity/authenticity without a blockchain.
- **Hashing:** BLAKE3 for content addressing and the Merkle tree (diff/merge/tamper-evidence).

Details in [DNA Format](DNA_FORMAT.md) §3–§5.

## 5. Secret handling

- Provider keys and passphrases are read from the **environment only**; never logged, never
  written into a strand, never sent anywhere except the chosen LLM provider.
- **Tiered redaction at ingest *and* outbound** ([ADR-025](../DECISIONS.md), [Privacy & Compliance](PRIVACY_COMPLIANCE.md)):
  a pipeline of regex/checksum → **entropy secret-scan (detect-secrets + gitleaks)** →
  **Presidio NER** removes secrets/PII *before* storage **and** before any LLM payload leaves
  the device — so "secrets never leave your machine" is literally true. The invariant holds
  across `write`, `import`, and `merge`. Redaction is defense-in-depth (no detector is complete).
- Crash dumps and logs are redacted; content never appears in logs.

## 6. Threats & mitigations

| Threat | Mitigation |
|---|---|
| Stolen `.dna` file | Encrypted at rest; useless without the key (Argon2id/keychain) |
| Tampered strand / forged facts | Signed manifest + Merkle integrity; import verifies, fails closed |
| Secret leaks into memory | Redaction before storage/model; no raw transcripts stored |
| Provider key leakage | Env-only; never persisted/logged; never in a strand |
| Malicious agent exfiltrates memory via MCP | Minimal tool surface; scope limits; redaction; (roadmap) per-agent scopes/rate limits + audit log |
| Memory poisoning (bad facts injected) | Provenance on every fact; confidence; conflict resolution; user review; rollback |
| Untrusted shared strand on import | Signature/author check; warn/block on untrusted key; merge preserves provenance, never auto-trusts |
| Re-embedding leaks across spaces | Embedding space pinned per strand; mismatch → explicit re-embed, never silent mix |
| Supply-chain (deps) | Pinned deps, lockfiles; minimal surface; pre-launch audit |

## 7. Privacy posture

- **No ambient capture.** Helix ingests only what the user routes to it.
- **No required account.** The default product needs no sign-up, no server, no email.
- **Telemetry off by default**, and local-only when enabled; aggregates are shared only on
  explicit opt-in. Cost/usage stats live on the user's machine.
- **Right to forget / erase.** Any fact can be soft-deleted (recoverable) and then purged;
  the whole strand can be destroyed by deleting one file and the key.

## 8. The agent-exfiltration problem & the lethal trifecta ([ADR-024](../DECISIONS.md))

Helix is, by design, the **private-data leg of the "lethal trifecta"** (private data + untrusted
content + exfiltration ability). Because any connected agent can call `memory.search`, a
*malicious or hijacked* agent could try to vacuum memory, and **returned memory text is itself
untrusted** — a poisoned memory could carry injected instructions.

Mitigations now: the MCP surface is tiny; results are scope-bounded and token-budgeted; secrets
are never present to leak; stored content is sanitized so it can't act as instructions; tool
descriptions are static and audited (anti tool-poisoning/rug-pull); the daemon binds to loopback
and validates `Origin`; remote endpoints use OAuth 2.1 (PKCE, RFC 8707, no token passthrough).
On the roadmap: per-agent scopes/allow-lists, rate limits, and a local audit log of what each
agent read. See [MCP Integration](MCP_INTEGRATION.md) and [Consolidation](CONSOLIDATION.md)
(anti-poisoning guardrails).

## 9. What Helix does NOT claim

- It does not protect against a fully compromised host (keylogger/root) — no local-first tool can.
- The default (no passphrase, keychain-wrapped) trades some at-rest strength for usability;
  setting `HELIX_PASSPHRASE` strengthens it.
- Cloud extraction means trusting your chosen provider with *redacted* slices — that's a door
  the user opts to open.

## 10. Pre-launch security checklist

- [ ] External cryptography & redaction review.
- [ ] Fuzz the import/merge path (malformed/tampered strands).
- [ ] Verify no secret ever reaches logs, strands, or telemetry (automated tests).
- [ ] Per-agent access controls + audit log shipped before broad MCP exposure.
- [ ] Dependency audit + lockfile pinning + SBOM.

(Disclosure process: [SECURITY.md](../SECURITY.md).)
