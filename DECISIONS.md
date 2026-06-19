# Decisions (Architecture Decision Record)

This is the running log of every meaningful decision on Helix — and, crucially, **when a
decision changes, why it changed**. Each entry is an ADR. Newest decisions are appended at
the bottom. Status is one of `Proposed`, `Accepted`, `Superseded by ADR-XXX`, `Deprecated`.

> Format per [Michael Nygard's ADR template](https://github.com/joelparkerhenderson/architecture-decision-record).
> If you reverse or amend a decision, **do not edit the old entry** — add a new one and
> mark the old one `Superseded`.

---

## ADR-001 — Product concept: a local-first, portable, git-like memory layer for coding agents
**Status:** Accepted · **Date:** 2026-06-18

**Context.** The user wants to build an "AI agent memory transfer" product inspired by
Walrus Memory ("take your AI's memory anywhere") and the broader Mem0/OpenMemory space,
but *bigger* and useful for everyday coding. Research findings:
- *Walrus Memory*: portable, encrypted, verifiable memory on decentralized storage; SDK-first.
- *Mem0/OpenMemory*: universal memory layer, MCP-compatible, fact extraction with
  ADD/UPDATE/DELETE/NOOP operations, vector + graph stores; OpenMemory adds a local store + dashboard.
- *MCP* is now the de-facto "USB-C for AI," with 200+ community servers by Q2 2026.

**Decision.** Build **Helix**: a memory layer that is (1) **coding-agent-first** (models
repos, stacks, conventions, decisions as first-class types), (2) **local-first** (runs
fully offline, the user owns the data), (3) **git-like portable** (a single signed,
encrypted `.dna` strand you can export/import/merge/branch/rollback), and (4) **near-zero
cost** (local embeddings + free-tier-first LLM router). MCP is the primary interface.

**Why founders/users love it.** It's the one thing the incumbents don't combine: vendor
portability *plus* local ownership *plus* coding-native depth *plus* git-like ergonomics
*plus* free to run. It's a wedge (developers, MCP) into a platform (any agent, any user).

**Consequences.** We avoid the blockchain/decentralized-storage complexity Walrus takes on
(simpler, cheaper, offline). We must invest in a robust portable format and merge semantics.

**Alternatives considered.**
- *Cloud-first SaaS memory* (like hosted Mem0): rejected — contradicts "user owns memory"
  and adds cost; we keep an *optional* cloud sync but never require it.
- *Decentralized/blockchain storage* (like Walrus): rejected for v1 — heavy, costly,
  unnecessary for the core value; revisit as an optional backend (see ADR-010).

---

## ADR-002 — Brand name: "Helix"; portable artifact: the `.dna` strand
**Status:** Accepted · **Date:** 2026-06-18

**Context.** The GitHub repo is `Agent-DNA-Transfer`. We want a memorable, ownable brand
that fits the "DNA / transfer" metaphor and reads well to founders.

**Decision.** Product brand = **Helix** (the double helix = two strands of memory). The
portable memory bundle = a **`.dna` strand**. CLI verb set is git-like (`init`, `clone`,
`push`, `pull`, `merge`, `log`). The MCP server command = `helix-mcp`. PyPI distribution names use the `helix-dna-*` family
(meta = `helix-dna`); the import packages stay `helix_core`/`helix_cli`/`helix_mcp`/`helix_sdk`
and the CLI command stays `helix`. (`helix-memory`/`helix-cli`/`helix-mcp` were taken on PyPI.)

**Consequences.** "Helix" is a common word; **trademark/availability check is a TODO before
any public launch** (tracked in ROADMAP). The repo name `Agent-DNA-Transfer` stays as the
descriptive umbrella; "Helix" is the product within it.

**Alternatives considered.** *Mnema*, *Synapse*, *Cortex*, *Recall*, *Genome*. Helix won on
metaphor fit + memorability. This decision is explicitly reversible — see CLAUDE rule
"specs before code"; renaming later is a find-and-replace + ADR.

---

## ADR-003 — Primary interface is the Model Context Protocol (MCP)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** We need to reach *every* agent (Claude Code, Cursor, Copilot, Windsurf,
ChatGPT desktop, Gemini) without bespoke integrations per tool.

**Decision.** Expose memory through a small, stable **MCP server**. Agents get tools
(`memory.search`, `memory.write`, `memory.forget`, ...) and resources (the memory graph).
Anything an agent can do flows through MCP. Native plugins/adapters are thin wrappers.

**Consequences.** We inherit MCP's portability and its constraints (tool-call latency,
schema limits). We must keep the surface minimal and versioned. Non-MCP agents are reached
via the SDK or CLI export/import as a fallback.

---

## ADR-004 — Language & runtime: Python 3.11+ core, managed with `uv`
**Status:** Accepted · **Date:** 2026-06-18

**Context.** The AI/ML and embeddings ecosystem (fastembed, sentence-transformers,
litellm, sqlite-vec bindings) is richest in Python; the user has OpenAI/Gemini keys.

**Decision.** Core engine, CLI, and MCP server in **Python 3.11+**, managed with **`uv`**
(fast, reproducible). Dashboard and TS SDK in TypeScript. This is a polyglot monorepo.

**Consequences.** Two toolchains to maintain. Justified: Python for AI core, TS for UI.
Distribution via `pipx`/`uv tool` for the CLI; the MCP server ships in the same package.

**Alternatives considered.** *All-TypeScript* (single toolchain, great MCP SDK): rejected —
weaker local-embeddings/ML story. *Rust core* (perf, single binary): rejected for v1 —
slower iteration; revisit for a hot-path rewrite if profiling demands it.

---

## ADR-005 — Storage: the strand is a single SQLite file (`sqlite-vec` + relational graph)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** "Portable single file" and "local-first" demand an embedded store with no
server. We need vectors *and* a graph.

**Decision.** Each strand is **one SQLite database**. Vectors live in **`sqlite-vec`**
virtual tables; the knowledge graph (nodes/edges/attributes) lives in normal relational
tables; graph algorithms run on **NetworkX** projections in memory. The `.dna` export wraps
this DB + a signed manifest (see ADR-008).

**Consequences.** Trivially portable (copy a file), transactional, offline. Scales to
~10⁵–10⁶ memories per user comfortably — well beyond an individual's needs. For very large
team strands we may add an optional server-backed store (ADR-010), but SQLite is the default.

**Alternatives considered.** *Chroma/LanceDB*: fine, but sqlite-vec keeps everything in one
portable file with zero extra processes. *Postgres+pgvector*: rejected as default (requires
a server); offered as an optional backend for teams.

---

## ADR-006 — Embeddings: local-by-default (`fastembed` / bge-small), cloud optional
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Cost requirement: default to **$0**. Embeddings are the highest-volume model
call; doing them in the cloud is the main cost driver.

**Decision.** Default embeddings run **locally** via `fastembed` with
`BAAI/bge-small-en-v1.5` (384-dim, fast on CPU, no API). Cloud embeddings
(Gemini `text-embedding-004` free tier, OpenAI `text-embedding-3-small`) are opt-in for
users who want higher quality and don't mind a key. Dimension is recorded per-strand so a
strand never mixes embedding spaces silently; switching providers triggers a re-embed.

**Consequences.** First run downloads a ~130MB model (cached). Zero ongoing cost. Quality is
slightly below large cloud embeddings but more than sufficient for personal memory recall.

---

## ADR-007 — LLM router: free-tier-first (Gemini 2.0 Flash → gpt-4o-mini), and *optional*
**Status:** Accepted · **Date:** 2026-06-18

**Context.** The user prefers a free Gemini key if it suffices, else their paid
`gpt-4o-mini`. LLM calls are needed for fact extraction, consolidation, and conflict
resolution — but not for every message.

**Decision.** A **LiteLLM-based router** with this policy:
1. **Heuristic pre-filter first** — cheap local rules decide if an LLM call is even needed
   (most messages don't produce new durable facts). No model call → no cost.
2. **Default model = Gemini 2.0 Flash** (free tier) for extraction/consolidation.
3. **Fallback = gpt-4o-mini** when Gemini is unavailable/rate-limited or the user prefers it.
4. **Response cache** keyed by a hash of the prompt+inputs so identical work is never paid
   for twice.
5. **Structured JSON output** to minimize tokens; batched extraction across turns.
The LLM is **optional**: with no key, Helix uses a deterministic local extractor (regex +
embeddings + rules) — lower recall, still $0, still useful.

**Consequences.** Default cost stays ~$0 (free tier + heuristics + cache). Quality scales up
smoothly if the user adds a key. We must implement and test the no-LLM path as a first-class
mode, not an afterthought.

**Alternatives considered.** *Always-on cloud LLM per message*: rejected — expensive and
unnecessary. *Local LLM (Ollama) for extraction*: kept as a **third option** for power users
who want better-than-heuristic extraction at $0 with no cloud (see ROADMAP).

---

## ADR-008 — `.dna` portable format: signed + encrypted + versioned bundle
**Status:** Accepted · **Date:** 2026-06-18

**Context.** The headline feature is "take your memory anywhere." That artifact must be
secure, verifiable, and mergeable.

**Decision.** A `.dna` file is a bundle (zip/tar) containing: the SQLite strand, a JSON
**manifest** (schema version, embedding model+dim, counts, content hashes), and a
**detached Ed25519 signature** over the manifest. Contents are encrypted with
**XChaCha20-Poly1305** using a key derived from the user's passphrase (Argon2id) or device
key. Strands carry a monotonically increasing version and a content-hash history enabling
**diff / merge / rollback** (git-like). Full spec: [`docs/DNA_FORMAT.md`](docs/DNA_FORMAT.md).

**Consequences.** Integrity is independently verifiable (signature) like Walrus, without a
blockchain. Merging two people's memories requires conflict resolution (CRDT-ish rules +
LLM-assisted tie-breaks) — non-trivial, specified in the format/TSD docs.

---

## ADR-009 — License: Apache-2.0
**Status:** Accepted · **Date:** 2026-06-18

**Context.** We want broad adoption, contributor confidence, and a patent grant suitable
for a startup that may commercialize hosted/team features.

**Decision.** **Apache-2.0** for the open-source engine, CLI, MCP server, and SDKs. Future
hosted/team offerings may be a separate commercial layer (open-core), recorded in a later ADR.

**Alternatives considered.** *MIT* (simpler, no patent grant) — viable but Apache's patent
clause is safer for a venture-backed path. *AGPL* (forces hosted forks open) — rejected as
too restrictive for an SDK/library meant to be embedded widely.

---

## ADR-010 — Optional pluggable backends (deferred, not in v1)
**Status:** Proposed · **Date:** 2026-06-18

**Context.** Some users/teams will want server-backed or decentralized/verifiable storage.

**Decision (proposed).** Keep storage behind an interface so we can later offer optional
backends — Postgres+pgvector (teams), and a Walrus/decentralized-storage adapter
(verifiable, censorship-resistant) — *without* changing the local-first default. Not built
in v1; the interface is designed now so we don't paint ourselves into a corner.

---

## ADR-011 — Repo is spec-first; scaffold precedes implementation
**Status:** Accepted · **Date:** 2026-06-18

**Context.** This is a very large project (target: a real open-source/startup-grade
codebase). Building blind invites churn.

**Decision.** Write the PRD, TSD, System Architecture, memory/format/security/cost specs,
and a monorepo scaffold **first**; implement against them in phases (see ROADMAP). Code and
docs must never disagree — a change that contradicts a doc updates the doc in the same PR.

**Consequences.** Slower start, far less rework, and any contributor (human or AI) shares a
single source of truth. Pre-alpha packages may be stubs; the structure is authoritative.

---

---

# Wave 2 — research-driven decisions (2026-06-18)

The following ADRs were added after a seven-stream deep-research pass (competitive
landscape, memory science, retrieval SOTA, storage/infra, crypto/sync/CRDT, MCP/
integrations, privacy/eval/business). They deepen — and in a few places refine — the
foundational ADRs above. Each cites the dossier that grounds it; see [`docs/RESEARCH.md`](docs/RESEARCH.md)
for the consolidated survey and sources.

## ADR-012 — Memory taxonomy: episodic / semantic / procedural + an entity graph; CLS two-stage
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Generic memory layers store undifferentiated "facts." Cognitive science
distinguishes memory types with different retrieval triggers, decay rates, and consolidation
paths; the Complementary Learning Systems (CLS) framework explains a fast episodic store that
trains a slow semantic store by replay.

**Decision.** Helix's long-term memory has four first-class shapes: **episodic** (event log),
**semantic** (durable facts), **procedural** (skills/playbooks), and a cross-cutting
**entity-relationship graph**. Our coding-native types (project, decision, convention,
snippet, …) map onto these. The live agent context window is **working memory** and is never
the system of record. Writes follow a **two-stage CLS** path: cheap fast episodic capture
online; slow generalizing **consolidation** offline. Full spec: [`docs/MEMORY_MODEL.md`](docs/MEMORY_MODEL.md), [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md).

**Consequences.** Richer schema and a background consolidation process to build/maintain;
in return, recall is sharper and storage is compressed (ten episodes → one semantic rule).

**Supersedes/refines** ADR-001's memory shape (which listed flat types). Alternatives: a
single flat fact table (rejected — loses type-specific decay/retrieval).

## ADR-013 — Bi-temporal fact model (valid-time + transaction-time)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Facts change ("we moved billing to Postgres", "Priya left the team"). Deleting or
overwriting loses the audit trail and breaks rollback/merge.

**Decision.** Every fact carries **valid-time** (when it is true in the world) and
**transaction-time** (when Helix learned it), the XTDB/Graphiti model. Invalidation is
**append-only**: a superseded fact is closed, never deleted. This powers contradiction
handling, point-in-time queries, rollback, and conflict-aware merge. See [`docs/SYNC.md`](docs/SYNC.md), [`docs/MEMORY_MODEL.md`](docs/MEMORY_MODEL.md).

**Consequences.** More storage and slightly more complex queries; gains audit, time-travel,
and a clean basis for merge. Source: Graphiti/Zep (arxiv 2501.13956), XTDB bitemporality.

## ADR-014 — Decay & reinforcement: per-type exponential decay + SM-2-style reinforcement
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Memory must stay sharp as it grows; the Ebbinghaus forgetting curve and spaced
repetition give proven models.

**Decision.** Compute salience at retrieval time as `importance · e^(−λ·Δt_last_access)` with
per-type half-lives (episodic ~7d, procedural ~90d, semantic ~non-decaying until
contradicted; `λ = ln2/half_life`). On successful recall, **reinforce** SM-2-style (grow the
effective half-life via an easiness factor, clamp ≥ 1.3; reset Δt). Below a salience floor a
memory is archived/consolidated, **never auto-deleted**. Details: [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md).

**Consequences.** No cron needed (decay is computed on read); frequently-useful memories
become near-permanent. Sources: Ebbinghaus, SuperMemo SM-2, Stanford Generative Agents.

## ADR-015 — Reflection trees + sleep-time consolidation
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Raw episodes alone don't yield higher-level understanding ("this codebase prefers
composition over inheritance"); doing that work on the hot path would add latency and cost.

**Decision.** Adopt Generative-Agents **reflection** (when accumulated importance exceeds a
threshold, synthesize higher-level insights stored as first-class memories linked to their
source episodes) and **sleep-time consolidation** (a background worker runs during idle time,
using a stronger/slower model since it isn't latency-bound). Both are off the query hot path.

**Consequences.** Better semantic/procedural memory over time; requires an idle-time scheduler
and careful anti-hallucination guards (ADR-029). Sources: Generative Agents (2304.03442),
MemGPT (2310.08560), Letta sleep-time compute.

## ADR-016 — Retrieval pipeline: hybrid + RRF + graph PPR + MMR, with NO LLM on the hot path
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Recall must be p95 < 150 ms on CPU at $0 over 10⁵–10⁶ items. Query-time LLM
expansion (HyDE/Query2doc) costs 2000 ms+; CPU cross-encoder reranking of top-100 is
impossible (65–195× slower than GPU).

**Decision.** Default pipeline: query-embed → embedding **router/scope** (skip-retrieval when
appropriate) → **hybrid retrieve** (dense + BM25) → **RRF fuse (k=60)** → **graph expansion**
via Personalized PageRank / bounded traversal (HippoRAG-style) → multi-signal **ranking** →
**MMR** dedup/diversity → **token-budgeted packing** (most-salient at head and tail to beat
"lost in the middle"). All LLM work is pushed to **ingest time**. An optional high-quality
tier adds late-interaction reranking (answerai-colbert-small) or an int8 cross-encoder on
top-20–30, and HyDE/multi-query async. Full spec: [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md).

**Consequences.** Fast, cheap, offline recall. Keep BM25 always (personal memory is full of
identifiers/paths BM25 must catch). Sources: Cormack RRF (SIGIR'09), HippoRAG (2405.14831),
"Lost in the Middle" (2307.03172), MMR (Carbonell & Goldstein 1998).

## ADR-017 — Embeddings: bge-small-en-v1.5 (int8) default; Matryoshka upgrade tier; quantization
**Status:** Accepted · **Date:** 2026-06-18 · **Refines ADR-006**

**Decision.** Default local embedding = **BAAI/bge-small-en-v1.5** (384-dim, 33M, MTEB 62.17,
best-in-small-class) via fastembed ONNX, stored **int8-quantized** (4× smaller, ~99% recall
with rescoring). Upgrade tier = **mxbai-embed-large-v1** or **arctic-embed-l-v2.0**
(Matryoshka-truncatable dims, multilingual), with **binary quantization + float rescore** at
scale (32× smaller). Embedding space (provider/model/dim/quantization) stays pinned per strand
(ADR-006); switching triggers a tracked re-embed. Details: [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md).

**Consequences.** $0 high-quality recall on CPU; a clean quality ladder. Source: MTEB,
HuggingFace embedding-quantization, Nomic/Arctic Matryoshka.

## ADR-018 — Storage confirmed: sqlite-vec brute-force in one file; Kùzu rejected; store interface
**Status:** Accepted · **Date:** 2026-06-18 · **Refines ADR-005**

**Context.** Benchmarks confirm sqlite-vec brute-force is fast enough at our scale with
quantization (17–41 ms @1M); **Kùzu (the embedded graph DB we might have used) was
abandoned/archived Oct 2025**; DuckDB-VSS HNSW persistence is experimental (no WAL recovery →
corruption risk).

**Decision.** Default store stays **one SQLite file**: `sqlite-vec` vectors (brute-force +
int8/binary quantization) + **relational node/edge tables with recursive CTEs**, NetworkX
projections for richer graph work. **Do not adopt upstream Kùzu**; if a graph engine is ever
needed, use a maintained fork behind the interface. Everything sits behind a `MemoryStore`
interface with a team-scale upgrade path (LanceDB → pgvector → Qdrant). Before exporting a
`.dna`, **checkpoint WAL + atomic-rename** so the artifact is a single self-contained file.
Sources/benchmarks: [`docs/RESEARCH.md`](docs/RESEARCH.md).

**Consequences.** Maximum portability + transactional safety with no dependency-abandonment
risk; ANN/graph engines remain optional, isolated behind the interface.

## ADR-019 — Crypto suite for `.dna`: XChaCha20-Poly1305 secretstream, Argon2id, BLAKE3 Merkle, Ed25519, wrap-don't-encrypt
**Status:** Accepted · **Date:** 2026-06-18 · **Refines ADR-008**

**Decision.** Encrypt the strand with **XChaCha20-Poly1305** via libsodium **secretstream**
over **64 KiB chunks** (truncation-resistant, portable, random-nonce-safe). Derive keys with
**Argon2id** (desktop params, start m=64 MiB, t=3, p=1). Use **wrap-don't-encrypt**: a random
data key encrypts the payload and is itself wrapped by the passphrase/keychain/recovery/
hardware key (enables re-keying + multi-factor unlock). Integrity via a **BLAKE3 Merkle tree**
over content-addressed chunks; **Ed25519** detached signature over the Merkle root, verified
on import. This makes `.dna` **independently verifiable offline, with no blockchain** (we keep
Walrus's verifiability, drop the chain). Spec: [`docs/DNA_FORMAT.md`](docs/DNA_FORMAT.md), [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

**Consequences.** Strong, portable, offline-verifiable artifact; chunked AEAD enables seekable
incremental exports. Sources: libsodium, C2SP `age` STREAM, OWASP Argon2id, BLAKE3.

## ADR-020 — Key management & recovery: keychain + passphrase + recovery code + optional Shamir/hardware
**Status:** Accepted · **Date:** 2026-06-18

**Decision.** Daily unlock via the **OS keychain** (macOS Keychain / Windows DPAPI / Linux
libsecret); portable fallback via **passphrase → Argon2id**. A high-entropy **recovery code**
independently wraps the data key (forgotten passphrase ≠ data loss). Optional **2-of-3 Shamir
secret sharing** and **hardware keys** (age-plugin-yubikey, passkeys/WebAuthn) for high-value
users/teams. Any one factor can unwrap the data key; losing one never loses data; losing all
does (true E2E). See [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

**Consequences.** Usable-but-strong default with a real recovery story. Sources: 1Password,
Standard Notes, Obsidian Sync, age-plugin-yubikey.

## ADR-021 — Merge strategy: CRDT convergence + git-style 3-way semantic merge + bi-temporal
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Merging two strands (over time, or across teammates) must not silently lose facts;
last-write-wins does exactly that.

**Decision.** Use an **Automerge-style CRDT** (op-based, full history) for mechanical
convergence of concurrent edits, **plus git-style 3-way semantic merge** at the fact/field
level (using the commit-DAG merge-base) for contradictory facts that need logic, resolved with
the **bi-temporal** model (ADR-013). Store is content-addressed (Prolly/Merkle, Dolt-style) so
diffs/merges are cheap and incremental. "Two facts meet" has one code path whether over time
or across people. Spec: [`docs/SYNC.md`](docs/SYNC.md).

**Consequences.** Conflict-aware, reversible, audit-preserving merge — the hardest and most
differentiating feature. Sources: Automerge, MRDTs, Dolt, XTDB.

## ADR-022 — Optional E2E sync: bring-your-own-storage first, two-secret derivation
**Status:** Proposed · **Date:** 2026-06-18 · **Refines ADR-010**

**Decision.** Team/multi-device sync is **optional and end-to-end encrypted**; any server/relay
sees only ciphertext. Default transport is **bring-your-own-bucket** (S3/R2/Drive) moving
content-addressed encrypted chunks; a thin relay is optional for NAT/presence. Adopt
**1Password-style two-secret derivation** (account passphrase + high-entropy Secret Key) so
stored blobs resist offline cracking. Not in v1; designed now so local-first stays the default.
Spec: [`docs/SYNC.md`](docs/SYNC.md).

## ADR-023 — MCP architecture: one local daemon + stdio shim; ~5 tools; token-budgeted results
**Status:** Accepted · **Date:** 2026-06-18 · **Refines ADR-003**

**Decision.** Run a long-lived **Streamable HTTP daemon on `127.0.0.1`** (shared store/cache
across concurrent agents) **plus a thin stdio shim** for clients that prefer stdio. Lead with
**Tools** (keep to ~5: `memory.search`, `memory.context`, `memory.write/add`, `memory.get`,
`memory.forget`; `memory.relate` optional), add **Resources** for read/browse; treat Prompts/
Sampling/Elicitation as optional enhancements (avoid hard deps on Sampling/Roots given draft
deprecation). **Token-budget every result** (`response_format` concise|detailed, `limit`/
`max_tokens`; default well under Claude Code's ~25k tool-output cap), **human-readable IDs**,
idempotent dedup/supersede writes, `isError`-in-result error handling, stable names +
`tools/list_changed`. Spec: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md), [`docs/MCP_INTEGRATION.md`](docs/MCP_INTEGRATION.md).

**Consequences.** One shared memory across all agents; a tiny, stable, context-friendly surface
no competitor token-budgets today. Sources: MCP spec 2025-06-18/11-25, Anthropic "writing
tools for agents."

## ADR-024 — Agent/MCP security posture: memory is the private-data leg of the lethal trifecta
**Status:** Accepted · **Date:** 2026-06-18

**Decision.** Treat Helix as the **private-data leg of the "lethal trifecta"** (private data +
untrusted content + exfiltration). Default **read-mostly**; require explicit consent for
cross-namespace reads or writes that could exfiltrate; bind to loopback + validate `Origin`;
non-deterministic session IDs; **treat returned memory text as untrusted** (sanitize so stored
content can't act as injected instructions); keep tool descriptions static and audited
(anti tool-poisoning/rug-pull); remote endpoints use OAuth 2.1 (PKCE, RFC 8707, no token
passthrough). See [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

**Consequences.** Hardened against the signature attacks on memory MCP servers. Sources:
Invariant Labs (tool poisoning), Simon Willison (lethal trifecta), MCP security best practices.

## ADR-025 — Redaction pipeline: tiered, at ingest AND outbound
**Status:** Accepted · **Date:** 2026-06-18 · **Refines ADR (redaction in TSD/Security)**

**Decision.** Redact with a tiered pipeline — regex/checksum → **entropy secret-scan
(detect-secrets + gitleaks)** → **Presidio NER** → mask — **before writing** to a strand
**and before any outbound LLM payload**, so "secrets never leave your machine" is literally
true. Redaction is defense-in-depth (no detector is complete), and is covered by tests
asserting no secret reaches a strand. Spec: [`docs/PRIVACY_COMPLIANCE.md`](docs/PRIVACY_COMPLIANCE.md).

**Consequences.** Strong privacy guarantee; some false positives (tunable). Sources: Microsoft
Presidio, Yelp detect-secrets, gitleaks.

## ADR-026 — GDPR posture: provenance-cascade erasure; never fine-tune on user memory
**Status:** Accepted · **Date:** 2026-06-18

**Decision.** Helix is **retrieval-only** — it never fine-tunes on user memory — avoiding the
unsolved machine-unlearning problem. Every derived artifact (embedding, summary, graph node)
carries a **provenance link** to its source record, so an erasure (GDPR Art. 17) is a
deterministic **cascade delete** of the record and everything derived from it. Local-first
keeps the user as sole controller (no processor relationship, no cross-border transfer). Spec:
[`docs/PRIVACY_COMPLIANCE.md`](docs/PRIVACY_COMPLIANCE.md).

**Consequences.** Clean, defensible "right to be forgotten." Source: EDPB Opinion 28/2024.

## ADR-027 — Evaluation: LongMemEval over LoCoMo; define the coding-agent memory benchmark
**Status:** Accepted · **Date:** 2026-06-18

**Decision.** Do **not** optimize for or trust vendor **LoCoMo** numbers (documented flaws;
full-context baseline beats specialized systems). Build the internal harness on
**LongMemEval** dimensions (extraction, multi-session, **temporal**, **knowledge-update**,
**abstention**) plus Helix-specific metrics (precision/recall@k, MRR, contradiction handling,
forget-cascade correctness, p50/p95 latency, tokens-per-retrieval, an adversarial poisoning
suite). **Define and publish a coding-agent memory benchmark** (the category gap) to own the
narrative. Spec: [`docs/EVALUATION.md`](docs/EVALUATION.md).

## ADR-028 — Business model: Apache-2.0 forever; never charge to read your own memory
**Status:** Accepted · **Date:** 2026-06-18 · **Refines ADR-009**

**Decision.** Keep the core **Apache-2.0 with a public no-relicense commitment** (permissive +
patent grant is what lets agent vendors/IDEs embed Helix; AGPL/SSPL/BSL would kill that GTM).
**Never charge to read your own local memory.** Monetize only true server-side infrastructure:
team sync, hosted encrypted backup/cross-device, org policy/audit/RBAC/SSO, managed cloud —
priced per-seat/per-org, not per-memory. The "review team memory like code" flow is the
primary paid trigger and growth loop. Spec: [`docs/BUSINESS.md`](docs/BUSINESS.md).

## ADR-029 — Anti-poisoning & memory-integrity guardrails
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Persistent memory poisoning (MINJA, MemoryGraft, Unit 42 on Bedrock) is the
signature attack on memory systems — temporally decoupled and self-reinforcing.

**Decision.** Every memory carries **provenance + confidence**; provenance distinguishes
**user-asserted vs agent-ingested** content. Ingested external content is untrusted and is
**injection-scanned before any durable write**. Consolidated facts must **cite ≥1 grounding
episode** (a validation gate against hallucinated memories). Contradictions are **flagged, not
silently overwritten** (bi-temporal, ADR-013). Memory is **human-reviewable and reversible**
(rollback), which doubles as the team-review feature. Spec: [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md), [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

## ADR-030 — Plugin/extension architecture
**Status:** Accepted · **Date:** 2026-06-18

**Decision.** Everything swappable sits behind a registered interface: `Embedder`,
`VectorStore`, `GraphStore`, `Extractor`, `LLMProvider`/router, `Redactor`, `AgentConnector`,
`SyncBackend`. Plugins are discovered via entry points. This is what makes the local→team
upgrade path (ADR-018), the embeddings ladder (ADR-017), and broad agent support possible
without touching the engine. Spec: [`docs/PLUGINS.md`](docs/PLUGINS.md).

---

## ADR-031 — Phase 3 LLM layer: stdlib provider clients; LiteLLM optional (refines ADR-007)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** ADR-007 specified a LiteLLM-based router. Implementing Phase 3, requiring LiteLLM
in the core path would add a heavy dependency and make the offline core un-installable on a
bare Python; it would also make the LLM path hard to unit-test without network/keys.

**Decision.** Implement the router over a small **Provider interface** with **dependency-free
stdlib `urllib`** clients for **Gemini** (free-tier-first), **OpenAI** (`gpt-4o-mini` fallback),
and **Ollama** (local, $0). A **FakeProvider** makes the entire LLM path testable offline. The
router adds a **SQLite response cache** (pay once), a **monthly token budget guardrail** that
caps *paid* usage and degrades to deterministic extraction when exhausted, and an
**LLMExtractor** that always falls back to the deterministic extractor on any failure. LiteLLM
remains a valid drop-in behind the same Provider interface for users who want its breadth.

**Consequences.** The default stays **$0/offline/deterministic** with no new dependency; the
LLM path is opt-in (set `HELIX_LLM_PROVIDER` + a key) and fully covered by tests via the fake
provider. This refines — does not reverse — ADR-007's policy (free-tier-first, cached, budgeted,
optional); only the "LiteLLM is the implementation" detail is relaxed.

---

## ADR-032 — Phase 4 `.dna` implementation choices (refines ADR-008/019)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Implementing the `.dna` codec, a few spec primitives weren't available as
stdlib/installed deps, and some streaming features are more than the MVP needs.

**Decision.** Build the `.dna` codec on **PyNaCl/libsodium**, which matches the spec where it
counts: **XChaCha20-Poly1305** (AEAD), **Ed25519** (detached signature over the manifest),
**Argon2id** (KDF, interactive limits). Deviations from ADR-019, recorded here:
- **Merkle hash = BLAKE2b (stdlib)**, not BLAKE3 (not stdlib; optional future upgrade).
- **Container = zip (DEFLATE)**, not tar+zstd — simpler, stdlib, fine for individual strands.
- **Encryption = 64 KiB secretstream chunks** (XChaCha20-Poly1305), truncation-resistant — the
  spec's intent. *(Initially single-blob; upgraded to chunked streaming, with a back-compatible
  `enc_mode` field so legacy single-blob strands still import.)*
Crypto is **lazily imported** so the always-on $0 memory loop stays dependency-free; only
`export`/`import`/`merge` need PyNaCl. Wrap-don't-encrypt, signed Merkle root, fail-closed
verification, and offline verifiability are all preserved.

**Consequences.** Spec-accurate enough to deliver verifiable, portable, encrypted strands today
(round-trip/tamper/wrong-passphrase tested); BLAKE3 + chunked streaming remain clean upgrades
behind the same format/version. Updated in [`docs/DNA_FORMAT.md`](docs/DNA_FORMAT.md).

---

## ADR-033 — Phase 5 dashboard: stdlib HTTP daemon + self-contained HTML (refines the FastAPI/React plan)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** The architecture sketched a FastAPI daemon + React/Vite dashboard. For the
local-first MVP that is heavier than needed: it adds a build step and a server framework just to
show a single-user localhost UI.

**Decision.** Ship the dashboard as a **dependency-free stdlib `http.server` daemon** (bound to
`127.0.0.1`, single-threaded/serial) exposing a small JSON API, serving a **single self-contained
HTML page** (vanilla JS + inline CSS, no CDN) — so it runs offline with zero build and zero new
runtime deps, honoring the $0/local-first ethos even for the UI. `helix dashboard` launches it.
The richer **React/Vite/Tailwind** frontend and a FastAPI backend remain valid upgrades for the
hosted/team product; they are not required for the local experience.

**Consequences.** Instantly runnable and testable (API driven over HTTP in tests, no browser).
SQLite is opened with `check_same_thread=False` so the daemon thread can serve it; access stays
serialized. Curation depth (inline edit, history timeline, graph viz) grows iteratively.

---

## ADR-034 — LLM-assisted gray-band consolidation (refines ADR-007, Phase 3 tail)
**Status:** Accepted · **Date:** 2026-06-18

**Context.** Pure cosine thresholds decide ADD/UPDATE/NOOP/SUPERSEDE well at the extremes, but
the middle ("gray band", ~0.65–0.97) is genuinely ambiguous: is the new statement a duplicate,
a refinement, a contradiction that should supersede, or a distinct fact?

**Decision.** When similarity falls in the gray band, the candidate and nearest memory share a
type, **and an LLM router is configured**, ask the model to classify the relationship
(`duplicate | update | contradict | distinct`) and act on the verdict (NOOP / UPDATE /
SUPERSEDE / ADD). It is **gated to the gray band only** (clear DUP matches still NOOP for free),
and **falls back to the deterministic decision** on any failure/unavailability — so the $0
default is unchanged. Wired into both the write path and `.dna` merge. Spec:
[`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md).

**Consequences.** Smarter conflict handling (e.g. "we use Mongo" → "we use Postgres" correctly
supersedes when the LLM says so) without extra cost on the common path; fully tested offline via
a fake provider.

## Packaging note (ADR-004 follow-up)
The `helix-core` package has **zero required runtime dependencies** (pure stdlib); semantic
embeddings (`fastembed`) and the `.dna` crypto (`pynacl`) are **optional extras**
(`helix-core[embeddings]`, `helix-core[crypto]`, `helix-core[all]`), imported lazily. The CLI
and SDK pull `helix-core[all]`. Verified: all four packages build (sdist + wheel) and the core
installs + runs standalone in a fresh venv with no third-party deps.

---

## ADR-035 — v2 direction: "Git for your AI's memory" + the portable-memory open standard
**Status:** Proposed · **Date:** 2026-06-19
**Context.** v1 shipped a SOTA-aligned engine. Eight parallel deep-research sweeps (memory frontier,
competitive landscape, ecosystem, collaboration, retrieval, trust/compliance, business, product/UX)
converged on a clear finding: every funded competitor (Mem0, Zep, Letta) is cloud-locked, and every
aligned OSS project (Basic Memory, Cognee) is general-purpose — leaving {local-first ∩ coding-native ∩
portable-signed-encrypted ∩ OSS-$0} occupied by **no one**. The git-like memory verbs
(diff/merge/branch/rollback on a portable strand) are unclaimed white-space.
**Decision.** v2 is **additive, not a rewrite.** Reposition Helix as **"Git for your AI's memory"**
(headline: diff/merge/branch/rollback on the signed `.dna`) and pursue, as the moonshot, an **open
standard for portable agent memory** ("USB for AI memory"). Full plan, pillars, effort/priority, and a
three-wave roadmap live in [`docs/V2_PLAN.md`](docs/V2_PLAN.md). Invariants from ADR-001/006/007/028 are
unchanged: $0/local-first default, no core cloud dependency, no charging to read your own memory,
encryption never paywalled. Notable refinements it schedules: procedural/skill memory (new type),
offline sleep-time consolidation (executes ADR-015), staleness detection, local cross-encoder reranker +
embedding upgrade (executes ADR-017), per-fact signed provenance + quarantine (extends ADR-029),
erasure-cascade engine (executes ADR-026), envelope encryption (executes ADR-020), framework adapters +
MCP-registry distribution, and the open-core Sync/Team tiers (extends ADR-028).
**Consequences.** Gives the project a sharp, defensible thesis and a sequenced backlog; commits us to
building a coding-memory eval (ADR-027) rather than chasing conversational benchmarks; defers a graph-DB
dependency permanently (the field is converging back to built-in entity linking — vindicates ADR-005).
**Alternatives considered.** (a) Rewrite the engine around an external graph/temporal DB — rejected
(cost, violates single-file portability). (b) Pivot general-purpose to chase Mem0 — rejected (abandons
the only white-space we own). (c) Lead with a hosted cloud product — rejected (violates local-first).

## ADR-036 — Portable Agent Memory: publish `.dna`'s record format as an open standard
**Status:** Proposed · **Date:** 2026-06-20
**Context.** v2 plan §8 (the moonshot): MCP standardized how agents *talk to* memory but not a
portable memory *artifact*. Owning that gap positions Helix as the category's interchange layer.
**Decision.** Publish a vendor-neutral **Portable Agent Memory** standard
([`docs/PORTABLE_MEMORY_STANDARD.md`](docs/PORTABLE_MEMORY_STANDARD.md), v1.0): an open JSON record
format (typed, bi-temporal, provenance-bearing) with three conformance levels — **core** (required
fields), **signed** (per-fact Ed25519 + BLAKE2b Merkle root), **encrypted** (the `.dna` container).
Ship a reference implementation in `helix_core.standard` (`validate()` is pure stdlib so any project
can vendor it), wired via `Engine.export_portable`/`conform` and `helix export-portable`/`helix
conform`. The encrypted binary `.dna` (ADR-008/019/032) remains the secure *container*; this is the
open *record format* it carries.
**Consequences.** Other tools can read/write/verify Helix memory without Helix; the validator is a
small adoption surface. Mirrors the *Portable Agent Memory* research (arXiv 2605.11032) but adds a
concrete, encrypt-at-rest reference + conformance checker. No new dependency; integrity uses the
existing BLAKE2b Merkle.
**Alternatives considered.** (a) Keep memory Helix-only — rejected (the moat is portability/ownership).
(b) Standardize the binary `.dna` itself as the interchange — rejected (encrypted + Python-specific;
a plain JSON record format is far easier for others to adopt). (c) Reuse the MCP wire format — rejected
(MCP is a transport, not a portable artifact).

---

## How to add a decision

1. Copy the ADR skeleton below, bump the number, set Status/Date.
2. Fill Context → Decision → Consequences → Alternatives.
3. If it changes an old ADR, mark the old one `Superseded by ADR-XXX` (add a new entry; do
   not delete history).
4. Link it from wherever the decision bites (CLAUDE.md, the relevant doc).

```
## ADR-XXX — <short title>
**Status:** Proposed · **Date:** YYYY-MM-DD
**Context.** ...
**Decision.** ...
**Consequences.** ...
**Alternatives considered.** ...
```
