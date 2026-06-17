# Helix Dashboard

The local web UI for curating your memory — making it visible, accountable, and editable
(PRD §6.4, ROADMAP Phase 5). React + Vite + Tailwind, talking to the local Helix daemon over
a localhost API.

Planned views:

- **Graph** — browse/search the typed memory graph; see relations.
- **Inspect** — for any fact: source, date, confidence, and *why it believes this* (provenance).
- **Curate** — edit / confirm / forget; tune decay.
- **History** — git-style timeline; diff and rollback.
- **Strands & keys** — export/import/merge `.dna`; manage your signing identity.
- **Cost & telemetry** — local-only: LLM calls/tokens/spend and gate drop-rate (prove you're at $0).

**Status:** pre-alpha placeholder. Scaffolded in Phase 5.
