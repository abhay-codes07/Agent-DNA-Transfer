# Helix — Memory Model

**Status:** Draft v2 · **Last updated:** 2026-06-18 · **Related:** [TSD](TSD.md) · [Consolidation](CONSOLIDATION.md) · [Retrieval](RETRIEVAL.md) · [.dna Format](DNA_FORMAT.md) · [Decisions](../DECISIONS.md)

The schema for what Helix remembers and how each memory lives, evolves, and dies. This is the
coding-native, cognitively-grounded heart of the product — the thing generic memory layers
don't model. v2 folds in the deep-research pass: a cognitive memory taxonomy, a bi-temporal
fact model, and a decay/reinforcement model. See [`docs/RESEARCH.md`](RESEARCH.md) for sources.

---

## 1. Design goals

- **Typed, not blobby.** Memory is a graph of typed facts, not a pile of text.
- **Cognitively grounded.** Mirror the human episodic / semantic / procedural split, which
  have genuinely different decay rates, retrieval triggers, and consolidation paths ([ADR-012](../DECISIONS.md)).
- **Coding-native first.** Repos, decisions, conventions, and snippets are first-class.
- **Accountable & reversible.** Every fact carries source, time, confidence, and provenance;
  anything can be confirmed, corrected, or forgotten — with history ([ADR-029](../DECISIONS.md)).
- **Time-aware.** Facts change; the model is **bi-temporal** so we never lose the audit trail
  ([ADR-013](../DECISIONS.md)).
- **Schema-pluggable.** The coding schema is the default; other domains plug in later.

---

## 2. The cognitive layer: four shapes of memory

Long-term memory has four first-class shapes ([ADR-012](../DECISIONS.md)). The live agent
context window is **working memory** — it is *never* the system of record.

| Shape | Human analog | What Helix stores | Default half-life |
|---|---|---|---|
| **Episodic** | Events bound to time/place | "On 2026-06-12, fixed flaky test X by mocking Y" | ~7 days (decays) |
| **Semantic** | Facts / general knowledge | "This repo uses pnpm, not npm" | ~non-decaying until contradicted |
| **Procedural** | Skills / how-to | "How to run the test suite"; reusable fix recipes | ~90 days |
| **Entity graph** | Schemas / relationships | modules, services, people and their relations | structural |

Episodic memory is captured cheaply and quickly; **consolidation** later distills repeated
episodes into durable semantic facts and procedural playbooks (the CLS two-stage process —
see [Consolidation](CONSOLIDATION.md)). Ten episodes of "had to activate the venv first"
become one semantic rule.

## 3. Coding-native node types

The coding types map onto the cognitive shapes above; each is timestamped, sourced,
confidence-scored, and editable.

| Type | Cognitive shape | Captures | Example |
|---|---|---|---|
| `identity` | semantic | Who the user is | "Senior backend dev; Go + Python; terse answers" |
| `preference` | semantic | How they like things done | "pytest, never unittest" |
| `project` | semantic + entity | A codebase and its shape | "`billing-svc`: FastAPI + Postgres; NATS events" |
| `decision` | semantic | A durable choice + rationale | "Chose Postgres over Mongo — needs ACID; 2026-05" |
| `convention` | procedural | Rules/standards in a context | "All API errors use RFC-7807 problem+json" |
| `snippet` | procedural | Reusable idiom/playbook | "retry-with-jitter helper (Python)" |
| `entity` | entity graph | People/teams/repos/services | "Priya owns `auth-svc`" |
| `episode` | episodic | A specific event | "Build broke on 2026-06-12 due to X" |
| `fact` | semantic | Generic catch-all | "Deploys frozen on Fridays" |

Types are extensible; new domains register additional types without touching the engine.

## 4. Node schema

```jsonc
{
  "id": "mem_billing_db_choice",   // human-readable id (not an opaque UUID) — ADR-023
  "type": "decision",
  "cognitive": "semantic",          // episodic | semantic | procedural | entity
  "content": "Chose Postgres over Mongo for billing — needs ACID transactions.",
  "scope": "project:billing-svc",   // "global" or "project:<id>"
  "attributes": { "alternatives": ["MongoDB"], "rationale": "Strong consistency for money" },

  // --- retrieval signals ---
  "embedding_ref": "vec_memories:mem_billing_db_choice",
  "importance": 0.8,        // [0..1] LLM/heuristic-rated at write time (poignancy)
  "confidence": 0.9,        // [0..1] how sure we are it's true/durable
  "salience": "derived",    // computed at read time: importance·e^(−λ·Δt_last_access) — ADR-014

  // --- bi-temporal (ADR-013) ---
  "valid_from": "2026-05-14T00:00:00Z",
  "valid_to": null,                 // null = currently true; set when superseded
  "recorded_at": "2026-05-14T10:32:00Z",   // transaction-time: when Helix learned it

  // --- lifecycle ---
  "status": "active",       // active | archived | forgotten | superseded
  "last_seen_at": "...",    // reinforcement signal
  "provenance": [ { "agent": "claude-code", "ref": "session:...", "extractor": "llm:gemini-2.0-flash",
                    "origin": "user-asserted" } ]   // origin: user-asserted | agent-ingested — ADR-029
}
```

## 5. Edges (relations)

The graph is what makes recall smart: pulling a `project` should also surface its `decisions`
and `conventions`, and Personalized-PageRank expansion ([Retrieval](RETRIEVAL.md)) walks these
edges.

```jsonc
{ "id": "edge_...", "from_id": "project:billing-svc", "to_id": "mem_billing_db_choice",
  "relation": "has_decision", "weight": 1.0, "provenance": {...}, "created_at": "..." }
```

Common relations: `works_on`, `owns`, `depends_on`, `has_decision`, `has_convention`,
`prefers`, `uses`, `supersedes`, `contradicts`, `related_to`. Edges carry provenance too.

## 6. Scope

- `global` — true about the user everywhere (identity, broad preferences).
- `project:<id>` — true within one codebase (architecture, conventions, decisions).

Recall is scope-aware: an agent in `billing-svc` gets that project's memory plus global facts,
not unrelated projects' — keeping recall relevant and preventing cross-project bleed.

## 7. Lifecycle

```
 candidate ──extract──► [consolidate] ──► ADD ─────► active
   (episodic)                          ├─► UPDATE ──► active (confidence↑, provenance+)
                                       ├─► NOOP ────► (unchanged)
                                       └─► SUPERSEDE► old: valid_to set, status=superseded
                                                       new: active, `supersedes` edge

 active ──(decay: salience falls)──► below floor ──► proposed archival ──► archived
 active ──reflection/consolidation──► distilled into semantic/procedural memory
 active ──user forgets──► forgotten (soft delete, recoverable from history)
```

- **Reinforcement & decay** are computed at read time (`salience = importance·e^(−λ·Δt)`,
  per-type half-life; SM-2-style reinforcement on recall — [ADR-014](../DECISIONS.md), [Consolidation](CONSOLIDATION.md)).
- **Supersession** is bi-temporal and append-only: the old fact's `valid_to` is closed and it
  becomes `superseded`; nothing is hard-deleted, so history, rollback, and merge work.
- **Forget** is a user-initiated soft delete; recoverable via `helix log`/`rollback` until purged.
- **Archival, not deletion:** low-salience memories drop out of default retrieval but stay on
  disk, searchable on demand — guarding against catastrophic forgetting.

## 8. Provenance & integrity (why it believes this)

Every node/edge links to provenance: the source slice, the extractor and model, the
consolidation op, and crucially the **origin** (`user-asserted` vs `agent-ingested`). This
powers the dashboard's "why?" button, GDPR cascade-erasure ([Privacy](PRIVACY_COMPLIANCE.md)),
and the anti-poisoning guardrails ([ADR-029](../DECISIONS.md)): agent-ingested content is
untrusted, injection-scanned before durable write, and consolidated facts must cite ≥1
grounding episode. Contradictions are flagged, never silently overwritten.

## 9. What is NOT stored

- **Raw transcripts.** Helix stores distilled facts, not chat logs (privacy + size).
- **Secrets.** Tiered redaction removes keys/tokens/.env values *before* storage and *before*
  any LLM call ([Privacy & Compliance](PRIVACY_COMPLIANCE.md), [ADR-025](../DECISIONS.md)).
- **Anything not routed.** No ambient capture; the user chooses what Helix sees.

## 10. Example mini-graph

```
 (identity: "prefers terse, typed Python")
        │ prefers
        ▼
 (preference: "pytest over unittest") ──related_to──► (convention: "100% type hints in core")
                                                              ▲ has_convention
 (project: billing-svc) ──has_decision──► (decision: "Postgres over Mongo" · valid 2026-05→now)
        │ depends_on                         │ decided_by
        ▼                                    ▼
 (entity: auth-svc)                    (entity: "Priya")
```

A query like *"how do we handle the billing DB?"* hits the decision via hybrid search, then
graph-expands (PPR) to the project, its conventions, and the owning entity — exactly the
context a coding agent needs, surfaced without the user re-explaining anything, and aware of
*when* each fact became true.
