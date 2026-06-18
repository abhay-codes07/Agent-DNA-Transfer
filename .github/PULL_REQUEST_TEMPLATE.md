<!-- Thanks for contributing to Helix! Keep PRs small and focused. -->

## What & why

<!-- What does this change, and why? Link the issue: Closes #123 -->

## Checklist

- [ ] Tests added/updated; `pytest` is green (the **$0/offline path** stays first-class).
- [ ] `ruff check`, `black --check`, and `mypy` pass.
- [ ] Docs updated **in the same PR** if behavior/specs changed (spec-first — code and docs must agree).
- [ ] No new **required** network/cloud dependency on a core path; any LLM/cloud use is opt-in.
- [ ] Default cost stays **$0** (if not, there's a `DECISIONS.md` ADR explaining why).
- [ ] No secrets, `.env`, or `.dna` strands committed.
- [ ] If this changes the MCP surface or `.dna` format, an **ADR** was added to `DECISIONS.md`.

## Notes for reviewers

<!-- Anything tricky, trade-offs, follow-ups, or screenshots. -->
