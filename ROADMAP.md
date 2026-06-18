# Helix — Roadmap

**Last updated:** 2026-06-18 · **Related:** [PRD](docs/PRD.md) · [TSD](docs/TSD.md) · [Decisions](DECISIONS.md)

Phased plan from a working wedge to a platform. Each phase is shippable on its own and
preserves the invariants: **local-first, user-owns-memory, $0 default, MCP interface.**
Dates are intentionally omitted; phases gate on exit criteria, not calendar.

> Legend: ☐ todo · ◐ in progress · ☑ done. Everything is ☐ today (pre-alpha, spec stage).

---

## Phase 0 — Foundation (you are here)
Spec-first groundwork so humans and AI agents share one source of truth.

- ☑ PRD, TSD, System Architecture
- ☑ DECISIONS (ADR) log, CLAUDE.md contributor contract
- ☑ License + community files + repo scaffold
- ☐ Supporting specs: Memory Model, DNA Format, Cost, MCP, Security, Glossary
- ☐ `uv` workspace + package skeletons that import and run `--help`

**Exit:** a contributor (human or AI) can read the docs and know exactly what to build.

---

## Phase 1 — Local memory MVP ($0, offline) ✅ shipped
The smallest thing that delivers the core value with zero cost and no network.

- ☑ `helix-core`: ingestion → redaction → heuristic gate
- ☑ Deterministic (no-LLM) extractor + local embeddings (dependency-free hashing default;
  `fastembed` bge-small auto-used when installed)
- ☑ Stores: one SQLite file (vectors + relational graph + FTS + history); transactional writes
  (`sqlite-vec` is an optional accelerator; brute-force cosine is the default)
- ☑ Consolidation (ADD/UPDATE/NOOP/SUPERSEDE, bi-temporal) + basic conflict resolution
- ☑ Hybrid retrieval (dense + keyword → RRF → rank → MMR) + graph (PPR-lite) expansion
- ☑ Read-time decay/salience + SM-2 reinforcement; `maintain` decay-archival
- ☑ `helix-cli`: `init`, `add`, `search`, `list`, `context`, `forget`, `relate`, `maintain`, `doctor`

**Exit:** ✅ a user can store and recall personal/project facts locally, for free, offline.
31 tests pass; verified via CLI + SDK quickstart.

---

## Phase 2 — Reach every agent (MCP) ✅ shipped
Make the memory show up *inside* the tools people already use.

- ☑ `helix-mcp` server (FastMCP/stdio): `memory_search/context/write/get/forget/relate/list`
- ☑ `helix connect <agent>` for Claude Code, Cursor, Windsurf, VS Code, Gemini, Zed, Codex
- ☑ Token-budgeted, concise/detailed results (the surface no competitor budgets today)
- ☑ Integration tests + a live stdio round-trip via the real `mcp` SDK client

**Exit:** ✅ an MCP client recalls the same memory over stdio (verified end-to-end). Next:
real `fastembed` semantic embeddings + the `.dna` portability layer.

---

## Phase 3 — LLM-enhanced, still ~$0 ✅ mostly shipped
Better extraction quality without breaking the cost promise.

- ☑ LLM router: Gemini 2.0 Flash free tier → gpt-4o-mini fallback (stdlib provider clients;
  LiteLLM optional — [ADR-031](DECISIONS.md))
- ☑ Response cache (SQLite, pay-once) + structured JSON output + token-budget guardrail
- ☑ LLM-backed extractor (gate-gated; always falls back to deterministic on failure/budget)
- ☑ Optional local LLM (Ollama) extractor path
- ☐ LLM-assisted conflict adjudication for gray-band consolidation (deferred)
- ☐ Batched multi-turn extraction (deferred)

**Exit:** ✅ quality jumps with a key, default stays $0/offline. Verified offline with a fake
provider (cache, budget, fallback) + graceful degradation when no provider is reachable.

---

## Phase 4 — Portability: the `.dna` strand ✅ shipped
Deliver the headline: take your memory anywhere.

- ☑ Strand codec: package/sign (Ed25519)/encrypt (XChaCha20-Poly1305)/Argon2id/verify
  (PyNaCl; BLAKE2b Merkle — [ADR-032](DECISIONS.md))
- ☑ `export` / `import` (signature + integrity verified; fail-closed on tamper/wrong passphrase)
- ☑ `verify` (offline, no passphrase) · `log` (history) · `diff` · `rollback` (restore from .dna)
- ☑ `merge` two strands (reuses consolidation → dedup/supersede)
- ☐ Embedding-space re-embed on import mismatch (deferred; same-embedder import works today)
- ☐ BLAKE3 + 64 KiB chunked streaming for very large strands (deferred)

**Exit:** ✅ exported on home A, imported on a fresh home B, and recall works — verified live and
in tests (round-trip, tamper detection, wrong-passphrase, merge dedup, diff).

---

## Phase 5 — Curation UX (dashboard) ✅ shipped (v1)
Make memory visible, accountable, and editable.

- ☑ Local daemon API (stdlib `http.server`, 127.0.0.1) + self-contained HTML dashboard
  ([ADR-033](DECISIONS.md)); `helix dashboard`
- ☑ Browse/search memories; add/forget; per-memory type/scope/origin; Stats panel
- ☑ Graph tab (nodes + typed relations)
- ☑ Inline edit (re-embeds on content change), provenance "why it believes this" drill-down,
  History timeline tab
- ☐ React/Vite/Tailwind frontend + decay/reinforcement tuning (next)

**Exit:** ✅ a user can browse, search, add, and forget memories in a browser without the CLI;
deeper curation (inline edit, history) is iterative. API tested over HTTP.

---

## Phase 6 — SDKs & ecosystem ✅ v1 shipped
Let others build on Helix.

- ☑ Python SDK (`helix_sdk.Helix`) — full parity (memory, transfer, sync, edit, history, stats)
- ☑ TypeScript SDK (`@helix-memory/sdk`) — fetch client against the local daemon API
- ☑ Connectors: 8 named clients (incl. **claude-desktop**, per-OS) + a generic
  `helix connect <name> --path <file> --key <key>` for any MCP client
- ☐ Public docs site; MCP-directory listings; more example recipes (next)

**Exit:** ✅ a third party can embed Helix via the Python or TS SDK, and wire it into essentially
any MCP client. SDK parity verified in tests.

---

## Phase 7 — Teams & optional sync (open-core) ✅ v1 shipped
Shared memory without giving up local-first ([ADR-010](DECISIONS.md), [ADR-022](DECISIONS.md)).

- ☑ Encrypted team sync: `helix push` / `helix pull` move the **encrypted** `.dna` to a shared
  location; pull reuses the Phase 4 merge (conflict-aware dedup). Backend sees only ciphertext.
- ☑ `SyncBackend` interface + `LocalDirBackend` (bring-your-own folder / synced drive)
- ☐ `S3Backend`/R2 + thin relay (interface stubbed; wired later)
- ☐ Store interface → optional Postgres+pgvector backend (for very large team strands)
- ☐ Scoped sharing, org policy/audit, "review memory like code" PR flow (commercial layer)
- ☐ Decentralized/verifiable backend (Walrus-style) as a pluggable option

**Exit:** ✅ two people share + merge a strand with no secret leakage (verified live + tests);
the redaction invariant + E2E encryption mean the backend never sees plaintext.

---

## Phase 8 — Beyond coding ("everyone")
Generalize the wedge.

- ☐ Pluggable memory schemas (writers, researchers, founders, analysts)
- ☐ Browser extension / web capture; broader assistant connectors
- ☐ Non-technical onboarding (managed local app)

**Exit:** the same engine serves non-developers with portable, owned memory.

---

## Cross-phase, always-on
- Security: tiered redaction tests, crypto review, anti-poisoning guardrails, **external audit
  before any public launch** ([Security](docs/SECURITY_MODEL.md), [Privacy](docs/PRIVACY_COMPLIANCE.md))
- ☑ **Evaluation harness** (`helix eval` / `helix_core.eval`): precision/recall@k, MRR, and
  recall latency on a built-in coding-agent benchmark ([Evaluation](docs/EVALUATION.md));
  $0/offline path tested as a first-class CI config (GitHub Actions: ruff + black + mypy + pytest)
- Trademark/availability check for "Helix" before public launch ([ADR-002](DECISIONS.md))
- Performance budgets (recall p95, footprint) enforced in CI
- Docs and ADRs kept in lockstep with code (spec-first invariant)

## Research-driven workstreams (woven across phases)
These deepen the phases above; each maps to a Wave-2 ADR and a spec:
- **Cognitive memory model** — episodic/semantic/procedural + entity graph, bi-temporal facts
  ([Memory Model](docs/MEMORY_MODEL.md), ADR-012/013).
- **Consolidation engine** — CLS two-stage, decay/reinforcement, reflection, sleep-time
  ([Consolidation](docs/CONSOLIDATION.md), ADR-014/015) — Phase 3+.
- **Retrieval pipeline** — hybrid + RRF + graph PPR + MMR, quantized embeddings
  ([Retrieval](docs/RETRIEVAL.md), ADR-016/017) — Phase 1.
- **Merge & sync** — CRDT + 3-way semantic merge, optional E2E sync
  ([Sync](docs/SYNC.md), ADR-021/022) — Phase 4/7.
- **Plugin interfaces** — embeddings/stores/LLM/connectors ([Plugins](docs/PLUGINS.md), ADR-030).

---

## Guiding sequence
**Wedge before platform.** Ship Phases 1–4 (local memory → every agent → cheap quality →
portability) to nail the unique promise, *then* expand to UX, SDKs, teams, and everyone.
Resist building the platform before the wedge is loved.
