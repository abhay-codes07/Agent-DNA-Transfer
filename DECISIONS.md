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
`push`, `pull`, `merge`, `log`). The MCP server = `helix-mcp`. PyPI package = `helix-memory`.

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
