# Helix — Project Governance & RFC Process

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [Contributing](../CONTRIBUTING.md) · [Decisions](../DECISIONS.md) · [Business](BUSINESS.md)

How decisions get made, how the project is structured, and how big changes are proposed. Helix
is open-source (Apache-2.0) and spec-first; governance exists to keep the invariants intact as
the contributor base grows.

## 1. Principles

- **The invariants are non-negotiable.** Local-first, user-owns-memory, $0-default, MCP
  interface, spec-first ([CLAUDE.md](../CLAUDE.md) golden rules). Governance protects these.
- **Decisions are written down.** Every meaningful choice is an ADR in [`DECISIONS.md`](../DECISIONS.md);
  reversing one means a new ADR, never silent edits.
- **Open by default.** Discussion, roadmap, and decisions happen in public (issues/PRs/RFCs).

## 2. Roles

| Role | Responsibility |
|---|---|
| **Maintainers** | Review/merge, cut releases, steward the invariants, accept/reject RFCs |
| **Core team** | Maintainers with commit + release rights; final call on ADRs |
| **Contributors** | Anyone with a merged change; can author RFCs and draft ADRs |
| **Users** | File issues, request features, vote on RFCs via reactions |

Early-stage: a small core team (the founders). As the project grows, maintainership is earned
through sustained, high-quality contribution and is granted by existing maintainers.

## 3. The RFC process (for substantial changes)

Use an RFC when a change is cross-cutting, alters a public interface (MCP surface, `.dna`
format, SDK), affects an invariant, or is otherwise hard to reverse.

```
idea → discussion issue → RFC PR (docs/rfcs/NNNN-title.md) → review (≥2 maintainers)
     → accepted → ADR recorded in DECISIONS.md → tracked in ROADMAP → implemented
```

An RFC states: motivation, design, alternatives, security/privacy/cost impact (must show it
preserves the invariants), migration/compat, and open questions. Small/local changes skip the
RFC and go straight to a PR.

## 4. Versioning & stability

Three independently versioned surfaces (TSD §13):
- **`.dna` format version** — strands self-describe; the codec migrates forward and refuses
  unknown-newer strands. Breaking format changes require an RFC + a migration path.
- **MCP tool surface** — semver'd; growth requires an ADR ([ADR-023](../DECISIONS.md)); stable
  names + `tools/list_changed` for clients.
- **SDK / library API** — semver; deprecations carry one minor-version of warning.

Releases follow semver; pre-1.0 may break with clear notes. Security fixes are backported to
the latest minor.

## 5. Security & disclosure

Vulnerabilities go through [`SECURITY.md`](../SECURITY.md) (private disclosure), not public
issues. A security review + redaction/crypto audit is a gate before any public launch
([ROADMAP](../ROADMAP.md) cross-phase). Maintainers coordinate disclosure windows and credit.

## 6. Trademark & naming

"Helix" is a working brand pending a trademark/availability check before public launch
([ADR-002](../DECISIONS.md)). The Apache-2.0 license does **not** grant trademark rights; the
name and logo are governed separately. The repo (`Agent-DNA-Transfer`) is the descriptive
umbrella.

## 7. Commercial layer & conflicts of interest

The core engine, CLI, MCP server, and SDKs are Apache-2.0 **forever, with a public
no-relicense commitment** ([ADR-028](../DECISIONS.md)). Any commercial offering (team sync,
hosted backup, org policy, managed cloud) is a **separate layer** and must never degrade the
open core or charge to read your own local memory. Maintainers disclose commercial affiliations.

## 8. Code of Conduct

All participation is governed by the [Code of Conduct](../CODE_OF_CONDUCT.md). Enforcement is a
maintainer responsibility.
