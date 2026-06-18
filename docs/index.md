# Helix

### Take your AI's memory anywhere.

**A local-first, portable, git-like memory layer for every AI coding agent.**

Helix gives your AI a long-term memory that *belongs to you* — your preferences, projects,
decisions, and coding style — and lets you carry it across Claude Code, Cursor, Copilot,
Windsurf, ChatGPT, Gemini, and any MCP-compatible agent. One memory. Every agent. Owned by you.

It runs **$0 and offline by default**: a dependency-free core, an embedded vector + graph store
in one SQLite file, and a portable, signed, encrypted **`.dna`** strand you can `export`,
`import`, `merge`, and `push`/`pull` like code.

## Start here

- **Why & what** → [PRD](PRD.md), [Competitive Analysis](COMPETITIVE_ANALYSIS.md)
- **How it works** → [System Architecture](SYSTEM_ARCHITECTURE.md), [Technical Spec](TSD.md),
  [Memory Model](MEMORY_MODEL.md), [Retrieval](RETRIEVAL.md)
- **Portability** → [`.dna` Format](DNA_FORMAT.md), [Sync & Merge](SYNC.md)
- **Trust** → [Security Model](SECURITY_MODEL.md), [Privacy & Compliance](PRIVACY_COMPLIANCE.md)
- **The research behind it** → [Research Survey](RESEARCH.md)

The decision log (ADRs), roadmap, changelog, and source live in the
[GitHub repository](https://github.com/abhay-codes07/Agent-DNA-Transfer).

!!! note "Status"
    Working alpha (v0.1.0). The core product is built and tested; see the repository's
    `ROADMAP.md` for what's next.
