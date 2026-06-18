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

## Phase 3 — LLM-enhanced, still ~$0
Better extraction quality without breaking the cost promise.

- ☐ LLM router (LiteLLM): Gemini 2.0 Flash free tier → gpt-4o-mini fallback
- ☐ Response cache + batching + structured JSON output + token-budget guardrail
- ☐ LLM-backed extractor + LLM-assisted conflict adjudication (gray-band only)
- ☐ Optional local LLM (Ollama) extractor path

**Exit:** quality jumps with a key, yet ≥ 90% of users still incur $0 (PRD §9).

---

## Phase 4 — Portability: the `.dna` strand
Deliver the headline: take your memory anywhere.

- ☐ Strand codec: package/sign (Ed25519)/encrypt (XChaCha20-Poly1305)/verify
- ☐ `export` / `import` with schema + embedding-space compatibility (re-embed on mismatch)
- ☐ `log` / `diff` / `rollback` (history)
- ☐ `merge` two strands (reuse consolidation + conflict resolution)

**Exit:** a user exports on machine A and imports/merges on machine B and it "just works"
(PRD G2 / metric: portability proof).

---

## Phase 5 — Curation UX (dashboard)
Make memory visible, accountable, and editable.

- ☐ Local daemon API (FastAPI) + dashboard (React/Vite/Tailwind)
- ☐ Browse/search the graph; edit/confirm/forget; provenance ("why it believes this")
- ☐ History timeline; cost & telemetry panel; strand/key management
- ☐ Memory decay/reinforcement surfaced and tunable

**Exit:** a user can fully audit and curate their memory without the CLI.

---

## Phase 6 — SDKs & ecosystem
Let others build on Helix.

- ☐ Python SDK (`helix-sdk-python`) parity with core ops
- ☐ TypeScript SDK + MCP client helpers
- ☐ `examples/` recipes; connectors for Copilot, Windsurf, ChatGPT desktop
- ☐ Public docs site; MCP-directory listings; "Add to …" one-liners

**Exit:** a third party can embed Helix in a custom agent in an afternoon.

---

## Phase 7 — Teams & optional sync (open-core)
Shared memory without giving up local-first ([ADR-010](DECISIONS.md)).

- ☐ Store interface → optional Postgres+pgvector backend
- ☐ Encrypted team strand sync (bring-your-own storage first; thin relay later)
- ☐ Scoped sharing, redaction-on-share guarantees, org policy/audit (commercial layer)
- ☐ Explore decentralized/verifiable backend (Walrus-style) as a pluggable option

**Exit:** a team shares and merges a strand with no secret leakage; revenue layer exists
without ever charging to read your own memory.

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
- **Evaluation harness** from Phase 1: LongMemEval-style metrics + a coding-agent memory
  benchmark; the $0/offline path tested as a first-class CI config ([Evaluation](docs/EVALUATION.md))
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
