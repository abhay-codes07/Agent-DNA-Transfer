# CLAUDE.md

Guidance for AI agents (Claude Code, Cursor, etc.) working **inside this repository**.
This is the contract for how to contribute to Helix. Read it before writing code.

> Not to be confused with the product itself. Helix *gives agents memory*; this file
> tells agents *how to build Helix*.

---

## What this project is

**Helix** is a local-first, portable, git-like **memory layer for AI coding agents**.
It extracts durable facts from the conversations/code a user chooses to share, stores
them as a typed knowledge graph in an embedded vector + graph store, and serves them to
any agent over the **Model Context Protocol (MCP)**. Memory is packaged as a portable,
signed, encrypted **`.dna` strand**.

If you're new, read in this order:
1. [`docs/PRD.md`](docs/PRD.md) — what we're building and why.
2. [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) — how the pieces fit.
3. [`docs/TSD.md`](docs/TSD.md) — the technical contract.
4. [`DECISIONS.md`](DECISIONS.md) — why things are the way they are. **Append here when you change a decision.**

## Golden rules

1. **Local-first, always.** No feature may *require* a network call or cloud account to
   work. Cloud (embeddings, sync, LLM) is strictly opt-in and degradable. If you add a
   dependency on a hosted service for a core path, that's a bug.
2. **The user owns the memory.** Every stored fact must be human-readable, editable,
   sourced, and deletable. Never store opaque blobs the user can't inspect. No silent
   collection — Helix only ingests what the user explicitly routes to it.
3. **$0 by default.** The default configuration must run with **zero API spend**: local
   embeddings, embedded stores, and an LLM router that prefers a free tier and skips the
   LLM entirely when a heuristic suffices. Any change that increases default cost must be
   justified in `DECISIONS.md` and gated behind config.
4. **Privacy is not a feature, it's the foundation.** Strands are encrypted at rest.
   Signing keys never leave the device unless the user exports them. Telemetry is
   off by default and, when on, is local-only unless explicitly shared.
5. **MCP is the interface.** Agents talk to Helix through MCP tools/resources, never by
   reaching into internals. Keep the MCP surface small, stable, and documented in
   [`docs/MCP_INTEGRATION.md`](docs/MCP_INTEGRATION.md).
6. **Specs before code.** This repo is spec-first. If your change contradicts a doc,
   update the doc in the same change. Code and docs must never disagree.

## Tech stack (see DECISIONS.md for rationale)

| Layer | Choice |
|---|---|
| Core engine, CLI, MCP server | **Python 3.11+**, managed with **`uv`** |
| Embeddings (default) | **local** via `fastembed` (BAAI/bge-small-en-v1.5) — no API |
| Embeddings (optional cloud) | Gemini `text-embedding-004` (free tier) / OpenAI `text-embedding-3-small` |
| Vector store | **`sqlite-vec`** (embedded; the strand *is* a SQLite file) |
| Graph store | SQLite relational tables + in-memory NetworkX projections |
| LLM router | **LiteLLM**; default **Gemini 2.0 Flash** (free tier) → fallback **gpt-4o-mini** |
| Optional cloud sync API | **FastAPI** |
| Dashboard | **TypeScript + React + Vite + Tailwind** |
| Crypto | libsodium / PyNaCl — XChaCha20-Poly1305 (encrypt), Ed25519 (sign) |
| Lint / format / types | `ruff`, `black`, `mypy` (Python); `eslint`, `prettier` (TS) |
| Tests | `pytest` (+ `pytest-cov`); `vitest` (TS) |

## Repository layout

```
helix/
├── docs/                  # the source of truth — read before coding
├── packages/
│   ├── helix-core/        # extraction, stores, retrieval, consolidation, .dna codec
│   ├── helix-cli/         # `helix` command (init/connect/export/import/merge/log)
│   ├── helix-mcp/         # MCP server exposing memory tools/resources to agents
│   └── helix-sdk-python/  # programmatic API
├── apps/
│   └── dashboard/         # local web UI to browse/edit the memory graph
├── sdks/
│   └── typescript/        # TS SDK + MCP client helpers
├── examples/              # end-to-end usage recipes
├── DECISIONS.md           # architecture decision record (append-only-ish)
├── ROADMAP.md
└── CLAUDE.md              # you are here
```

> Some packages are scaffolds/stubs during pre-alpha. The structure is authoritative even
> where the implementation is pending — build into it, don't around it.

## How to work here

- **Environment:** Windows-friendly. The shell is PowerShell; a Bash tool is available for
  POSIX scripts. Prefer cross-platform Python over shell where possible. Use forward
  slashes in code; never hard-code a user's home path.
- **Setup (target):** `uv sync` at the workspace root; `uv run helix --help` to smoke-test.
- **Before you commit:** run `ruff check`, `black --check`, `mypy`, and `pytest`. For TS,
  `pnpm lint && pnpm test`. Don't commit secrets — `.env` is gitignored; use `.env.example`.
- **Commits:** small, logical, present-tense. End commit messages with the
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer. **Do not push** unless
  the user explicitly asks. Branch before committing to `main` for non-trivial work.
- **Secrets/keys:** This project may use a Gemini or OpenAI key for the LLM router. Read it
  from the environment (`GEMINI_API_KEY`, `OPENAI_API_KEY`) only. Never log it, never write
  it into a strand, never commit it.

## Coding conventions

- Match the surrounding code's style, naming, and comment density. Don't introduce a new
  pattern when an existing one fits.
- Public functions get type hints and a one-line docstring stating the contract.
- Keep the LLM optional: any code path that calls a model must have a deterministic,
  local fallback (even if lower quality) so `$0` mode still works.
- Every fact written to the graph must carry: `source`, `created_at`, `confidence`,
  and `type`. No exceptions — downstream features (audit, decay, merge) depend on it.
- Errors that touch user memory must fail safe: never corrupt or partially-write a strand.
  All strand mutations go through the transactional codec in `helix-core`.

## What NOT to do

- Don't add a cloud dependency to a core path (see rule 1).
- Don't store raw conversation logs — Helix stores *distilled facts*, not transcripts.
- Don't expand the MCP tool surface without updating `docs/MCP_INTEGRATION.md` and `DECISIONS.md`.
- Don't bump default cost above $0 without an ADR entry.
- Don't push to the remote unless explicitly asked.

## Pointers

- Product spec → [`docs/PRD.md`](docs/PRD.md)
- Technical contract → [`docs/TSD.md`](docs/TSD.md)
- Memory schema (bi-temporal, typed) → [`docs/MEMORY_MODEL.md`](docs/MEMORY_MODEL.md)
- Memory lifecycle (decay/reflection) → [`docs/CONSOLIDATION.md`](docs/CONSOLIDATION.md)
- Retrieval pipeline → [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md)
- Portable format → [`docs/DNA_FORMAT.md`](docs/DNA_FORMAT.md)
- Sync & merge → [`docs/SYNC.md`](docs/SYNC.md)
- Agent surface → [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) · [`docs/MCP_INTEGRATION.md`](docs/MCP_INTEGRATION.md)
- Extension points → [`docs/PLUGINS.md`](docs/PLUGINS.md)
- Cost rules → [`docs/COST_OPTIMIZATION.md`](docs/COST_OPTIMIZATION.md)
- Security/threat model → [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md) · privacy → [`docs/PRIVACY_COMPLIANCE.md`](docs/PRIVACY_COMPLIANCE.md)
- Evaluation → [`docs/EVALUATION.md`](docs/EVALUATION.md)
- Why-it's-this-way (the research) → [`docs/RESEARCH.md`](docs/RESEARCH.md)
- Decisions & changes (30 ADRs) → [`DECISIONS.md`](DECISIONS.md)

> **Before implementing a subsystem, read its dedicated doc above** — they carry the
> research-backed algorithms (e.g. RRF k=60, Personalized PageRank, per-type decay half-lives,
> XChaCha20 secretstream, BLAKE3 Merkle). The Wave-2 ADRs (012–030) are the binding decisions.
