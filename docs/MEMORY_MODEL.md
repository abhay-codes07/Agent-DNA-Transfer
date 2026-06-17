# Helix — Memory Model

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD](TSD.md) · [DNA Format](DNA_FORMAT.md)

The schema for what Helix remembers and how each memory lives, evolves, and dies. This is
the coding-native heart of the product — the thing generic memory layers don't model.

---

## 1. Design goals

- **Typed, not blobby.** Memory is a graph of typed facts, not a pile of text.
- **Coding-native first.** Repos, stacks, conventions, and decisions are first-class.
- **Accountable.** Every fact carries source, time, confidence, and provenance.
- **Editable & reversible.** Anything can be confirmed, corrected, or forgotten — with history.
- **Schema-pluggable.** The coding schema is the default; other domains plug in later (PRD §4).

---

## 2. Node types

| Type | What it captures | Example |
|---|---|---|
| `identity` | Who the user is | "Senior backend dev; Go + Python; prefers terse answers" |
| `preference` | How they like things done | "Use `pytest`, never `unittest`; tabs in Go, spaces elsewhere" |
| `project` | A codebase and its shape | "`billing-svc`: FastAPI + Postgres; event-driven via NATS" |
| `decision` | A durable choice + rationale | "Chose Postgres over Mongo for billing — needs ACID; 2026-05" |
| `entity` | People/teams/repos/services | "Priya owns `auth-svc`; on-call rotation in #infra" |
| `convention` | Rules/standards in a context | "All API errors use RFC-7807 problem+json" |
| `snippet` | Reusable code idiom/pattern | "Standard retry-with-jitter helper (Python)" |
| `fact` | Generic catch-all durable fact | "Deploys are frozen on Fridays" |

Types are extensible; new domains register additional types without touching the engine.

## 3. Node schema

```jsonc
{
  "id": "01J...",            // UUIDv7 (time-sortable)
  "type": "decision",
  "content": "Chose Postgres over Mongo for billing — needs ACID transactions.",
  "scope": "project:billing-svc",   // "global" or "project:<id>"
  "attributes": {                    // type-specific, validated per type
    "alternatives": ["MongoDB"],
    "rationale": "Strong consistency for money; mature tooling",
    "decided_on": "2026-05-14"
  },
  "embedding_ref": "vec_memories:01J...",
  "confidence": 0.9,        // how sure Helix is this is true/durable
  "salience": 0.7,          // current importance; decays unless reinforced
  "status": "active",       // active | archived | forgotten | superseded
  "source": { "agent": "claude-code", "ref": "session:...", "ingested_at": "..." },
  "created_at": "...",
  "updated_at": "...",
  "last_seen_at": "..."     // reinforcement signal
}
```

## 4. Edges (relations)

The graph is what makes recall smart: pulling a `project` should also surface its
`decisions` and `conventions`.

```jsonc
{ "id": "...", "from_id": "<project>", "to_id": "<decision>",
  "relation": "has_decision", "weight": 1.0, "source": {...}, "created_at": "..." }
```

Common relations: `works_on`, `owns`, `depends_on`, `has_decision`, `has_convention`,
`prefers`, `uses`, `supersedes`, `contradicts`, `related_to`. Edges carry provenance too.

## 5. Scope

- `global` — true about the user everywhere (identity, broad preferences).
- `project:<id>` — true within one codebase (architecture, conventions, decisions).

Recall is scope-aware: an agent working in `billing-svc` gets that project's memory plus
global facts, not unrelated projects'. Scope keeps recall relevant and prevents cross-project
bleed.

## 6. Lifecycle

```
 candidate ──extract──► [consolidate] ──► ADD ─────► active
                                       ├─► UPDATE ──► active (confidence↑, provenance+)
                                       ├─► NOOP ────► (unchanged)
                                       └─► SUPERSEDE► old:superseded, new:active

 active ──(no reinforcement, decay)──► low salience ──► proposed archival ──► archived
 active ──user forgets──► forgotten (soft delete, recoverable from history)
```

- **Reinforcement:** being recalled, confirmed, or re-observed bumps `salience`/`last_seen`.
- **Decay:** `salience` falls on a slow half-life; stale low-confidence facts sink, then are
  *proposed* (never auto-forced) for archival.
- **Supersession:** contradictions never hard-delete; the old fact is kept `superseded` with a
  `supersedes` edge so history and rollback work.
- **Forget:** user-initiated soft delete; recoverable via `helix log`/`rollback` until purged.

See [TSD §6.3/§6.5/§6.6](TSD.md) for the algorithms behind each transition.

## 7. Provenance (why it believes this)

Every node and edge links to one or more provenance records: the slice it came from, the
extractor and model used, and the consolidation op that created/changed it. The dashboard's
"why?" button reads this. Provenance is also how merge keeps both contributors' history when
two strands combine.

## 8. What is NOT stored

- **Raw transcripts.** Helix stores distilled facts, not chat logs (privacy + size).
- **Secrets.** Redaction removes keys/tokens/.env values *before* storage (invariant).
- **Anything not routed.** No ambient capture; the user chooses what Helix sees.

## 9. Example mini-graph

```
 (identity: "prefers terse, typed Python")
        │ prefers
        ▼
 (preference: "pytest over unittest") ──related_to──► (convention: "100% type hints in core")
                                                              ▲ has_convention
 (project: billing-svc) ──has_decision──► (decision: "Postgres over Mongo")
        │ depends_on                         │ decided_by
        ▼                                    ▼
 (entity: auth-svc)                    (entity: "Priya")
```

A query like *"how do we handle the billing DB?"* hits the decision via vector search, then
graph-expands to the project, its conventions, and the owning entity — exactly the context a
coding agent needs, surfaced without the user re-explaining anything.
