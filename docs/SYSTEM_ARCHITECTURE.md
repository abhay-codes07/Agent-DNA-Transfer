# Helix — System Architecture

**Status:** Draft v1 · **Last updated:** 2026-06-18
**Related:** [PRD](PRD.md) · [TSD](TSD.md) · [DNA Format](DNA_FORMAT.md) · [Security](SECURITY_MODEL.md) · [Decisions](../DECISIONS.md)

This document is the "how it all fits together" view: topology, data flow, trust boundaries,
deployment, scaling, and the monorepo layout. Diagrams are ASCII so they live in the repo and
diff cleanly.

---

## 1. Architectural principles

1. **Local-first core.** The whole engine runs on the user's machine; the network is optional
   ([ADR-001](../DECISIONS.md)).
2. **One protocol to reach every agent.** MCP is the front door ([ADR-003](../DECISIONS.md)).
3. **The strand is the unit of truth and portability.** A single self-describing, signed,
   encrypted SQLite file ([ADR-005](../DECISIONS.md), [ADR-008](../DECISIONS.md)).
4. **Pluggable everything.** Embeddings, LLM, vector store, graph store sit behind interfaces
   so we can swap local↔cloud↔decentralized without touching callers.
5. **Cost is an architectural constraint, not a tuning knob.** The gate→local→free-tier
   pipeline is baked into the data flow ([ADR-007](../DECISIONS.md)).
6. **Fail safe, never corrupt.** Every strand mutation is transactional and reversible.

---

## 2. C4-ish view

### 2.1 Context (level 1)

```
        ┌─────────────────────────────────────────────────────────┐
        │                        The User                         │
        │   (developer; owns the device, keys, and the strand)    │
        └───────────────┬───────────────────────────┬─────────────┘
                        │ uses                       │ curates
                        ▼                            ▼
   ┌──────────────────────────────┐      ┌────────────────────────┐
   │   AI coding agents           │ MCP  │   Helix Dashboard      │
   │ Claude Code · Cursor ·       │◄────►│  (local web UI)        │
   │ Copilot · Windsurf · ChatGPT │      └───────────┬────────────┘
   └──────────────┬───────────────┘                  │ localhost API
                  │                                   │
                  ▼                                   ▼
            ┌───────────────────────────────────────────────┐
            │                 Helix (local)                  │
            │   engine · MCP server · CLI · stores · codec   │
            └───────────────────────┬───────────────────────┘
                                    │ optional, opt-in
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                        ▼
    ┌──────────────┐      ┌──────────────────┐     ┌──────────────────┐
    │ LLM provider │      │ cloud embeddings │     │  team/cloud sync │
    │ Gemini/OpenAI│      │ (optional)       │     │   (optional)     │
    └──────────────┘      └──────────────────┘     └──────────────────┘
```

Solid arrows = required/local. Bottom row = optional, off by default, behind the trust
boundary the user explicitly opens.

### 2.2 Containers (level 2)

```
┌───────────────────────────── User's machine ──────────────────────────────┐
│                                                                            │
│  ┌────────────┐   stdio/MCP   ┌──────────────┐   in-proc   ┌────────────┐  │
│  │  Agent     │◄─────────────►│ helix-mcp    │────────────►│ helix-core │  │
│  └────────────┘               │ (MCP server) │             │  engine    │  │
│                               └──────────────┘             │            │  │
│  ┌────────────┐   in-proc                                  │  ┌───────┐ │  │
│  │ helix-cli  │─────────────────────────────────────────► │  │stores │ │  │
│  └────────────┘                                            │  │vec+gph│ │  │
│                                                            │  └───┬───┘ │  │
│  ┌────────────┐  localhost HTTP/WS   ┌─────────────┐       │      │     │  │
│  │ dashboard  │◄────────────────────►│ daemon API  │◄─────►│      ▼     │  │
│  │ (browser)  │                      │ (FastAPI)   │       │  strand.db │  │
│  └────────────┘                      └─────────────┘       │  (.dna)    │  │
│                                                            └────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
```

`helix-core` is a library; the MCP server, CLI, and daemon API are thin front-ends over it.
The strand (`strand.db`) is the shared persistent state, opened transactionally.

### 2.3 Components inside `helix-core` (level 3)

```
                       ┌──────────────────────────────────────────┐
   routed slice  ───►  │ Ingestion ─► Redaction ─► Heuristic Gate  │
                       └───────────────┬──────────────────────────┘
                                       │ (passes gate)
                                       ▼
                  ┌───────────────────────────────────────────┐
                  │ Extractor (deterministic | LLM-backed)    │──► Embedder
                  └───────────────┬───────────────────────────┘        │
                                  ▼                                     ▼
                  ┌───────────────────────────────────────────┐   ┌─────────┐
                  │ Consolidator (ADD/UPDATE/DELETE/NOOP)      │◄─►│ Stores  │
                  │ + Conflict Resolver                        │   │ vec/gph │
                  └───────────────┬───────────────────────────┘   └─────────┘
                                  ▼
   recall(query) ◄── Retriever (vector + graph + rank + pack)  ◄── Stores
                                  │
        Strand Codec (sign/encrypt/verify · diff/merge/rollback) ◄── Stores
                                  │
        Scheduler (decay · re-embed · compaction)
```

See [TSD §3, §6](TSD.md) for component contracts and algorithms.

---

## 3. Data flow

### 3.1 Write path (learning)
1. Agent or CLI routes a slice via `memory.write`/`memory.note` (MCP) or SDK.
2. **Redaction** scrubs secrets *before* storage or any model call.
3. **Heuristic gate** decides if extraction is worthwhile; most slices stop here ($0).
4. **Extractor** (local or LLM) emits candidate facts; **Embedder** vectorizes them.
5. **Consolidator** compares to existing memory → ADD/UPDATE/DELETE/NOOP; **Conflict
   resolver** handles contradictions; **history** logs the op.
6. Result is committed transactionally to `strand.db`.

The write path is **asynchronous to the agent** — it returns an ack fast and does extraction
in the background so it never blocks the user (NFR-2).

### 3.2 Read path (recall)
1. Agent calls `memory.search`/`memory.context` with a query and a token budget.
2. Retriever embeds the query, does ANN search, expands the graph, ranks, and packs under the
   budget.
3. Results (with source + confidence) return over MCP and are injected into the agent's
   context. p95 < 150 ms (NFR-1).

### 3.3 Transfer path (the headline)
1. `helix export` → codec snapshots `strand.db`, writes `manifest.json`, signs it, encrypts
   the DB, packages `.dna`.
2. Move the file anywhere.
3. `helix import` → verify signature → decrypt → check schema/embedding compatibility
   (re-embed if needed) → open.
4. `helix merge other.dna` → union + consolidate + resolve conflicts → new version
   (reversible). See [TSD §7](TSD.md) and [DNA Format](DNA_FORMAT.md).

---

## 4. Trust boundaries & security architecture

```
   ┌────────────────────── TRUSTED (user's device) ───────────────────────┐
   │  keys (Ed25519 sign, encryption key), plaintext strand in memory,     │
   │  engine, stores, dashboard. Secrets read from env, never persisted.   │
   └───────────────┬───────────────────────────────────────┬──────────────┘
                   │ encrypted + signed                     │ redacted text only,
                   ▼ at rest                                ▼ user-opted-in
        ┌────────────────────┐                   ┌────────────────────────┐
        │  .dna on disk /     │                   │  LLM / cloud provider  │
        │  in transit         │                   │  (extraction only)     │
        │  (UNTRUSTED medium) │                   │  (UNTRUSTED)           │
        └────────────────────┘                   └────────────────────────┘
```

- **At rest / in transit:** strand encrypted (XChaCha20-Poly1305), manifest signed (Ed25519),
  integrity verified on import. The medium (disk, USB, cloud drive) is treated as untrusted.
- **To an LLM provider:** only *redacted* text is ever sent, and only when the user has
  supplied a key and the gate decided extraction is needed. Secrets are scrubbed pre-flight.
- **Keys** never leave the device unless the user explicitly exports them.

Full model and threat analysis: [Security Model](SECURITY_MODEL.md).

---

## 5. Deployment topologies

### T1 — Solo, offline, $0 (default)
Everything local; no keys; deterministic extractor; local embeddings. This is the out-of-box
experience and the privacy/cost baseline.

### T2 — Solo, LLM-enhanced
Same, plus a Gemini (free) or OpenAI key for higher-quality extraction. Still ~$0 via
gate + free tier + cache. Cloud sees only redacted slices.

### T3 — Small team (later, [ADR-010](../DECISIONS.md))
Each member runs Helix locally; a shared **team strand** is synced via an optional encrypted
backend (bring-your-own S3/Drive or a thin relay). Merges reconcile members' updates. No
secrets ever sync. The engine and trust model are unchanged; sync is an add-on.

### T4 — Power user, fully local LLM
Ollama provides extraction locally: better-than-heuristic quality, still $0, still offline.

No topology changes the core; they only flip which pluggable backend is active.

---

## 6. Scaling & performance

- **Per-strand capacity:** 10⁵–10⁶ memories on `sqlite-vec` with ANN; well beyond an
  individual's lifetime of context (NFR-5).
- **Recall:** p95 < 150 ms via ANN + cached graph projection; ranking is O(N candidates),
  not O(all).
- **Write:** background/async; batched extraction amortizes any LLM latency.
- **Memory footprint:** lazy graph projection, model cache on disk; idle RAM < 200 MB (NFR-11).
- **Growth management:** decay + compaction keep the working set sharp as the strand grows;
  archived nodes drop out of the hot ANN index.
- **Big team strands:** if a single SQLite strand becomes a bottleneck, the store interface
  allows a Postgres+pgvector backend without API changes ([ADR-010](../DECISIONS.md)).

---

## 7. Failure modes & resilience

| Failure | Behavior |
|---|---|
| No network / no key | Deterministic extractor + local embeddings; full core works |
| LLM provider down / rate-limited | Router falls back (Gemini→OpenAI→deterministic); never blocks or loses data |
| Embedding model missing on first run | Download + cache; clear progress; offline after |
| Crash mid-write | Atomic temp-write + WAL → no partial/corrupt strand |
| Import tampered/incompatible strand | Signature/schema check fails closed with guidance |
| Conflicting facts | Resolver supersedes (reversible); user can override |
| Strand corruption (disk) | Restore from history/backup; codec validates on open |

---

## 8. Monorepo layout

```
Agent-DNA-Transfer/                 # repo (umbrella: "Agent DNA Transfer")
├── README.md
├── CLAUDE.md                       # how agents contribute here
├── DECISIONS.md                    # ADR log
├── ROADMAP.md
├── LICENSE  CONTRIBUTING.md  SECURITY.md  CODE_OF_CONDUCT.md
├── .env.example  .gitignore
├── pyproject.toml                  # uv workspace root
├── Makefile                        # common dev tasks
│
├── docs/                           # the source of truth
│   ├── PRD.md  TSD.md  SYSTEM_ARCHITECTURE.md
│   ├── MEMORY_MODEL.md  DNA_FORMAT.md  MCP_INTEGRATION.md
│   ├── COST_OPTIMIZATION.md  SECURITY_MODEL.md  GLOSSARY.md
│
├── packages/                       # Python workspace members
│   ├── helix-core/                 # engine: extract/store/recall/consolidate/codec
│   │   ├── pyproject.toml
│   │   └── src/helix_core/
│   │       ├── __init__.py
│   │       ├── ingestion.py  redaction.py  gate.py
│   │       ├── extract/ (deterministic.py, llm.py, base.py)
│   │       ├── embed/   (local.py, cloud.py, base.py)
│   │       ├── stores/  (vector.py, graph.py, base.py)
│   │       ├── consolidate.py  conflict.py  retrieve.py  rank.py
│   │       ├── strand/  (codec.py, crypto.py, manifest.py, merge.py)
│   │       ├── llm/     (router.py, cache.py)
│   │       ├── models.py  config.py  scheduler.py
│   ├── helix-cli/                  # `helix` command
│   │   └── src/helix_cli/ (main.py, commands/…)
│   ├── helix-mcp/                  # MCP server
│   │   └── src/helix_mcp/ (server.py, tools.py, resources.py)
│   └── helix-sdk-python/           # programmatic SDK
│       └── src/helix_sdk/
│
├── sdks/
│   └── typescript/                 # TS SDK + MCP client helpers
│
├── apps/
│   └── dashboard/                  # React + Vite + Tailwind local UI
│
├── examples/                       # end-to-end recipes
└── tests/                          # cross-package integration & perf tests
```

Package boundaries mirror the component diagram (§2.3): `helix-core` is the only place with
business logic; the rest are front-ends. This keeps the surface testable and the cost/privacy
invariants enforceable in one place.

---

## 9. Cross-cutting concerns

- **Config & secrets:** single precedence chain (TSD §9); secrets from env only.
- **Observability:** local structured logs + metrics surfaced in the dashboard; telemetry off
  by default (TSD §10).
- **Cost:** the gate→local→free-tier pipeline is part of the write-path architecture, not an
  optional optimization ([Cost](COST_OPTIMIZATION.md)).
- **Versioning:** strand schema, MCP surface, and embedding space are independently versioned
  (TSD §13).

---

## 10. Why this architecture wins

It collapses five competitor gaps into structural defaults: **local-first** (privacy +
offline + $0), **MCP** (reach every agent with one integration), **single signed strand**
(portability + integrity without a chain), **pluggable backends** (a clean path to teams and
decentralized storage *later* without a rewrite), and **a single engine library** (cost and
privacy invariants enforced in one auditable place). The hard product promises in the
[PRD](PRD.md) fall out of the architecture instead of being bolted on.
