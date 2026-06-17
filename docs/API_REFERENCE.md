# Helix — API Reference (MCP · Daemon · SDK)
**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD](TSD.md) · [MCP Integration](MCP_INTEGRATION.md) · [Decisions](../DECISIONS.md)

Helix is a local-first, coding-agent-first, portable, `$0`-by-default AI memory layer. It exposes memory to agents over the **Model Context Protocol (MCP)**, ships a CLI and Python/TS SDKs, and runs as a single local daemon. This document is the canonical reference for the **MCP tool surface**, the **local Daemon REST API**, and the **SDKs**.

> Design authority: **ADR-023** (MCP architecture — daemon + stdio shim, ~5 tools, token budget) and **ADR-024** (security posture). See [Decisions](../DECISIONS.md).

---

## 1. Architecture

Helix runs **one local daemon** and exposes it to agents through **two MCP transports** plus a REST surface. The daemon owns the **single source of truth**: one embedded store, one cache, one consolidation worker — shared safely across all concurrent agents.

```
            ┌─────────────────────────────────────────────────────────┐
            │                    Agents / Clients                     │
            │  Claude Code   Cursor   Windsurf   VS Code   Gemini CLI │
            └───────┬─────────────┬──────────────────────┬────────────┘
                    │ stdio        │ stdio                 │ Streamable HTTP
                    ▼              ▼                       ▼
            ┌───────────────┐ ┌───────────────┐   (direct, multi-client)
            │ helix-mcp     │ │ helix-mcp     │           │
            │ stdio shim    │ │ stdio shim    │           │
            └──────┬────────┘ └──────┬────────┘           │
                   │ proxy (HTTP)    │ proxy (HTTP)        │
                   ▼                 ▼                     ▼
            ┌─────────────────────────────────────────────────────────┐
            │   helixd  —  local daemon  (127.0.0.1:7878)             │
            │   • Streamable HTTP MCP endpoint  (multi-client)        │
            │   • REST API (/remember /recall /forget /graph ...)     │
            │   • Origin validation (DNS-rebinding defense)           │
            ├─────────────────────────────────────────────────────────┤
            │   ONE store · ONE cache · ONE consolidation worker      │
            │   SQLite/Lance/pgvector/Qdrant  +  embedding cache       │
            └─────────────────────────────────────────────────────────┘
```

### Why one daemon

- **Shared state, no contention.** Streamable HTTP can serve **multiple clients** from one process, so every agent reads/writes the *same* memory and shares the embedding cache and consolidation results. Running an MCP server per-agent would fork state and re-embed redundantly. (https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- **stdio for portability.** Many coding agents only speak **stdio** today (and the spec says clients **SHOULD** support stdio). Helix ships a thin **stdio shim** (`helix-mcp`) that does nothing but proxy framed JSON-RPC to the daemon's HTTP endpoint. The shim holds no state.
- **SSE is gone.** The standalone HTTP+SSE transport was **deprecated 2025-03-26**; Helix implements only **stdio + Streamable HTTP**.

### Transport security (local)

The daemon binds **`127.0.0.1` only** and **validates the `Origin` header** on every Streamable HTTP request to defend against DNS-rebinding attacks (a browser tricked into POSTing to `localhost`). Requests with an unexpected/absent `Origin` are rejected. See ADR-024 and [Security Model](SECURITY_MODEL.md).

---

## 2. MCP Tool Surface

Helix exposes a **deliberately small** tool set. Anthropic's guidance is explicit: too many tools distract the model and bloat context; existing memory servers either ship 4 flat tools (OpenMemory) or 9 graph tools (reference KG server) and **none expose a token budget** — the gap Helix fills. (https://www.anthropic.com/engineering/writing-tools-for-agents, https://mem0.ai/blog/introducing-openmemory-mcp, https://github.com/modelcontextprotocol/servers/blob/main/src/memory/README.md)

| Tool | Purpose | Mutating | Key budget controls |
|------|---------|----------|---------------------|
| `memory.search` | Semantic + keyword recall | No | `response_format`, `limit`, `max_tokens` |
| `memory.context` | Assemble a token-budgeted context pack for a task | No | `response_format`, `max_tokens` |
| `memory.write` (alias `memory.add`) | Persist a memory (dedup/supersede, idempotent) | Yes | `idempotency_key` |
| `memory.get` | Fetch one memory by human-readable ID | No | `response_format` |
| `memory.forget` | Delete / tombstone a memory | Yes | `idempotency_key` |
| `memory.relate` *(optional)* | Create a typed edge between memories | Yes | `idempotency_key` |

**Cross-cutting conventions**

- **Human-readable IDs**, not UUIDs: `mem_2026-06-18_auth-retry-policy_a1b2`. Easier for the model to reference, dedupe, and cite. (Anthropic tool-design guidance.)
- **`response_format: concise | detailed`** on every read tool. `concise` returns the minimum to act on (think *72 tokens*); `detailed` returns provenance, scores, and edges (think *206 tokens*). Concise is the default.
- **`max_tokens` / `limit`** truncate and paginate. Claude Code caps a single tool response at **~25,000 tokens**; Helix never emits more than the caller's `max_tokens` and defaults well under the cap.
- **Errors**: *business/tool* errors (not found, budget exceeded, validation) are returned as a **successful JSON-RPC result with `isError: true`** so the model can see and recover from them; only *protocol* failures (malformed request, transport) become **JSON-RPC errors**. (https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- **`tools/list_changed`**: tool **names are stable**; capability changes are announced via the `tools/list_changed` notification rather than renaming.

### 2.1 `memory.search`

Semantic + lexical recall over the store, re-ranked, gated, and token-budgeted.

**Input**

```json
{
  "type": "object",
  "required": ["query"],
  "properties": {
    "query":          { "type": "string", "description": "Natural-language or keyword query" },
    "scope":          { "type": "string", "enum": ["project", "global", "session"], "default": "project" },
    "filters":        { "type": "object", "additionalProperties": { "type": "string" } },
    "limit":          { "type": "integer", "minimum": 1, "maximum": 50, "default": 8 },
    "max_tokens":     { "type": "integer", "minimum": 64, "maximum": 25000, "default": 1500 },
    "response_format":{ "type": "string", "enum": ["concise", "detailed"], "default": "concise" }
  }
}
```

**Output**

```json
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id":       { "type": "string", "example": "mem_2026-06-12_db-pool_7c4e" },
          "text":     { "type": "string" },
          "score":    { "type": "number" },
          "source":   { "type": "string", "description": "detailed only" },
          "created":  { "type": "string", "format": "date-time", "description": "detailed only" }
        }
      }
    },
    "truncated":     { "type": "boolean" },
    "tokens_used":   { "type": "integer" },
    "next_cursor":   { "type": "string", "nullable": true }
  }
}
```

### 2.2 `memory.context`

Assembles a **ready-to-inject context pack** for the current task — the recall results already gated, deduped, ordered, and packed to fit a budget. This is the tool agents call most.

**Input**

```json
{
  "type": "object",
  "required": ["task"],
  "properties": {
    "task":           { "type": "string", "description": "What the agent is about to do" },
    "scope":          { "type": "string", "enum": ["project", "global", "session"], "default": "project" },
    "max_tokens":     { "type": "integer", "minimum": 128, "maximum": 25000, "default": 4000 },
    "response_format":{ "type": "string", "enum": ["concise", "detailed"], "default": "concise" }
  }
}
```

**Output**

```json
{
  "type": "object",
  "properties": {
    "context":      { "type": "string", "description": "Packed memory text, budget-fit" },
    "citations":    { "type": "array", "items": { "type": "string" }, "description": "Memory IDs used" },
    "tokens_used":  { "type": "integer" },
    "dropped":      { "type": "integer", "description": "Memories gated/dropped to fit budget" }
  }
}
```

### 2.3 `memory.write` (alias `memory.add`)

Persists a memory. **Idempotent** (via `idempotency_key`) and **dedup/supersede-aware**: a write whose content is near-duplicate of an existing memory is merged; a write the extractor judges to *supersede* a prior memory tombstones the old one and links `supersedes →`.

**Input**

```json
{
  "type": "object",
  "required": ["text"],
  "properties": {
    "text":            { "type": "string" },
    "kind":            { "type": "string", "enum": ["fact", "preference", "decision", "snippet", "task"], "default": "fact" },
    "scope":           { "type": "string", "enum": ["project", "global", "session"], "default": "project" },
    "tags":            { "type": "array", "items": { "type": "string" } },
    "idempotency_key": { "type": "string", "description": "Retries with same key are no-ops" },
    "supersede_hint":  { "type": "string", "description": "Optional ID this write replaces" }
  }
}
```

**Output**

```json
{
  "type": "object",
  "properties": {
    "id":         { "type": "string", "example": "mem_2026-06-18_auth-retry_a1b2" },
    "status":     { "type": "string", "enum": ["created", "merged", "superseded", "noop"] },
    "supersedes": { "type": "array", "items": { "type": "string" } }
  }
}
```

> **Dedup/supersede semantics.** `created` = novel. `merged` = folded into an existing near-duplicate (returns that ID). `superseded` = replaced one or more prior memories (returned in `supersedes`). `noop` = idempotency key already seen.

### 2.4 `memory.get`

**Input**

```json
{
  "type": "object",
  "required": ["id"],
  "properties": {
    "id":             { "type": "string" },
    "response_format":{ "type": "string", "enum": ["concise", "detailed"], "default": "detailed" }
  }
}
```

**Output (`detailed`)**

```json
{
  "type": "object",
  "properties": {
    "id":        { "type": "string" },
    "text":      { "type": "string" },
    "kind":      { "type": "string" },
    "scope":     { "type": "string" },
    "tags":      { "type": "array", "items": { "type": "string" } },
    "edges":     { "type": "array", "items": { "type": "object",
                    "properties": { "rel": {"type":"string"}, "to": {"type":"string"} } } },
    "created":   { "type": "string", "format": "date-time" },
    "updated":   { "type": "string", "format": "date-time" }
  }
}
```

A miss returns a **successful result with `isError: true`** and a message, not a JSON-RPC error.

### 2.5 `memory.forget`

**Input**

```json
{
  "type": "object",
  "required": ["id"],
  "properties": {
    "id":              { "type": "string" },
    "mode":            { "type": "string", "enum": ["tombstone", "hard"], "default": "tombstone" },
    "idempotency_key": { "type": "string" }
  }
}
```

**Output**

```json
{ "type": "object", "properties": {
    "id":     { "type": "string" },
    "status": { "type": "string", "enum": ["forgotten", "noop"] } } }
```

### 2.6 `memory.relate` *(optional)*

Creates a typed edge in the memory graph.

**Input**

```json
{
  "type": "object",
  "required": ["from", "to", "rel"],
  "properties": {
    "from":            { "type": "string" },
    "to":              { "type": "string" },
    "rel":             { "type": "string", "enum": ["supersedes", "depends_on", "contradicts", "refines", "relates_to"] },
    "idempotency_key": { "type": "string" }
  }
}
```

**Output**

```json
{ "type": "object", "properties": {
    "edge_id": { "type": "string" },
    "status":  { "type": "string", "enum": ["created", "noop"] } } }
```

---

## 3. MCP Resources

Helix exposes read-only **MCP Resources** for clients that browse rather than call tools:

| URI | Description | MIME |
|-----|-------------|------|
| `helix://graph` | The memory graph (nodes + typed edges) for the active scope | `application/json` |
| `helix://strand/manifest` | The "strand" manifest — the portable export descriptor (memories, embeddings provider, schema version) used for backup/transfer | `application/json` |

Resources are budget-aware: large graphs paginate via `?cursor=`.

---

## 4. Local Daemon REST API

The daemon mirrors the MCP surface over plain HTTP for the CLI, SDKs, and non-MCP integrations. Same store, same gate, same budgeting.

| Method & Path | Mirrors | Notes |
|---------------|---------|-------|
| `POST /remember` | `memory.write` | Body = write input; honors `Idempotency-Key` header |
| `GET  /recall?q=&limit=&max_tokens=&format=` | `memory.search` | |
| `POST /context` | `memory.context` | |
| `GET  /memory/{id}?format=` | `memory.get` | |
| `POST /forget` | `memory.forget` | |
| `GET  /graph?scope=&cursor=` | `helix://graph` | |
| `GET  /healthz` | — | Liveness/readiness; no auth |
| `GET  /metrics` | — | Local Prometheus-style metrics (see [Observability](OBSERVABILITY.md)) |

**Example**

```bash
curl -s 127.0.0.1:7878/recall \
  --get --data-urlencode "q=retry policy for the auth client" \
  --data "limit=5&format=concise&max_tokens=1200"
```

```bash
curl -s 127.0.0.1:7878/remember \
  -H "Idempotency-Key: write-2026-06-18-001" \
  -H "Content-Type: application/json" \
  -d '{"text":"Auth client retries 3x with jitter","kind":"decision","scope":"project"}'
```

All `GET`/`POST` requests are subject to the same **`Origin` validation** as the MCP HTTP endpoint.

---

## 5. SDKs

### 5.1 Python SDK

```python
from helix import Helix

mem = Helix()  # connects to local daemon at 127.0.0.1:7878 (or HELIX_URL)

mem.write("Auth client retries 3x with jitter", kind="decision",
          idempotency_key="write-001")

hits = mem.search("retry policy", limit=5,
                  response_format="concise", max_tokens=1200)

pack = mem.context("debug the auth retry storm", max_tokens=4000)
print(pack.context, pack.citations)

m = mem.get("mem_2026-06-18_auth-retry_a1b2", response_format="detailed")
mem.forget(m.id, mode="tombstone")
mem.relate(m.id, "mem_..._b3", rel="supersedes")
```

Selected signatures:

```python
class Helix:
    def __init__(self, url: str | None = None, *, scope: str = "project") -> None: ...
    def search(self, query: str, *, limit: int = 8, max_tokens: int = 1500,
               response_format: Literal["concise","detailed"] = "concise",
               scope: str | None = None, filters: dict | None = None) -> SearchResult: ...
    def context(self, task: str, *, max_tokens: int = 4000,
                response_format: Literal["concise","detailed"] = "concise") -> ContextPack: ...
    def write(self, text: str, *, kind: str = "fact", scope: str | None = None,
              tags: list[str] | None = None, idempotency_key: str | None = None,
              supersede_hint: str | None = None) -> WriteResult: ...
    def get(self, id: str, *, response_format: str = "detailed") -> Memory: ...
    def forget(self, id: str, *, mode: Literal["tombstone","hard"] = "tombstone") -> ForgetResult: ...
    def relate(self, frm: str, to: str, *, rel: str) -> RelateResult: ...
```

### 5.2 TypeScript SDK

```ts
import { Helix } from "@helix/sdk";

const mem = new Helix();                       // HELIX_URL or 127.0.0.1:7878

await mem.write("Auth client retries 3x with jitter",
  { kind: "decision", idempotencyKey: "write-001" });

const hits = await mem.search("retry policy",
  { limit: 5, responseFormat: "concise", maxTokens: 1200 });

const pack = await mem.context("debug the auth retry storm", { maxTokens: 4000 });
```

```ts
class Helix {
  constructor(opts?: { url?: string; scope?: "project" | "global" | "session" });
  search(query: string, opts?: SearchOpts): Promise<SearchResult>;
  context(task: string, opts?: ContextOpts): Promise<ContextPack>;
  write(text: string, opts?: WriteOpts): Promise<WriteResult>;
  get(id: string, opts?: { responseFormat?: "concise" | "detailed" }): Promise<Memory>;
  forget(id: string, opts?: { mode?: "tombstone" | "hard" }): Promise<ForgetResult>;
  relate(from: string, to: string, opts: { rel: EdgeRel }): Promise<RelateResult>;
}
```

---

## 6. Authentication & Authorization

Helix's posture is **local = trivial, remote = strict** (ADR-024, [Security Model](SECURITY_MODEL.md)).

| Mode | Transport | Auth |
|------|-----------|------|
| **Local (default)** | stdio shim / `127.0.0.1` HTTP | **Env credentials, no OAuth.** The MCP authorization spec explicitly scopes OAuth to *remote* servers; local stdio servers retrieve credentials from the environment. (https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) |
| **Remote (optional)** | Streamable HTTP over the network | **OAuth 2.1 + PKCE**, **RFC 8707 resource indicators** with **audience validation**; **token passthrough is forbidden** — Helix never forwards a client's token to an upstream API. |

Local mode never opens a browser, never runs an OAuth dance, and never listens off-loopback. Remote mode (self-hosted team daemon) is opt-in and binds an authorization server per the MCP spec.

---

## 7. Versioning & Token-Budget Discipline

- **Stable tool names.** `memory.search` etc. never get renamed; behavior changes are additive and signaled with `tools/list_changed`. (https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- **Token budget is a first-class contract.** Every read tool takes `max_tokens` and returns `tokens_used` + `truncated`. Helix targets responses well under Claude Code's **~25,000-token** tool-output cap, and `response_format: concise` is the default precisely to stay cheap. (https://www.anthropic.com/engineering/writing-tools-for-agents)
- **Pagination over truncation-blindness.** Reads return `next_cursor` so the model can page deliberately instead of silently losing data.

---

## Sources

- MCP Transports (stdio + Streamable HTTP; SSE deprecated; multi-client; Origin validation) — https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Authorization (OAuth 2.1 + PKCE, RFC 8707, no passthrough; local = env creds) — https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- MCP Server Tools (isError-in-result vs JSON-RPC error; tools/list_changed) — https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- Writing tools for agents (token budget ~25k, response_format, human IDs, fewer tools) — https://www.anthropic.com/engineering/writing-tools-for-agents
- OpenMemory MCP (4-tool baseline) — https://mem0.ai/blog/introducing-openmemory-mcp
- Reference KG memory server (9 tools) — https://github.com/modelcontextprotocol/servers/blob/main/src/memory/README.md

**See also:** [TSD](TSD.md) · [MCP Integration](MCP_INTEGRATION.md) · [Plugins](PLUGINS.md) · [Observability](OBSERVABILITY.md) · [Security Model](SECURITY_MODEL.md) · [Decisions](../DECISIONS.md)
