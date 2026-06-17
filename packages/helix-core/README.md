# helix-core

The Helix engine — the only package with business logic. Everything else (CLI, MCP server,
SDK, dashboard) is a thin front-end over this.

Subsystems (see [`docs/TSD.md`](../../docs/TSD.md) §3):

- `ingestion`, `redaction`, `gate` — accept and pre-filter routed slices ($0 cost lever).
- `extract/` — deterministic ($0 floor) and LLM-backed extractors.
- `embed/` — local embeddings by default; cloud optional.
- `stores/` — vector + graph behind Protocols (sqlite-vec + NetworkX default).
- `consolidate`, `conflict`, `retrieve`, `rank` — the ADD/UPDATE/DELETE/NOOP and recall logic.
- `strand/` — the `.dna` codec: sign/encrypt/verify, diff/merge/rollback.
- `llm/` — the optional, free-tier-first router.
- `engine.py` — the façade the rest of the repo calls.

**Status:** pre-alpha. Interfaces are authoritative; implementations land per
[`ROADMAP.md`](../../ROADMAP.md). Any path that calls a model must keep its deterministic,
local fallback working — `$0` mode is a first-class path (see [`CLAUDE.md`](../../CLAUDE.md)).
