# Helix — Technical Specification Document (TSD)

**Status:** Draft v1 · **Last updated:** 2026-06-18
**Related:** [PRD](PRD.md) · [System Architecture](SYSTEM_ARCHITECTURE.md) · [Memory Model](MEMORY_MODEL.md) · [DNA Format](DNA_FORMAT.md) · [Cost](COST_OPTIMIZATION.md) · [Security](SECURITY_MODEL.md) · [Decisions](../DECISIONS.md)

This document is the engineering contract: components, data model, algorithms, interfaces,
and the technology behind each. Where a choice is made, it links to the relevant ADR.

---

## 1. System overview

Helix is a pipeline wrapped around an embedded store, fronted by MCP:

```
 ingest ──> redact ──> heuristic gate ──> extract ──> embed ──> consolidate ──> store
                                                                                   │
 agent (MCP) ──> recall(query) ──> hybrid retrieve (vector + graph) ──> rank ──> inject
                                                                                   │
                                            export/import/merge  <──>  .dna strand
```

Everything runs in a single local process by default (the **Helix daemon**), with the CLI,
MCP server, and dashboard as clients/front-ends. No network is required for any core path
([ADR-001](../DECISIONS.md)).

---

## 2. Technology choices (summary)

| Concern | Choice | ADR |
|---|---|---|
| Core language | Python 3.11+, `uv` | [ADR-004](../DECISIONS.md) |
| Interface | MCP server | [ADR-003](../DECISIONS.md) |
| Vector store | `sqlite-vec` (embedded) | [ADR-005](../DECISIONS.md) |
| Graph store | SQLite tables + NetworkX projections | [ADR-005](../DECISIONS.md) |
| Embeddings | local `fastembed` bge-small (default); cloud optional | [ADR-006](../DECISIONS.md) |
| LLM router | LiteLLM; Gemini 2.0 Flash → gpt-4o-mini; optional | [ADR-007](../DECISIONS.md) |
| Portable format | signed+encrypted SQLite bundle `.dna` | [ADR-008](../DECISIONS.md) |
| Crypto | PyNaCl/libsodium: XChaCha20-Poly1305 + Ed25519 + Argon2id | [ADR-008](../DECISIONS.md) |
| Dashboard | React + Vite + Tailwind (TS) | [ADR-004](../DECISIONS.md) |
| Optional sync API | FastAPI | [ADR-010](../DECISIONS.md) |

---

## 3. Components

### 3.1 `helix-core` — the engine
The library everything else depends on. Subsystems:

- **Ingestion** — accepts routed slices (conversation turns, code, notes) with metadata
  (agent, project, timestamp). Never auto-captures.
- **Redaction** — scrubs secrets (API keys, tokens, private keys, .env values) via regex +
  entropy heuristics **before** anything is stored or sent to a model.
- **Heuristic gate** — decides whether a slice is even worth extracting from (most aren't).
  See §6.1. This is the primary cost lever.
- **Extractor** — turns a slice into candidate typed facts. Two engines behind one
  interface: deterministic (rules+embeddings) and LLM-backed.
- **Embedder** — turns text into vectors. Local default; pluggable.
- **Consolidator** — diffs candidate facts against existing memory and emits
  ADD/UPDATE/DELETE/NOOP operations (§6.3).
- **Conflict resolver** — detects contradictions, resolves via recency/confidence/provenance
  with optional LLM tie-break; never silently destroys data.
- **Stores** — `VectorStore`, `GraphStore`, `BlobStore` behind interfaces (§5).
- **Retriever** — hybrid vector+graph recall with ranking (§6.4).
- **Strand codec** — read/write/sign/encrypt/verify `.dna`; diff/merge/rollback (§7).
- **Scheduler** — background decay, re-embed on model change, compaction.

### 3.2 `helix-mcp` — MCP server
Exposes a small, stable tool/resource surface to agents (§4). Translates MCP calls into
core operations. Stateless over the core; one per machine.

### 3.3 `helix-cli` — the `helix` command
Operator surface: `init`, `connect`, `status/doctor`, `add/edit/forget`, `search`,
`export/import/merge`, `log/diff/rollback`, `config`. Thin wrapper over core.

### 3.4 `helix-sdk-python` / `sdks/typescript`
Programmatic access to the same core operations for custom agents and automation.

### 3.5 `apps/dashboard`
Local React app talking to the daemon over a localhost HTTP/WebSocket API. Browse/search the
graph, edit/confirm/forget, view history, see cost & telemetry, manage strands/keys.

---

## 4. MCP interface (the contract)

Full reference: [MCP Integration](MCP_INTEGRATION.md). Tools (names are stable, versioned):

| Tool | Input | Output | Notes |
|---|---|---|---|
| `memory.search` | `query`, `scope?`, `k?`, `types?` | ranked memories w/ source & confidence | the hot path; p95 < 150 ms |
| `memory.write` | `content`, `type?`, `scope?`, `source` | created/updated memory ids | runs redact→extract→consolidate |
| `memory.note` | `text` | ack | low-friction "remember this" |
| `memory.forget` | `id` or `query` | removed ids | soft-delete + history |
| `memory.list` | `scope?`, `type?`, `limit?` | memories | for inspection |
| `memory.relate` | `from_id`, `to_id`, `relation` | edge id | graph linking |
| `memory.context` | `scope?`, `budget_tokens?` | a packed context block | one-call "give me what matters" |

Resources: `helix://graph` (read-only graph view), `helix://strand/manifest` (metadata).
The surface is intentionally tiny; growth requires an ADR ([ADR-003](../DECISIONS.md)).

**Token discipline.** `memory.context` and `memory.search` accept a `budget_tokens` and pack
results greedily by rank under that budget, so agents never blow their context window.

---

## 5. Data model & storage

### 5.1 Logical model
See [Memory Model](MEMORY_MODEL.md) for the full schema. Core entities:

**Memory (node)**
```
id            : UUIDv7 (time-sortable)
type          : identity | preference | project | decision | entity | snippet | fact
content       : str                 # the distilled, human-readable fact
embedding     : float32[dim]        # dim recorded per strand
scope         : "global" | project_id
source        : {agent, ref, ingested_at}
confidence    : float [0..1]
salience      : float [0..1]        # decays over time unless reinforced
created_at    : ts
updated_at    : ts
last_seen_at  : ts                  # reinforcement signal
status        : active | archived | forgotten   # forget = soft delete
attributes    : JSON                # type-specific fields
```

**Edge (relation)**
```
id, from_id, to_id, relation (str), weight, created_at, source
```
Relations e.g. `works_on`, `depends_on`, `decided_by`, `prefers`, `contradicts`,
`supersedes`.

**Provenance** — every node/edge records what produced it (which slice, which extractor,
which model) so the user can always answer "why does it think this?"

### 5.2 Physical model — one SQLite file per strand ([ADR-005](../DECISIONS.md))
Tables: `memories`, `edges`, `provenance`, `history` (op log), `meta` (schema/embedding
info). Vectors live in a `sqlite-vec` virtual table `vec_memories(id, embedding)`. Graph
algorithms (neighbors, subgraph, centrality) run on a **NetworkX** projection built lazily
from `edges` and cached.

The strand DB is self-describing: `meta` records schema version, embedding provider+model+dim,
and counts, so any Helix install can open any strand or refuse cleanly.

### 5.3 Store interfaces
```python
class VectorStore(Protocol):
    def upsert(self, id: str, embedding: list[float], payload: dict) -> None: ...
    def query(self, embedding: list[float], k: int, filters: dict | None = None) -> list[Hit]: ...
    def delete(self, id: str) -> None: ...

class GraphStore(Protocol):
    def add_node(self, node: Memory) -> None: ...
    def add_edge(self, edge: Edge) -> None: ...
    def neighbors(self, id: str, depth: int = 1) -> list[Memory]: ...
    def subgraph(self, ids: list[str]) -> Graph: ...
```
Interfaces let us swap in Postgres+pgvector or a decentralized backend later
([ADR-010](../DECISIONS.md)) without touching callers.

---

## 6. Core algorithms

### 6.1 Heuristic gate (the cost lever — [Cost](COST_OPTIMIZATION.md))
Before any model is invoked, a cheap local classifier decides "is there a durable fact
here?" Signals: imperative memory cues ("remember", "always", "I prefer", "we decided"),
presence of entities/decisions, novelty vs. existing memory (embedding distance to nearest
neighbor), and slice length/type. If the gate's score < `HEURISTIC_CONFIDENCE_CUTOFF` for
"no fact," the slice is dropped with **zero** model calls. Empirically most turns are
dropped here, which is what keeps default cost at $0.

### 6.2 Extraction
Two interchangeable extractors behind `Extractor`:

- **Deterministic** (default, no key): rule/template matching + embedding clustering +
  entity extraction. Lower recall, fully local, $0. Always available as the floor.
- **LLM-backed** (if a key/Ollama present): a single structured-output prompt returns a list
  of typed candidate facts (JSON schema-constrained to minimize tokens). Batched across
  buffered turns rather than per-message.

Output of either: `list[CandidateFact]` with `type`, `content`, `attributes`, `confidence`.

### 6.3 Consolidation (ADD / UPDATE / DELETE / NOOP)
For each candidate, find the top-k semantically nearest existing memories. Then decide:

- **NOOP** — an equivalent memory already exists (cosine ≥ τ_dup and same type/scope).
- **UPDATE** — same subject, complementary/refined info → merge into existing, bump
  `confidence`, append provenance.
- **DELETE/SUPERSEDE** — candidate contradicts an existing memory → mark old `superseded`,
  add new, link with `supersedes`/`contradicts` edges (never hard-delete; keep history).
- **ADD** — novel → insert new node, embed, link to related entities.

The decision uses thresholds by default; when an LLM is available and the case is ambiguous
(distance in a gray band), one cheap call adjudicates. Idempotent and transactional.

### 6.4 Retrieval & ranking (recall)
Hybrid:
1. **Vector** — embed the query, ANN search in `sqlite-vec` for top-N candidates (filtered
   by scope/type).
2. **Graph expansion** — pull 1–2 hop neighbors of strong hits (e.g., a `project` node pulls
   its `decisions` and `conventions`).
3. **Rank** — score = `α·similarity + β·salience + γ·recency + δ·confidence + ε·graph_proximity`.
   Down-rank `archived`; exclude `forgotten`.
4. **Pack** — greedily fill `budget_tokens` by score; dedupe near-identical content.

Weights are configurable; defaults tuned for "surface stable, high-confidence, on-topic
facts first." p95 < 150 ms on a 10⁵-node strand (NFR-1).

### 6.5 Decay & reinforcement
`salience` decays on a slow half-life unless a memory is `last_seen`/recalled/confirmed,
which reinforces it. Stale, never-reinforced, low-confidence memories sink in ranking and
are eventually proposed for archival (never auto-deleted). Keeps recall sharp as memory grows.

### 6.6 Conflict resolution
Contradictions (detected during consolidation or by a periodic sweep) are resolved by:
recency > confidence > provenance authority, with the loser `superseded` (reversible). If
within a tie band and an LLM is available, one adjudication call decides and records its
reason in provenance. The user can always override in the dashboard.

---

## 7. The `.dna` strand (portable format)

Full spec: [DNA Format](DNA_FORMAT.md). Engineering summary:

- **Container:** a tar/zip with `strand.db` (the SQLite file), `manifest.json`, and
  `manifest.sig`.
- **Manifest:** schema version, embedding provider/model/dim, node/edge counts, created/by,
  and a content hash (Merkle root over row hashes) for integrity & cheap diffing.
- **Encryption:** `strand.db` encrypted with XChaCha20-Poly1305; key derived via Argon2id
  from the user passphrase, or wrapped by a device-keychain key.
- **Signature:** `manifest.sig` is an Ed25519 signature over the manifest; verified on import
  before any content is trusted.
- **Versioning:** each strand has a monotonically increasing version and an op-`history` log;
  combined with content hashes this enables `log`, `diff`, and `rollback`.

### 7.1 Transfer operations
- **export/clone** — package current strand → `.dna`.
- **import** — verify signature → decrypt → check schema/embedding compat (re-embed if the
  importing install uses a different embedding space) → open.
- **merge** — three-way merge of two strands: union nodes/edges, run consolidation across the
  combined set, resolve conflicts (§6.6), preserving both provenances. Always produces a new
  version (reversible). Secrets are never merged (redaction invariant holds across import).
- **rollback** — restore a prior version from history.

Merge is the hard part; it reuses consolidation + conflict resolution so there's one code
path for "two facts meet," whether from one user over time or two users at once.

---

## 8. Cost optimization (engineering view)

Detailed rationale in [Cost Optimization](COST_OPTIMIZATION.md). Mechanisms:

1. **Heuristic gate** (§6.1) — skip the LLM for most slices. Biggest lever.
2. **Local embeddings by default** ([ADR-006](../DECISIONS.md)) — the high-volume call is free.
3. **Free-tier-first router** ([ADR-007](../DECISIONS.md)) — Gemini 2.0 Flash free tier before
   any paid model; `gpt-4o-mini` only as fallback.
4. **Response cache** — hash(prompt+inputs) → result; identical extraction/consolidation work
   is never paid for twice.
5. **Batching** — buffer turns and extract in one call instead of per-message.
6. **Structured JSON output + compact prompts** — minimize tokens per call.
7. **Token budget guardrail** — `HELIX_MONTHLY_TOKEN_BUDGET`; `0` hard-disables paid calls.
8. **No-LLM mode is first-class** — deterministic extractor keeps the product useful at $0
   with no key at all.

Target: ≥ 90% of active users incur **$0** of API spend (PRD §9).

---

## 9. Configuration & secrets

- Config precedence: CLI flags → `.env`/env vars → `~/.helix/config.toml` → defaults.
- Secrets (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `HELIX_PASSPHRASE`) come from the environment
  only; never logged, never written into a strand, never sent anywhere except the chosen LLM
  provider. See [`.env.example`](../.env.example).

---

## 10. Observability

- Structured local logs (redacted) with levels; no content leaves the machine.
- Local metrics: recall latency, gate drop-rate, LLM calls/tokens/cost, store sizes,
  consolidation op mix. Surfaced in the dashboard.
- Telemetry is **off by default**; if enabled, it is local-only unless the user explicitly
  shares aggregates ([Security](SECURITY_MODEL.md)).

---

## 11. Testing strategy

- **Unit** — extractors, consolidation decisions, ranking, codec round-trips, crypto.
- **Golden** — fixed slices → expected fact sets (both extractor engines), so the $0 path is
  regression-protected.
- **Property** — strand encode→decode→verify is lossless; merge is commutative/associative
  where it should be; no operation corrupts a strand.
- **Integration** — MCP server against a mock agent; `connect` writes valid configs per agent.
- **Performance** — recall p95 on synthetic 10⁵–10⁶-node strands.
- **Security** — redaction never leaks secrets into a strand; tampered manifests are rejected.

CI runs the full matrix; the no-key/offline path is tested as a first-class configuration.

---

## 12. Failure & safety

- All strand mutations are transactional; a crash mid-write never yields a partial strand
  (write-temp-then-atomic-rename + SQLite WAL).
- LLM/network failures degrade to the deterministic path, never to data loss.
- Import of an incompatible/tampered strand fails closed with a clear error.
- `forget` is a soft-delete with history; true purge is an explicit, confirmed operation.

---

## 13. Versioning & compatibility

- **Strand schema version** in `meta`; the codec migrates forward and refuses unknown-newer
  strands with guidance.
- **MCP surface** is semver'd; agents negotiate the protocol version.
- **Embedding space** is pinned per strand; changing providers triggers a tracked re-embed,
  never a silent mismatch.

---

## 14. Open technical questions

- Best local-only extractor quality bar before recommending Ollama auto-enable.
- Merge conflict surface in the dashboard (auto vs. prompt) — UX + data-safety tradeoff.
- Graph store: keep NetworkX projection, or adopt embedded Kuzu when strands get large?
- Re-embedding cost/UX when a user switches embedding providers on a big strand.

Tracked alongside [PRD §12](PRD.md) and resolved via [`DECISIONS.md`](../DECISIONS.md).
