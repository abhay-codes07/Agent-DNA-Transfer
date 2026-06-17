# Tests

Cross-package integration, performance, and security tests live here; unit tests live next
to their package (e.g. `packages/helix-core/tests/`).

Strategy (TSD §11):

- **Unit** — extractors, consolidation, ranking, codec round-trips, crypto.
- **Golden** — fixed slices → expected fact sets (both extractor engines).
- **Property** — strand encode→decode→verify is lossless; merge never corrupts.
- **Integration** — MCP server vs. a mock agent; `connect` writes valid configs.
- **Performance** — recall p95 on synthetic 10⁵–10⁶-node strands.
- **Security** — redaction never leaks a secret into a strand; tampered manifests rejected.

The **no-key / offline ($0) path is a first-class CI configuration** so the free experience
can never silently regress (CLAUDE.md rule 3).
