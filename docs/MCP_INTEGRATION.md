# Helix — MCP Integration

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD §4](TSD.md) · [ADR-003](../DECISIONS.md)

The Model Context Protocol (MCP) is Helix's primary interface — the one integration that lets
*every* compatible agent (Claude Code, Cursor, Copilot, Windsurf, ChatGPT desktop, …) read and
write the same memory. The surface is intentionally small, stable, and versioned.

---

## 1. Server

`helix-mcp` runs locally and speaks MCP over stdio (and optionally a local socket). It is a
thin front-end over `helix-core`; it holds no business logic of its own. One server per
machine serves all connected agents against the user's active strand.

## 2. Tools

| Tool | Purpose | Key inputs | Output |
|---|---|---|---|
| `memory.search` | Semantic + graph recall (hot path) | `query`, `scope?`, `k?`, `types?`, `budget_tokens?` | ranked memories w/ source, confidence |
| `memory.context` | One-call "give me what matters here" | `scope?`, `budget_tokens?` | packed context block under budget |
| `memory.write` | Learn from a routed slice | `content`, `type?`, `scope?`, `source` | created/updated ids |
| `memory.note` | Low-friction "remember this" | `text`, `scope?` | ack + id |
| `memory.forget` | Soft-delete a fact | `id` \| `query` | removed ids |
| `memory.list` | Inspect stored memories | `scope?`, `type?`, `limit?` | memories |
| `memory.relate` | Link two memories | `from_id`, `to_id`, `relation` | edge id |

Design rules:
- **Token-budgeted:** recall tools accept `budget_tokens` and pack greedily by rank so an
  agent never overflows its context window.
- **Scope-aware:** pass `scope` (e.g. `project:billing-svc`) to keep recall relevant.
- **Provenance in results:** every returned memory carries `source` + `confidence` so the
  agent (and user) can judge trust.
- **Async writes:** `write`/`note` return fast; extraction/consolidation happen in the
  background (never block the agent — NFR-2).

## 3. Resources

| Resource | Description |
|---|---|
| `helix://graph` | Read-only view of the memory graph (for inspection/visualization) |
| `helix://strand/manifest` | Current strand metadata (schema, embedding space, counts, version) |

## 4. Connecting agents

`helix connect <agent>` writes the correct MCP config for each tool. Examples (illustrative):

**Claude Code** (`.mcp.json` / settings):
```jsonc
{
  "mcpServers": {
    "helix": { "command": "helix-mcp", "args": ["serve", "--stdio"] }
  }
}
```

**Cursor / Windsurf** — analogous MCP server entry pointing at `helix-mcp serve --stdio`.

`helix connect` detects the tool, finds its config location cross-platform, and adds the
entry idempotently. `helix doctor` verifies the connection end-to-end.

## 5. A typical session

```
agent startup
   └─ memory.context(scope="project:billing-svc", budget_tokens=1500)
        → injects: identity + project architecture + key decisions + conventions

user: "why did we pick Postgres here again?"
   └─ memory.search(query="why Postgres billing", scope="project:billing-svc", k=5)
        → returns the decision node + rationale + provenance

user: "from now on we use RFC-7807 for all API errors"
   └─ memory.note(text="All API errors use RFC-7807 problem+json", scope="project:billing-svc")
        → stored as a convention (async); recalled by every agent next time
```

The same memory now lights up in Cursor, Copilot, or ChatGPT — because they all read the same
local Helix strand over MCP.

## 6. Versioning & stability

- The tool/resource surface is **semver'd**; agents negotiate the MCP protocol version.
- **Growing the surface requires an ADR** ([ADR-003](../DECISIONS.md)) and an update to this
  doc — keeping it small is a feature, not a limitation.
- Non-MCP agents are reached via the SDK or via `export`/`import` as a fallback.

## 7. Security notes

- The MCP server only exposes the operations above — agents cannot reach store internals,
  keys, or raw provenance blobs beyond what a tool returns.
- Writes go through redaction; secrets never enter the strand even via `memory.write`.
- See [Security Model](SECURITY_MODEL.md) for the agent-exfiltration threat and mitigations.
