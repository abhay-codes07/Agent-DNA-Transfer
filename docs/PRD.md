# Helix — Product Requirements Document (PRD)

**Status:** Draft v1 · **Owner:** Founding team · **Last updated:** 2026-06-18
**Related:** [TSD](TSD.md) · [System Architecture](SYSTEM_ARCHITECTURE.md) · [Decisions](../DECISIONS.md) · [Roadmap](../ROADMAP.md)

---

## 0. TL;DR

Helix is a **local-first, portable, git-like memory layer for AI coding agents.** It learns
who you are and how you work, stores that as a knowledge graph *on your machine*, and serves
it to any agent over MCP — so Claude Code, Cursor, Copilot, Windsurf, and ChatGPT all wake
up already knowing you. Your memory lives in one portable, signed, encrypted **`.dna`
strand** you can move, version, merge, and roll back like code. It runs at **$0 by default.**

> One memory. Every agent. Owned by you.

---

## 1. Vision & mission

**Mission.** Give every developer a memory that belongs to *them*, not to a vendor — one
that travels with them across every AI tool they'll ever use.

**Vision.** Today, switching AI tools means amnesia. In five years, your AI memory should be
as portable as a git repo and as private as a password manager. Helix is the layer that
makes "your AI knows you, everywhere" the default — starting with the people who switch
tools most and feel the pain hardest: **developers.**

**The 10-year bet.** Models are commoditizing; *context* is the moat, and that moat should
belong to the user. Whoever owns the portable, user-controlled context layer owns the most
durable real estate in AI. We intend that layer to be open, local-first, and Helix-shaped.

---

## 2. The problem

Every AI agent is slowly learning you — your stack, your conventions, the architecture
you've re-explained five times, your taste in libraries. Then you switch tools, hit a
context-window limit, or end a session, and it's **gone.**

Four structural failures:

1. **Memory is trapped per-vendor.** ChatGPT memory ≠ Claude memory ≠ Cursor memory. There
   is no export-and-import-elsewhere.
2. **Memory is opaque.** You can't see what an agent "knows" about you, fix a wrong fact,
   or delete something sensitive at the granularity of a single belief.
3. **Memory isn't yours.** It lives on a vendor's servers under a vendor's terms, minable
   and revocable by someone who isn't you.
4. **Memory isn't coding-aware.** Generic "assistant memory" stores "the user likes concise
   answers." It does **not** model *this repo's architecture*, *why we chose Postgres over
   Mongo*, or *the team's naming conventions* — the context that actually makes a coding
   agent good.

The cost is real: repeated re-explaining, inconsistent agent behavior across tools, lock-in,
and a privacy posture no security-conscious developer is comfortable with.

### Why now

- **MCP won.** A single open protocol now connects agents to context ("USB-C for AI"), with
  200+ servers by Q2 2026. A memory layer can reach *every* agent through one integration.
- **Memory is a recognized architectural layer.** Mem0/OpenMemory proved the
  extraction→store→recall→consolidate loop; Walrus proved demand for portable, verifiable
  memory. The category exists; nobody owns the **local-first, coding-native, free** corner.
- **Local models & embeddings are good enough.** CPU embeddings (bge-small) and free LLM
  tiers make a $0 default genuinely viable.
- **Developers are the wedge.** They use the most tools, switch the most, and care the most
  about ownership and privacy. Win them and the pattern generalizes to everyone.

---

## 3. Competitive landscape

| Product | Shape | Strength | Gap Helix exploits |
|---|---|---|---|
| **ChatGPT / Claude memory** | Vendor-native | Zero setup | Trapped, opaque, not portable, not yours |
| **Mem0 (OSS + hosted)** | Universal memory SDK/API | Strong extraction engine, MCP | Cloud-leaning, generic (not coding-native), not a portable single artifact |
| **OpenMemory MCP** | Local memory + dashboard | Local store, MCP, dashboard | Generic facts, no git-like transfer/merge, no coding model |
| **Walrus Memory** | Portable memory on decentralized storage | Verifiable, portable, encrypted | Heavy infra, costy, cloud/chain-dependent, not coding-native, not free/offline |
| **MCP "memory" server (knowledge graph)** | Reference KG server | Simple, open | No extraction intelligence, no portability story, no UI |

**Helix's unique combination** (no competitor has all five):
local-first ownership · coding-native depth · git-like portable `.dna` · MCP-universal · $0 default.

> Positioning one-liner: *"Mem0's brain, OpenMemory's locality, Walrus's portability, git's
> ergonomics — built for coders and free to run."*

---

## 4. Target users & personas

### Primary — **"Polyglot Dev" (individual developer)**
Uses 2–4 AI tools (Claude Code + Cursor + ChatGPT). Switches based on task. Hates
re-explaining context. Privacy-conscious. Wants their AI to "just know" the project and
their preferences everywhere. **This is the wedge.**

### Secondary — **"Squad Lead" (small team)**
Wants the *team's* shared knowledge — architecture decisions, conventions, gotchas —
available to every member's agent. Needs to share a strand and merge updates without leaking
secrets. Onboarding a new dev = handing them the team strand.

### Tertiary — **"Privacy Hawk" (security-conscious / regulated)**
Will not put context in a vendor cloud. Needs local-only, encrypted, auditable memory with
explicit control over every fact. Helix's default mode *is* their requirement.

### Expansion — **"Everyone" (non-dev knowledge worker)**
Once the coding wedge is established, the same engine serves writers, researchers, founders,
and analysts who want portable personal memory across general assistants. Coding-native
types generalize into a pluggable schema (see [Memory Model](MEMORY_MODEL.md)).

### Anti-persona (not for v1)
Enterprises needing SSO, SOC2, on-prem multi-tenant deployments, and admin consoles. We
serve them later via the optional team/cloud layer — not at launch.

---

## 5. Goals & non-goals

### Goals (v1)
- G1. An agent connected to Helix recalls relevant personal/project memory **without the
  user re-explaining** it.
- G2. The user can **export their entire memory to one `.dna` file** and **import it on
  another machine/agent** and have it work.
- G3. Default operation costs **$0** and works **fully offline**.
- G4. The user can **see, edit, and delete** any individual memory via a local UI/CLI.
- G5. Helix is **coding-native**: it models repos, stacks, conventions, and decisions, not
  just generic "assistant facts."
- G6. Connect to **Claude Code and Cursor** in **under 2 minutes** each via MCP.

### Non-goals (v1)
- N1. No hosted multi-tenant SaaS, billing, or org admin console.
- N2. No decentralized/blockchain storage (designed-for, not built — [ADR-010](../DECISIONS.md)).
- N3. No automatic, silent capture of *everything* — ingestion is user-routed and explicit.
- N4. No mobile app. No browser extension at launch (later).
- N5. Not a general RAG-over-documents product; Helix is *memory about the user/projects*,
  not a document search engine (though it can reference docs).

---

## 6. The product

### 6.1 Core loop (what users experience)

1. **Connect** — `helix connect claude-code` writes the MCP config. Done.
2. **Work normally** — as the user works, Helix observes the slices they route to it and
   **extracts durable facts** in the background (heuristics first, LLM only when needed).
3. **Recall** — when any connected agent starts/needs context, it queries Helix over MCP and
   gets the most relevant memories injected — no re-explaining.
4. **Curate** — the user opens the dashboard to review, edit, confirm, or forget facts.
5. **Transfer** — `helix export brain.dna` → move it anywhere → `helix import brain.dna`.
6. **Evolve** — `helix log`/`diff`/`rollback` show how memory changed; merge teammates' strands.

### 6.2 What Helix stores (the memory graph)

Typed nodes, each timestamped, sourced, confidence-scored, editable (full schema in
[Memory Model](MEMORY_MODEL.md)):

- **Identity** — role, expertise, tools, working hours, communication style.
- **Preference** — formatting, libraries to use/avoid, testing style, tone.
- **Project** — services, architecture, dependencies, conventions, gotchas.
- **Decision** — durable choices + rationale (a personal/team ADR stream).
- **Entity** — people, teams, repos, services, and their relationships (graph edges).
- **Snippet/Pattern** — reusable idioms the user keeps reaching for.

Helix stores **distilled facts, not raw transcripts.** A chat about choosing a database
becomes a `Decision` node ("Chose Postgres over Mongo for X; see thread"), not a 4,000-token log.

### 6.3 The `.dna` strand (headline feature)

A single portable file = the user's whole memory: signed (Ed25519), encrypted
(XChaCha20-Poly1305), versioned, content-hashed. Supports git-like operations:
`export/import` (clone), `merge` (combine two memories with conflict resolution),
`log/diff` (history), `rollback` (undo a bad learning). Full spec: [DNA Format](DNA_FORMAT.md).

### 6.4 Surfaces

- **MCP server** — the universal interface; how agents read/write memory.
- **CLI (`helix`)** — init, connect, export/import/merge, log, edit, doctor.
- **Dashboard** — local web UI to browse the graph, edit/confirm/forget, view history, see
  cost/telemetry.
- **SDKs (Python, TypeScript)** — embed Helix in custom agents/scripts.

---

## 7. Requirements

### 7.1 Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | Extract durable facts from user-routed conversation/code slices | P0 |
| FR-2 | Heuristic pre-filter to skip the LLM when no new fact is likely | P0 |
| FR-3 | Store facts as a typed graph in an embedded vector+graph store | P0 |
| FR-4 | Semantic + graph retrieval of relevant memories for a query | P0 |
| FR-5 | Consolidation: ADD / UPDATE / DELETE / NOOP to keep memory clean & non-redundant | P0 |
| FR-6 | Conflict detection (contradictory facts) with resolution + provenance | P0 |
| FR-7 | MCP server exposing `memory.search/write/forget/list/relate` tools | P0 |
| FR-8 | `helix connect <agent>` to auto-configure MCP for Claude Code, Cursor, … | P0 |
| FR-9 | Export/import a signed, encrypted `.dna` strand | P0 |
| FR-10 | Local embeddings (default) with optional cloud embeddings | P0 |
| FR-11 | LLM router: free-tier-first (Gemini) → fallback (gpt-4o-mini), optional | P0 |
| FR-12 | Dashboard: browse, search, edit, confirm, forget memories | P1 |
| FR-13 | `helix log/diff/rollback` history operations | P1 |
| FR-14 | `helix merge` two strands with conflict resolution | P1 |
| FR-15 | Memory decay/aging (down-rank stale, unconfirmed facts) | P1 |
| FR-16 | Scoping: per-project vs global memory; redaction of secrets at ingest | P1 |
| FR-17 | Python + TypeScript SDKs | P1 |
| FR-18 | Optional local LLM (Ollama) extractor for $0 high-quality extraction | P2 |
| FR-19 | Optional encrypted cloud/team sync backend | P2 |
| FR-20 | Browser extension / web-app capture | P2 |

### 7.2 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | **Recall latency** (MCP search → results) | p95 < 150 ms local |
| NFR-2 | **Extraction latency** (background, non-blocking) | does not block the agent |
| NFR-3 | **Default cost** | $0 (no required API spend) |
| NFR-4 | **Offline** | full core functionality with no network |
| NFR-5 | **Capacity** | 10⁵–10⁶ memories per strand without degradation |
| NFR-6 | **Encryption at rest** | XChaCha20-Poly1305; keys via Argon2id/keychain |
| NFR-7 | **Integrity** | Ed25519-signed manifest; verified on import |
| NFR-8 | **Privacy** | telemetry off by default; secrets never persisted/logged |
| NFR-9 | **Portability** | strand opens on Windows/macOS/Linux identically |
| NFR-10 | **Setup time** | connect an agent in < 2 minutes |
| NFR-11 | **Footprint** | install + model cache < 300 MB; idle RAM < 200 MB |
| NFR-12 | **Data safety** | no partial/corrupt strand writes (transactional) |

---

## 8. UX principles

1. **Invisible when working, visible when curating.** Extraction is silent background work;
   inspection/editing is rich and explicit.
2. **Nothing happens you didn't route.** No ambient surveillance. The user chooses what
   Helix sees.
3. **Every fact is accountable.** Source, date, confidence, and "why I believe this" are one
   click away. Wrong facts are one click to fix or forget.
4. **It should feel like git.** Familiar verbs, history you can trust, undo that works.
5. **Free should feel first-class**, not crippled. The $0 path is the default, not a teaser.

---

## 9. Success metrics

**North Star:** *Weekly Recalled Memories that the user keeps* — memories Helix surfaced to
an agent that the user did **not** edit/forget within 7 days (signal that recall is both
used and correct).

Supporting metrics:

- **Activation:** % of installs that connect ≥1 agent and accumulate ≥10 confirmed memories within 7 days. Target ≥ 40%.
- **Portability proof:** % of active users who export a `.dna` and import it elsewhere. Target ≥ 20% (validates the headline).
- **Recall quality:** edit/forget rate on surfaced memories < 10%.
- **Cost integrity:** ≥ 90% of active users on the $0 path (no paid API spend).
- **Retention:** week-4 retention of activated users ≥ 35%.
- **Time-to-connect:** median < 2 minutes.

(Telemetry is opt-in and local-first; aggregate metrics are computed only from users who
explicitly share. See [Security Model](SECURITY_MODEL.md).)

---

## 10. Go-to-market

**Wedge:** open-source, developer-first, MCP-native. Land where developers already are.

- **Distribution:** PyPI (`pipx install helix-memory`), GitHub, MCP server directories,
  "Add to Cursor/Claude Code" one-liners, Homebrew later.
- **Narrative:** "Your AI forgets you every time you switch tools. Helix fixes that — locally
  and free." Demos showing the *same* memory lighting up Claude Code *and* Cursor.
- **Community:** great docs (this repo), example recipes, a public roadmap, fast issue
  response, and a Discord. Open-core builds trust that "your memory is really yours."
- **Loops:** the `.dna` *merge*/share flow is inherently viral inside teams — onboarding a
  teammate means handing them a strand.

**Business model (open-core, later — [ADR-009](../DECISIONS.md)):** the engine, CLI, MCP
server, and SDKs stay free/Apache-2.0 forever. Revenue comes from optional layers that don't
compromise local-first: encrypted **team sync**, hosted backup, org policy/audit, and
managed cloud for non-technical users. We never charge to *read your own memory.*

---

## 11. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Local extraction quality too low without an LLM | Med | High | Tiered extractor (heuristic→free LLM→optional Ollama); ship LLM-on path that's still ~$0 via free tier; measure edit/forget rate |
| MCP spec churn breaks integrations | Med | Med | Pin protocol version; thin adapter layer; integration tests per agent |
| Privacy mistrust ("is it really local?") | Med | High | Open source, offline-verifiable, no required account, transparent telemetry, security audit before launch |
| Merge/conflict resolution is hard & error-prone | High | Med | CRDT-style rules + provenance + LLM tie-break + always-reversible (rollback); never auto-destroy data |
| Incumbents (OpenAI/Anthropic) ship portable memory | Low–Med | High | They won't make it local-first/vendor-neutral by default; lean into ownership + coding depth + open ecosystem |
| Scope explosion (this is a big project) | High | Med | Spec-first, phased roadmap, $0/local invariants as guardrails; ship the wedge before the platform |
| Trademark "Helix" conflict | Med | Low | Name-check before public launch; rename is a find-replace + ADR ([ADR-002](../DECISIONS.md)) |
| Secret leakage into a strand | Low | High | Secret redaction at ingest; never store raw transcripts; security model + tests |

---

## 12. Open questions

- Default extraction tier when **no** key is present: ship Ollama auto-detect, or pure
  heuristic? (Leaning heuristic default, Ollama if detected.)
- Merge conflict UX: fully automatic with audit, or always prompt the user on conflicts?
- How much to auto-scope to the current repo vs. a global profile by default?
- Team sync trust model: bring-your-own-storage (S3/Drive) vs. a thin hosted relay first?

Decisions to these will be logged in [`DECISIONS.md`](../DECISIONS.md) as they're made.

---

## 13. Glossary

See [`docs/GLOSSARY.md`](GLOSSARY.md). Key terms: **strand** (`.dna` file = a user's
memory), **memory/fact** (one typed node), **consolidation** (ADD/UPDATE/DELETE/NOOP),
**recall** (retrieval for an agent), **transfer** (export/import/merge of strands).
