# Helix — Sync & Merge (optional, end-to-end encrypted)

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [.dna Format](DNA_FORMAT.md) · [Security](SECURITY_MODEL.md) · [Memory Model](MEMORY_MODEL.md) · [Decisions](../DECISIONS.md)

---

Helix is a **local-first, coding-agent-first, portable, $0-default** AI memory layer. The unit of portability is a single signed + encrypted **`.dna`** artifact (see [.dna Format](DNA_FORMAT.md)). This document specifies the *optional* layer on top: **end-to-end-encrypted sync** across devices/teams, and the **git-like merge semantics** that keep concurrent memory consistent.

> **Sync is always optional.** Local-first never requires it. A single user on a single machine with one `.dna` file is the supported baseline; everything below is additive and degrades to "copy a file around" when disabled.

Governing ADRs: **ADR-021** (merge strategy: CRDT + 3-way semantic + bi-temporal), **ADR-022** (optional E2E sync, BYO storage, two-secret derivation), **ADR-013** (bi-temporal fact model).

---

## 1. Principles

| # | Principle | Consequence |
|---|-----------|-------------|
| P1 | **Sync is optional, never load-bearing.** | All correctness guarantees hold offline. Disabling sync loses *convenience*, never *data*. |
| P2 | **E2E encrypted by default.** | Plaintext memory and keys never leave the device. The remote is an untrusted blob store. |
| P3 | **Server sees only ciphertext.** | Storage/relay handles content-addressed, encrypted chunks. No plaintext, no searchable index, no metadata it can read. |
| P4 | **Bring-your-own-bucket first.** | Default backend is *your* S3/R2/Drive. Helix ships no mandatory server → preserves the `$0-default`. |
| P5 | **Convergence is mechanical; contradiction is semantic.** | CRDTs guarantee replicas converge byte-for-byte; *contradictory facts* are resolved by business logic via 3-way merge. |
| P6 | **History is the product.** | We keep full op history and bi-temporal records. Provenance, audit, rollback, and anti-poisoning all derive from never throwing data away. |
| P7 | **Review team memory like code.** | Incoming memory lands as a reviewable diff (PR-style), which doubles as the primary defense against memory poisoning. |

**Threat boundary.** The remote (bucket or relay) is *honest-but-curious and possibly malicious about availability*. It can drop, reorder, or withhold chunks; it can serve stale data. It **cannot** read plaintext, forge a signed Merkle root, or silently mutate a chunk (content-addressing + Ed25519 detect both). See [Security](SECURITY_MODEL.md).

---

## 2. Storage model

```
                        ┌────────────────────────────────────────────┐
   device A             │   BYO bucket (S3 / R2 / Google Drive)       │
  ┌────────────┐        │   ── stores opaque, content-addressed,      │
  │ local .dna │◀──────▶│      encrypted chunks (blob = ciphertext)   │
  │  (Prolly)  │        │   ── no plaintext, no readable metadata     │
  └────────────┘        └────────────────────────────────────────────┘
        │                          ▲                    ▲
        │ encrypted chunks         │ push/pull          │ push/pull
        ▼                          │                    │
  ┌────────────┐         ┌─────────┴──────────┐   ┌─────┴──────┐
  │ optional   │◀───────▶│  device B          │   │  device C  │
  │ THIN RELAY │ presence│  (CRDT replica)    │   │ (CI agent) │
  │ NAT/notify │ + chunks└────────────────────┘   └────────────┘
  └────────────┘
   moves only content-addressed *encrypted* chunks; never plaintext
```

**Two interchangeable transports:**

| Transport | Role | Default? | What it sees |
|-----------|------|----------|--------------|
| **BYO bucket** (S3 / R2 / Drive) | Durable store of encrypted, content-addressed chunks. | ✅ default | Opaque ciphertext blobs keyed by hash. Nothing else. |
| **Thin relay** | Optional dumb pipe for **NAT traversal** + **presence/notify** when devices can't reach a shared bucket or want low-latency push. | ❌ opt-in | Only **content-addressed encrypted chunks** in transit. No accounts of plaintext, no key material. |

Design choices, mirroring Tarsnap (client-side crypto + dedup on S3) and litestream/dolt (BYO object storage):

- **Content-addressed chunks.** Each chunk's key = hash of its *ciphertext*. → dedup across versions/devices, cheap incremental upload, and tamper-evidence (a wrong byte → wrong address).
- **Wrap, don't re-encrypt.** A random per-archive/per-chunk data key is wrapped by the account key (see §3). The relay/bucket never touches an unwrapped key — same pattern Tarsnap uses with per-archive keys wrapped by an RSA key (https://www.tarsnap.com/crypto.html).
- **The relay is a dumb pipe.** It moves chunks and fans out presence pings. It performs **no merge, no decryption, no validation of contents**. All merge logic is client-side. Killing the relay degrades to bucket-only sync; killing the bucket degrades to local-only.

---

## 3. Key model for sync — two-secret derivation

We adopt **1Password-style two-secret key derivation** (https://agilebits.github.io/security-design/deepKeys.html). The account encryption key is derived from **two** independent inputs:

```
  account passphrase  ──┐
   (human-memorable,    │
    low entropy)        ├──▶  KDF (Argon2id, m=19–64MiB, t=1–3, p=1)
                        │           │
  Secret Key           ──┘           ▼
   (128-bit+, machine-     Account Key ──▶ wraps ──▶ random Data Keys
    generated, never                                      │
    typed/transmitted)                                    ▼
                                              XChaCha20-Poly1305 over chunks
```

**Why two secrets.** The passphrase alone is low-entropy and crackable offline if the server is breached. Mixing in a **high-entropy Secret Key** (generated on-device, never sent to the server, stored in the local keychain / written to the recovery sheet) means server-held blobs are **useless for offline brute force** — an attacker must compromise a *device*, not just the server. This is precisely 1Password's rationale, and it is why Helix's encrypted blobs resist offline cracking even with a weak passphrase.

**Crypto primitives** (shared with the `.dna` format — see [.dna Format](DNA_FORMAT.md) and [Security](SECURITY_MODEL.md)):

| Concern | Choice | Why |
|---------|--------|-----|
| AEAD | **XChaCha20-Poly1305** (libsodium `secretstream`) | 192-bit nonce → random nonces are collision-safe without a counter; portable, no AES-NI dependency (https://doc.libsodium.org/secret-key_cryptography/aead, https://en.wikipedia.org/wiki/ChaCha20-Poly1305). |
| Streaming framing | **age STREAM**: ChaCha20-Poly1305 over **64 KiB** chunks | Bounded memory, chunk-level integrity, standard framing (https://github.com/C2SP/C2SP/blob/main/age.md). |
| KDF | **Argon2id**, m=19–64 MiB, t=1–3, p=1 | OWASP-recommended memory-hard params (https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). |
| Key handling | **Wrap-don't-encrypt** | Random data key wrapped by passphrase / OS keychain / recovery code / hardware token. Rotate the wrapper without re-encrypting data. |
| Integrity + authenticity | **detached Ed25519 over a BLAKE3 Merkle root** | Offline-verifiable tamper-evidence without any blockchain (https://github.com/sigstore/sigstore/issues/122). |

**No chain.** Systems like Walrus add on-chain availability certificates + RedStuff erasure coding for *decentralized availability* (https://arxiv.org/abs/2505.05370). Helix needs **integrity + authenticity of a file you already hold**, not decentralized availability — so we **drop the chain** and keep only the signed Merkle root. Smaller, cheaper, $0-default.

---

## 4. Prior art

| System | E2E model | Key derivation | Storage | What we borrow |
|--------|-----------|----------------|---------|----------------|
| **Obsidian Sync** | E2E by default; user holds password, server stores opaque blobs (https://help.obsidian.md/Obsidian+Sync/Security+and+privacy) | passphrase | vendor relay | "server stores opaque blobs"; E2E as default |
| **Standard Notes (004)** | XChaCha20-Poly1305 items + Argon2 password; versioned protocol (https://standardnotes.com/help/security/encryption) | Argon2 | vendor | exact AEAD + KDF combo; **versioned** protocol |
| **1Password** | two-secret: account password + high-entropy Secret Key; all keys client-side (https://agilebits.github.io/security-design/deepKeys.html) | passphrase + Secret Key | vendor | **two-secret derivation** (§3) |
| **Tarsnap** | client-side AES-256 per-archive keys wrapped by RSA key; client-side dedup (https://www.tarsnap.com/crypto.html) | key file | on S3 | wrap-don't-encrypt; client-side dedup; **on S3** |
| **litestream / dolt** | — | — | BYO object storage | **BYO bucket** as the default backend |

---

## 5. The merge model

### 5.1 Why NOT last-write-wins

LWW picks a winner by timestamp and **silently discards the loser**. For a memory layer that is catastrophic: two agents concurrently learning two *different true facts* (e.g., "prefers tabs" on device A, "deploys via Fly.io" on device B) is not a conflict — it's two facts. LWW destroys one. **We reject LWW as the default.** LWW is permitted only for genuinely single-valued, last-observation-wins fields (e.g., a UI cursor position), never for facts.

### 5.2 Two-layer merge: mechanical convergence + semantic resolution

```
  ┌──────────────────────────────────────────────────────────────────┐
  │ LAYER 1 — CRDT (mechanical)                                        │
  │   op-based CRDT → all replicas converge byte-for-byte.             │
  │   Handles: sets, registers, sequences, structural concurrency.     │
  │   Guarantee: no lost ops, deterministic convergence.               │
  └───────────────────────────────┬──────────────────────────────────┘
                                   │ surfaces contradictions
                                   ▼
  ┌──────────────────────────────────────────────────────────────────┐
  │ LAYER 2 — 3-way SEMANTIC merge (business logic)                    │
  │   git-style 3-way at the FACT / FIELD level using the commit-DAG   │
  │   merge-base (lowest common ancestor).                             │
  │   Handles: contradictory facts that need domain rules.             │
  │   Output: keep-both / supersede / flag-for-review.                 │
  └──────────────────────────────────────────────────────────────────┘
```

**Layer 1 — CRDT.** CRDTs come in state-based (CvRDT) and op-based (CmRDT) flavors, plus delta-CRDTs, coordinated by vector clocks / dotted version vectors (https://mattweidner.com/2023/09/26/crdt-survey-3.html). Helix uses an **op-based CRDT** so replicas converge mechanically with full operation history.

| Library | Size | History | Trade-off |
|---------|------|---------|-----------|
| **Yjs** | ~18 kB | aggressive GC | Leaner, dominates at scale, but limited GC story and **can lose data on conflicting structural edits** (https://www.pkgpulse.com/guides/yjs-vs-automerge-vs-loro-crdt-libraries-2026). |
| **Automerge** | Rust/WASM ~320 kB | **keeps FULL history**, ~30% overhead (<1 byte/char) | Heavier, but provenance is preserved (https://automerge.org/blog/automerge-2/). |

**Decision: Automerge (op-based).** When **provenance is the product** — and for a memory/audit layer it is — keeping full history at ~30% overhead (sub-byte per character) is the right trade. Yjs's structural-edit data loss is disqualifying for facts.

**Layer 2 — 3-way semantic merge.** CRDTs can assume a *git-like versioned store* that supplies the **lowest common ancestor** for a 3-way merge (https://mattweidner.com/2023/09/26/crdt-survey-2.html, MRDTs). Helix's commit-DAG provides exactly this merge-base. For **contradictory facts** that mechanical convergence can't adjudicate, we run a git-style 3-way merge **at the fact/field granularity** against the merge-base, then apply domain rules: keep-both (concurrent independent facts), supersede (one strictly refines the other), or flag-for-review (genuine contradiction → §8).

### 5.3 Bi-temporal modeling (ADR-013)

Every fact carries **two** time axes (XTDB model, https://v1-docs.xtdb.com/concepts/bitemporality/):

| Axis | Meaning |
|------|---------|
| **valid-time** | When the fact is/was true *in the world*. |
| **transaction-time** | When Helix *learned/recorded* it. |

> "John lived in X" — **valid** 1990–1995, **recorded** 2026.

**Invalidation is append-only — never delete.** Superseding a fact appends an invalidation record; the old row stays. This yields audit, point-in-time rollback ("what did we believe on date D?"), and invalidation **without destroying data**. It also means merge never deletes — it only appends — which keeps Layers 1 and 2 monotonic and convergent.

### 5.4 Content-addressed Prolly / Merkle store

The `.dna` store is a **content-addressed Prolly (probabilistic B-) tree over a Merkle structure**, the Dolt "git for data" model: version tables cell-wise, store **only deltas**, diff/merge structurally (https://docs.dolthub.com/introduction/getting-started/git-for-data). Cousins: TerminusDB's git-like graph DB (https://thenewstack.io/terminusdb-takes-on-data-collaboration-with-a-git-like-approach/) and Git's own objects/packfiles/3-way-against-merge-base.

Mapping to Helix:

| Git / Dolt | Helix |
|------------|-------|
| commit | a **signed Merkle root** of the `.dna` store |
| checkout earlier commit | **rollback** = check out an earlier signed root |
| merge-base | lowest common ancestor in the commit-DAG for **3-way** merge |
| packfile delta | **structural sharing** → cheap incremental `.dna` exports |

Structural sharing is what makes the whole system cheap: unchanged subtrees share hashes, so incremental exports, diffs, and merges touch only what changed — fast diff/merge and small sync deltas.

---

## 6. "Review team memory like code" — PR-style flow

Team sync does **not** auto-trust incoming memory. It lands as a reviewable change set:

```
  teammate / agent push ─▶ encrypted chunks ─▶ your device decrypts
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │  Pending change set (a PR over memory)        │
  │   diff:  + 3 facts   ~ 1 superseded   - 0     │
  │   [ approve ]   [ revert ]   [ inspect ]      │
  └─────────────────────────────────────────────┘
        │ approve            │ revert
        ▼                    ▼
   merged into HEAD     dropped (append-only; nothing lost)
```

- **Diff / approve / revert** at the fact level, against the merge-base.
- **Anti-poisoning by construction.** Because untrusted memory is *proposed*, not *applied*, the review gate is the primary defense against memory-poisoning: a malicious or hallucinated fact is a diff line you can reject before it touches HEAD. Revert is cheap and lossless (append-only bi-temporal model, §5.3). See [Security](SECURITY_MODEL.md).

---

## 7. Conflict UX

| Situation | Mechanical (Layer 1) | Semantic (Layer 2) | User sees |
|-----------|----------------------|--------------------|-----------|
| Concurrent edits, independent fields | auto-merge | — | nothing (silent convergence) |
| Two concurrent *different* facts | both retained | keep-both | both facts, badged "concurrent" |
| One fact refines another | both retained | supersede (append invalidation) | newest, with "history" affordance |
| Direct contradiction | both retained | **flag-for-review** | conflict card: base ⟂ ours ⟂ theirs, pick/keep-both/edit |
| Structural concurrency | CRDT resolves | — | nothing |

Conflicts are **never destructive** — both sides are always recoverable from history. The 3-way conflict card shows **base / ours / theirs** drawn from the merge-base, exactly like a git merge conflict.

---

## 8. Opinionated decisions

| # | Decision | Rationale | ADR |
|---|----------|-----------|-----|
| D1 | **Sync is optional, off by default.** | Protects local-first + `$0-default`. | ADR-022 |
| D2 | **E2E by default; server sees only ciphertext.** | Untrusted-remote threat model. | ADR-022 |
| D3 | **BYO bucket (S3/R2/Drive) is the default backend.** | No mandatory server → $0. | ADR-022 |
| D4 | **Thin relay is opt-in, dumb-pipe only.** | NAT/presence without trusting it. | ADR-022 |
| D5 | **Two-secret key derivation (passphrase + Secret Key).** | Server blobs resist offline cracking. | ADR-022 |
| D6 | **XChaCha20-Poly1305 + Argon2id + age-STREAM (64 KiB).** | Portable, nonce-safe, memory-hard, standard. | ADR-022 |
| D7 | **Reject LWW for facts.** | LWW destroys concurrent facts. | ADR-021 |
| D8 | **Automerge op-based CRDT (full history).** | Provenance is the product; Yjs loses structural edits. | ADR-021 |
| D9 | **Git-style 3-way semantic merge via commit-DAG merge-base.** | Business logic for contradictions. | ADR-021 |
| D10 | **Bi-temporal, append-only; invalidation never deletes.** | Audit + rollback + lossless revert. | ADR-013 |
| D11 | **Signed BLAKE3 Merkle root; no blockchain.** | Integrity/authenticity of a held file, not decentralized availability. | ADR-022 |
| D12 | **PR-style review of incoming team memory.** | Anti-poisoning control. | ADR-021 |

---

## 9. Failure modes

| Failure | Behavior | Recovery |
|---------|----------|----------|
| Relay down | Degrade to bucket-only sync. | Automatic; no data impact. |
| Bucket down/unreachable | Degrade to local-only; queue chunks. | Resume on reconnect; content-addressing dedups the backlog. |
| Stale/withheld chunk | Detected: address ≠ content, or signed root won't verify. | Refetch; refuse to advance HEAD to an unverifiable root. |
| Malicious chunk mutation | Hash mismatch → rejected. | Refetch from another replica/bucket. |
| Forged commit | Ed25519 signature over Merkle root fails. | Reject; never merged. |
| Lost passphrase | Account Key underivable. | **Recovery code** (wrapped data key) restores access; without it, data is unrecoverable by design. |
| Lost Secret Key | Cannot complete two-secret derivation. | Restore from recovery sheet / another enrolled device. |
| Memory poisoning attempt | Lands as a *pending* diff, not applied. | Reject in PR review (§6); HEAD untouched. |
| Concurrent contradictory facts | Both retained; flagged. | Resolve via conflict card (§7); nothing lost. |
| Clock skew across devices | Bi-temporal transaction-time + DAG causality, not wall-clock, orders merges. | No LWW dependence → skew can't silently drop facts. |
| Partial upload / crash mid-sync | Content-addressed chunks are idempotent; commit (root) is atomic. | Re-push; only missing chunks transfer. HEAD advances only on a complete, verified root. |

---

## Sources

- ChaCha20-Poly1305 — https://en.wikipedia.org/wiki/ChaCha20-Poly1305
- libsodium AEAD / secretstream — https://doc.libsodium.org/secret-key_cryptography/aead
- age spec (STREAM, 64 KiB chunks) — https://github.com/C2SP/C2SP/blob/main/age.md
- OWASP Password Storage (Argon2id params) — https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- Sigstore: signed Merkle root discussion — https://github.com/sigstore/sigstore/issues/122
- Walrus (on-chain availability + RedStuff) — https://arxiv.org/abs/2505.05370
- Obsidian Sync security & privacy — https://help.obsidian.md/Obsidian+Sync/Security+and+privacy
- Standard Notes encryption (004) — https://standardnotes.com/help/security/encryption
- 1Password two-secret key derivation — https://agilebits.github.io/security-design/deepKeys.html
- Tarsnap crypto — https://www.tarsnap.com/crypto.html
- CRDT survey, part 3 (CvRDT/CmRDT, delta, version vectors) — https://mattweidner.com/2023/09/26/crdt-survey-3.html
- CRDT survey, part 2 (MRDTs, git-like LCA / 3-way) — https://mattweidner.com/2023/09/26/crdt-survey-2.html
- Automerge 2.0 (full history, ~30% overhead) — https://automerge.org/blog/automerge-2/
- Yjs vs Automerge vs Loro (2026) — https://www.pkgpulse.com/guides/yjs-vs-automerge-vs-loro-crdt-libraries-2026
- XTDB bitemporality — https://v1-docs.xtdb.com/concepts/bitemporality/
- Dolt "git for data" — https://docs.dolthub.com/introduction/getting-started/git-for-data
- TerminusDB git-like data collaboration — https://thenewstack.io/terminusdb-takes-on-data-collaboration-with-a-git-like-approach/
