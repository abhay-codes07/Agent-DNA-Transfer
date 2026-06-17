# Helix — Glossary

Shared vocabulary for the project. If a term here conflicts with code, the code is wrong —
fix it (spec-first invariant, [CLAUDE.md](../CLAUDE.md)).

| Term | Definition |
|---|---|
| **Helix** | The product: a local-first, portable, git-like memory layer for AI coding agents. |
| **Strand** | A user's whole memory as a single self-describing SQLite database; exported as a `.dna` file. |
| **`.dna`** | The portable strand artifact: signed (Ed25519), encrypted (XChaCha20-Poly1305), versioned. |
| **Memory / Fact** | One typed node in the graph (identity, preference, project, decision, entity, convention, snippet, fact). |
| **Edge / Relation** | A typed, weighted link between memories (e.g. `has_decision`, `depends_on`, `supersedes`). |
| **Scope** | Where a fact applies: `global` or `project:<id>`. Recall is scope-aware. |
| **Ingestion** | Accepting a user-routed slice (turn/code/note) for possible learning. No ambient capture. |
| **Slice** | A unit of routed input (a conversation turn, code block, or note) with metadata. |
| **Redaction** | Scrubbing secrets from a slice before any storage or model call (an invariant). |
| **Heuristic gate** | The cheap local check that decides whether a slice is worth extracting from — the main cost lever. |
| **Extraction** | Turning a slice into candidate typed facts (deterministic or LLM-backed). |
| **Embedding** | A vector representation of text used for semantic recall (local bge-small by default). |
| **Consolidation** | Deciding ADD / UPDATE / DELETE / NOOP for each candidate fact against existing memory. |
| **Conflict resolution** | Reconciling contradictory facts (recency > confidence > provenance; optional LLM tie-break). |
| **Recall** | Retrieving relevant memories for an agent (hybrid vector + graph + ranking). |
| **Salience** | A memory's current importance; decays over time unless reinforced. |
| **Confidence** | How sure Helix is a fact is true/durable. |
| **Provenance** | The record of what produced/changed a fact (slice, extractor, model, op) — the "why it believes this". |
| **Decay / Reinforcement** | Salience falling over time vs. rising when a fact is recalled/confirmed/re-seen. |
| **Transfer** | Moving memory between machines/agents/people via `export`/`import`/`merge`. |
| **Merge** | Combining two strands with consolidation + conflict resolution; reversible. |
| **Rollback** | Restoring a prior strand version from history. |
| **Manifest** | The plaintext, signed metadata of a `.dna` (schema, embedding space, counts, integrity root). |
| **MCP** | Model Context Protocol — the open interface through which agents read/write Helix memory. |
| **LLM router** | The component that picks/falls back across LLMs (free-tier-first) — or none at all. |
| **Deterministic extractor** | The no-LLM, rules+embeddings extractor; the $0 floor. |
| **Daemon** | The local Helix process hosting the engine for CLI, MCP server, and dashboard. |
| **ADR** | Architecture Decision Record — an entry in [`DECISIONS.md`](../DECISIONS.md). |
