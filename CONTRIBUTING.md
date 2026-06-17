# Contributing to Helix

Thanks for wanting to help build a memory layer that belongs to the user. This guide
explains how we work. The short version: **read the specs, keep it local-first and free,
update docs in the same change as code.**

## Ground rules (non-negotiable)

These mirror the golden rules in [`CLAUDE.md`](CLAUDE.md):

1. **Local-first.** No feature may require a network call or account to function.
2. **User owns the memory.** Every fact is readable, editable, sourced, deletable.
3. **$0 by default.** Don't raise default cost without an ADR in [`DECISIONS.md`](DECISIONS.md).
4. **Privacy first.** Encrypt at rest; never log or persist secrets; telemetry off by default.
5. **MCP is the interface.** Don't grow the MCP surface without updating the spec.
6. **Specs before code.** If your change contradicts a doc, fix the doc in the same PR.

## Getting set up (target — pre-alpha)

```bash
git clone https://github.com/abhay-codes07/Agent-DNA-Transfer.git
cd Agent-DNA-Transfer
uv sync                      # Python workspace
uv run helix --help          # smoke test the CLI
pnpm -C apps/dashboard install   # dashboard (optional)
```

## Workflow

1. **Find or open an issue.** Describe the problem before the solution.
2. **Branch** from `main`: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`.
3. **Make the change**, with tests. Keep PRs small and focused.
4. **Run checks locally** (see below) — green before you push.
5. **Update docs** touched by the change (PRD/TSD/architecture/ADR).
6. **Open a PR** describing *what* and *why*. Link the issue and any ADR.

## Quality gates

Python:
```bash
uv run ruff check .
uv run black --check .
uv run mypy packages
uv run pytest --cov
```
TypeScript:
```bash
pnpm lint && pnpm test
```

A change to anything that calls an LLM must keep the **no-LLM local fallback** working and
tested — `$0` mode is a first-class path, not a degraded one.

## Commit & PR conventions

- Conventional-commit-ish subjects: `feat(core): add memory decay`, `fix(cli): ...`, `docs: ...`.
- Small, logical commits. Don't mix refactors with behavior changes.
- AI-assisted commits include the trailer:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Never commit secrets, `.env`, or `.dna` strands (user data). See [`.gitignore`](.gitignore).

## Where things live

See [`docs/SYSTEM_ARCHITECTURE.md`](docs/SYSTEM_ARCHITECTURE.md) for the full layout. Quick map:

- `packages/helix-core` — engine (extraction, stores, retrieval, consolidation, `.dna` codec)
- `packages/helix-cli` — the `helix` command
- `packages/helix-mcp` — MCP server
- `packages/helix-sdk-python` / `sdks/typescript` — SDKs
- `apps/dashboard` — local web UI
- `docs/` — the source of truth

## Reporting security issues

Do **not** open a public issue for vulnerabilities. See [`SECURITY.md`](SECURITY.md).

## Code of Conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Be kind; assume good faith.
