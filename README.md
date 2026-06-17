<div align="center">

# 🧬 Helix

### Take your AI's memory anywhere.

**A local-first, git-like portable memory layer for every AI coding agent.**

Helix gives your AI a long-term memory that *belongs to you* — your preferences, your
projects, your decisions, your coding style — and lets you carry it across Claude Code,
Cursor, Copilot, Windsurf, ChatGPT, Gemini, and any MCP-compatible agent.

One memory. Every agent. Owned by you.

[Product Requirements](docs/PRD.md) ·
[Technical Spec](docs/TSD.md) ·
[Architecture](docs/SYSTEM_ARCHITECTURE.md) ·
[Decisions](DECISIONS.md) ·
[Roadmap](ROADMAP.md)

![status](https://img.shields.io/badge/status-pre--alpha-orange)
![license](https://img.shields.io/badge/license-Apache--2.0-blue)
![local-first](https://img.shields.io/badge/local--first-yes-brightgreen)
![cost](https://img.shields.io/badge/default%20cost-%240%2Fmo-brightgreen)

</div>

---

## The problem

Every AI agent you use is slowly learning who you are — your stack, your conventions,
the architecture of the project you've explained five times, the fact that you prefer
`pytest` over `unittest` and tabs in Go but spaces everywhere else.

Then you switch tools. Or the session ends. Or the context window fills up. And it's
**gone**. You start from zero, re-explaining yourself to a machine that should already know.

Today that memory is:

- **Trapped** — locked inside one vendor's cloud (ChatGPT memory ≠ Claude memory ≠ Cursor memory).
- **Opaque** — you can't see it, edit it, audit it, or delete a single wrong fact.
- **Not yours** — it lives on someone else's servers, under someone else's terms.
- **Not portable** — there is no "export my brain and import it elsewhere."

## The idea

**Helix is a memory layer that lives with _you_, not with a vendor.**

It watches the conversations and code you *choose* to share, extracts durable facts,
stores them locally as a structured **knowledge graph**, and serves them back to *any*
agent through the open **Model Context Protocol (MCP)** — so every tool you use wakes up
already knowing you.

The whole thing is packaged as a portable, signed, encrypted file: a **`.dna` strand**.
Move it between laptops. Sync it to a teammate. Version it like code. Roll it back when
an agent learns something wrong.

```
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │  Claude Code │     │    Cursor    │     │   ChatGPT    │
  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
         │  MCP               │  MCP               │  MCP
         └────────────────────┼────────────────────┘
                              ▼
                   ┌─────────────────────┐
                   │     Helix Engine    │   extract · store · recall · consolidate
                   │  (runs on YOUR box) │
                   └──────────┬──────────┘
                              ▼
                     🧬  your-brain.dna
                  (signed · encrypted · versioned)
```

## Why this is different

| | ChatGPT/Claude memory | Mem0 / OpenMemory | **Helix** |
|---|---|---|---|
| Works across vendors | ❌ | ✅ (MCP) | ✅ (MCP) |
| Local-first / offline | ❌ | partial | ✅ default |
| You can read & edit every fact | ❌ | partial | ✅ full graph UI |
| Coding-aware (repos, stacks, decisions) | ❌ | ❌ generic | ✅ first-class |
| Portable single-file export | ❌ | ❌ | ✅ `.dna` |
| Git-like (diff / merge / rollback / branch) | ❌ | ❌ | ✅ |
| Default running cost | $$ | $/cloud | **$0** (local embeddings) |
| Team / org shared memory | ❌ | enterprise | ✅ shareable strands |

> Walrus Memory proved people want portable, verifiable agent memory. Mem0 proved the
> extraction/consolidation engine works. **Helix is what happens when you make that
> coding-native, local-first, free to run, and as easy to move around as a git repo.**

## What Helix remembers

Helix doesn't store raw chat logs. It distills them into a typed **memory graph**:

- **Identity** — who you are, role, expertise, tooling.
- **Preferences** — style, formatting, libraries you like/avoid, how you want to be talked to.
- **Projects** — architecture, services, conventions, gotchas, "why we did it this way."
- **Decisions** — durable choices and their rationale (your personal ADR log).
- **People & teams** — collaborators, ownership, who knows what.
- **Snippets & patterns** — reusable code idioms you keep reaching for.

Every node is timestamped, sourced, confidence-scored, and editable.

## Quick start (target experience — see [Roadmap](ROADMAP.md) for status)

```bash
# 1. Install
pipx install helix-memory          # or: uv tool install helix-memory

# 2. Create your memory strand (one local, encrypted file)
helix init

# 3. Connect it to your agents (writes MCP config for each)
helix connect claude-code
helix connect cursor

# 4. ...just work. Helix learns in the background.

# 5. Take it anywhere
helix export ~/Desktop/my-brain.dna      # signed + encrypted bundle
helix import my-brain.dna                 # on a new machine
helix merge teammate.dna                  # combine memories, resolve conflicts
helix log                                 # see how your memory evolved, git-style
```

By default Helix runs **100% locally and free**: local embeddings, an embedded vector +
graph store, and an LLM router that only calls a model when it actually needs one — and
prefers a free tier when it does. See [Cost Optimization](docs/COST_OPTIMIZATION.md).

## Documentation

**Product & strategy**
| Doc | What's inside |
|---|---|
| [PRD](docs/PRD.md) | Vision, personas, problem, scope, requirements, metrics, GTM |
| [Competitive Analysis](docs/COMPETITIVE_ANALYSIS.md) | 11-product teardown + the 6-axis positioning table |
| [Business Model & GTM](docs/BUSINESS.md) | Open-core, pricing principles, growth loops |
| [Roadmap](ROADMAP.md) | Phased plan from MVP to platform |
| [Research Survey](docs/RESEARCH.md) | The cited literature/landscape behind every decision |

**Engineering**
| Doc | What's inside |
|---|---|
| [Technical Spec (TSD)](docs/TSD.md) | Components, data model, APIs, algorithms, tech choices |
| [System Architecture](docs/SYSTEM_ARCHITECTURE.md) | Diagrams, data flow, deployment, scaling, trust boundaries |
| [Memory Model](docs/MEMORY_MODEL.md) | Typed graph schema: episodic/semantic/procedural + bi-temporal |
| [Consolidation, Decay & Reflection](docs/CONSOLIDATION.md) | CLS two-stage, decay/reinforcement, reflection, sleep-time |
| [Retrieval Pipeline](docs/RETRIEVAL.md) | Hybrid + RRF + graph PPR + MMR; no LLM on the hot path |
| [`.dna` Format](docs/DNA_FORMAT.md) | The portable, signed, encrypted bundle spec |
| [Sync & Merge](docs/SYNC.md) | Optional E2E sync; CRDT + 3-way semantic merge |
| [Cost Optimization](docs/COST_OPTIMIZATION.md) | How Helix stays at ~$0 |
| [API Reference](docs/API_REFERENCE.md) | MCP tools, local daemon REST, SDKs |
| [MCP Integration](docs/MCP_INTEGRATION.md) | Tools/resources exposed to agents |
| [Plugins & Extensions](docs/PLUGINS.md) | Pluggable embeddings/stores/LLM/connectors |
| [Observability](docs/OBSERVABILITY.md) | Local metrics + the "$0" cost dashboard |

**Trust, quality & process**
| Doc | What's inside |
|---|---|
| [Security Model](docs/SECURITY_MODEL.md) | Encryption, signing, threat model, anti-poisoning |
| [Privacy & Compliance](docs/PRIVACY_COMPLIANCE.md) | Redaction, GDPR erasure cascade, never-fine-tune |
| [Evaluation & Benchmarks](docs/EVALUATION.md) | LongMemEval, the coding-memory benchmark gap, harness |
| [Governance & RFCs](docs/GOVERNANCE.md) | Roles, RFC process, versioning, commercial layer |
| [Decisions (ADR)](DECISIONS.md) | Every meaningful choice + why, and what changed (30 ADRs) |
| [Glossary](docs/GLOSSARY.md) | Shared vocabulary |
| [CLAUDE.md](CLAUDE.md) | Guidance for AI agents working *in this repo* |

## Project status

**Pre-alpha — planning & scaffolding.** This repository currently contains the full
product and technical design. Implementation is phased; see the [Roadmap](ROADMAP.md).
Everything here is intentionally specified before being built so contributors (human and
AI) share one source of truth.

## License

[Apache-2.0](LICENSE). Your memory is yours; the engine is open.

<div align="center">
<sub>Built in the open. Memory should belong to the human, not the model.</sub>
</div>
