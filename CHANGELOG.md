# Changelog

All notable changes to Helix are documented here. Format: [Keep a Changelog](https://keepachangelog.com);
this project aims for [Semantic Versioning](https://semver.org).

## [0.1.1] — 2026-06-20

The v2 wave: **"Git for your AI's memory."** 162 tests; ruff + black + mypy clean; CI green. Still
$0/offline by default, core dependency-free. PyPI distribution names: the **`helix-dna-*`** family
(`pipx install helix-dna`).

### Added — memory intelligence
- **Procedural / skill memory** (`helix learn` / `how`) — verified how-to recipes keyed by triggers,
  with SM-2 reliability.
- **Sleep-time consolidation** (`helix sleep`), **staleness detection** + review queue,
  **conflict surfacing**, **change-as-event timeline**, opt-in **A-MEM auto-linking**.

### Added — trust, collaboration, retrieval
- **Erasure cascade + tombstones + DSAR**, **scoped redacted sharing + quarantine** (TOFU),
  **per-fact Ed25519 signing** wired into share/merge verification, a **tamper-evident audit log**,
  **CRDT merge** (`merge_replica`), governance (`propose`/`review`), multi-agent **handoff**.
- **Optional reranker**, **complexity-gated deep recall**, **proactive surfacing**, **themes**,
  retention **purge**, **bitemporal `as_of`**.

### Added — surfaces & the standard
- Redesigned **local dashboard** (copilot, canvas knowledge graph, review queue, $0-meter + heatmap,
  time-travel slider, audit, cmd-K, "graph assembles itself" onboarding); Host/Origin hardening.
- **GitHub/repo connector** (`helix repo`), **LangGraph + AutoGen** adapters, **VS Code** + **browser**
  extensions.
- **Portable Agent Memory** open standard (`helix export-portable` / `conform`) — the "USB for AI memory".

### Fixed
- Relay drains the request body before rejecting a PUT (removes an intermittently-flaky test).

## [0.1.0] — 2026-06-18

First working alpha. A local-first, portable, git-like memory layer for AI coding agents that
runs **$0 and offline by default** (stdlib-only core; `fastembed`, PyNaCl, an LLM, and MCP are
graceful opt-ins). 74 tests; ruff + black + mypy clean; CI configured.

### Added — core memory ($0 / offline)
- Write path: redact → heuristic gate → extract → embed → consolidate → store.
- Typed, **bi-temporal** knowledge graph in one SQLite file (vectors + graph + FTS + history).
- Consolidation: ADD / UPDATE / NOOP / **SUPERSEDE**, with **LLM-assisted gray-band
  adjudication** when a model is configured (deterministic otherwise).
- Hybrid retrieval: dense + keyword → RRF → graph (PPR-lite) expansion → multi-signal ranking
  → MMR; read-time decay + SM-2 reinforcement; `maintain` archival; **`reflect`** (LLM insight
  synthesis from clusters of facts, cited via `derived_from`).
- Embeddings: dependency-free hashing embedder default; **fastembed (bge-small)** when installed.
- `ingest` (seed memory from markdown/notes files or folders, batched) and Markdown export.

### Added — reach & portability
- **MCP server** (FastMCP/stdio) + `connect` for 8 clients (Claude Code/Desktop, Cursor,
  Windsurf, VS Code, Gemini, Zed, Codex) and a `--path` override for any other.
- **Optional LLM router** (Gemini free-tier → gpt-4o-mini → Ollama), cached + token-budgeted;
  **batched extraction** (one call for many slices).
- **Portable `.dna` strand** — signed (Ed25519), encrypted (XChaCha20-Poly1305, chunked,
  truncation-resistant), versioned; **BLAKE3** Merkle (BLAKE2b fallback) **verified on import**;
  export / verify / import / merge / diff / rollback; re-embed on import.
- **Encrypted team sync** — `push` / `pull` over a local folder, an **HTTP object store**, or
  **S3/R2**, plus a thin **`helix relay`** server; the backend only ever sees ciphertext.
- **Swappable store interface** (`Store`) with the default SQLite backend and an experimental
  **Postgres + pgvector** backend (`PgVectorStore`) for large/shared strands.

### Added — surfaces & quality
- Local **dashboard** (stdlib HTTP daemon + self-contained HTML): browse/search/add/edit/forget,
  provenance ("why"), history timeline, graph, stats.
- **SDKs**: Python (full parity) and TypeScript (daemon client).
- **`helix eval`** recall-quality benchmark (precision/recall@k, MRR, latency).
- Apache-2.0; zero-dependency core packaged with optional extras (`[embeddings]`, `[crypto]`,
  `[all]`); `py.typed`; GitHub Actions CI.

### Tooling
- GitHub Actions: CI (ruff + black + mypy + pytest), a release workflow (PyPI Trusted
  Publishing on tag), and a docs deploy (MkDocs Material).

### Known gaps (see ROADMAP)
PyPI publish (workflow ready, not yet published) and full Node-built frontends remain. The
React/Vite dashboard and TypeScript SDK are written against the daemon API but not built in CI;
the `PgVectorStore` is experimental (no Postgres in CI). The stdlib dashboard + SQLite are the
tested defaults.

[0.1.0]: https://github.com/abhay-codes07/Agent-DNA-Transfer/releases/tag/v0.1.0
