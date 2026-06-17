# Helix — Plugin & Extension Architecture
**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD](TSD.md) · [MCP Integration](MCP_INTEGRATION.md) · [Decisions](../DECISIONS.md)

Helix is **pluggable by construction**: every component that could plausibly need swapping — the embedder, the vector/graph store, the extractor, the LLM router, the redactor, the agent connector, the sync backend — sits **behind an interface** and is discovered via **entry points**. The default configuration runs **local-only and `$0`**; every paid or networked component is opt-in.

> Design authority: **ADR-030** (plugin architecture) and **ADR-018** (store interface). See [Decisions](../DECISIONS.md).

---

## 1. Extension Points

```
                     ┌──────────────────────────────────────────────┐
   agent text  ──▶   │  AgentConnector   (Claude Code / Cursor / …) │
                     └───────────────┬──────────────────────────────┘
                                     ▼
                     ┌──────────────────────────────────────────────┐
                     │  Extractor   → memories (+ supersede hints)  │
                     │  Redactor    → strip secrets/PII             │
                     │  LLMRouter    → Provider (gemini/openai/…)    │
                     └───────────────┬──────────────────────────────┘
                                     ▼
                     ┌──────────────────────────────────────────────┐
                     │  Embedder   → vectors  (fastembed / gemini)  │
                     ├──────────────────────────────────────────────┤
                     │  VectorStore  +  GraphStore                  │
                     │  SQLite → Lance → pgvector → Qdrant          │
                     └───────────────┬──────────────────────────────┘
                                     ▼
                     ┌──────────────────────────────────────────────┐
                     │  SyncBackend  (optional, opt-in export/pull) │
                     └──────────────────────────────────────────────┘
```

| Interface | Responsibility | Default impl | Optional impls |
|-----------|----------------|--------------|----------------|
| `Embedder` | text → vector | `FastEmbedEmbedder` (local) | `GeminiEmbedder`, `OpenAIEmbedder` |
| `VectorStore` | persist + ANN search | `SQLiteStore` | `LanceStore`, `PgvectorStore`, `QdrantStore` |
| `GraphStore` | nodes + typed edges | `SQLiteGraphStore` | `PgGraphStore` |
| `Extractor` | turn turns into memories; emit supersede hints | `HeuristicExtractor` | `LLMExtractor` |
| `LLMRouter` / `Provider` | route extraction/judging calls to a model | `NullRouter` (heuristics only) | `GeminiProvider`, `OpenAIProvider`, `OllamaProvider` |
| `Redactor` | strip secrets/PII before persist & log | `RegexRedactor` | `LLMRedactor` |
| `AgentConnector` | speak a client's config dialect / protocol | `ClaudeCodeConnector` | Cursor / Windsurf / VS Code / Gemini / Zed / Codex / `OpenAIRouterConnector` |
| `SyncBackend` | export/import "strands" to remote | `NoopSync` | `S3Sync`, `HelixCloudSync` |

Every interface is small, synchronous-or-async-agnostic, and **versioned** (`HELIX_PLUGIN_API = "1"`).

---

## 2. Registration & Discovery (entry points)

Plugins are ordinary Python (or Node) packages that advertise themselves via **entry points**. Helix scans the named groups at daemon startup, builds a registry, and selects an implementation by config key.

**Python (`pyproject.toml`)**

```toml
[project.entry-points."helix.embedders"]
gemini = "helix_gemini.embed:GeminiEmbedder"

[project.entry-points."helix.stores"]
qdrant = "helix_qdrant.store:QdrantStore"

[project.entry-points."helix.extractors"]
llm = "helix_llm_extract:LLMExtractor"
```

**Entry-point groups**

| Group | Selected by |
|-------|-------------|
| `helix.embedders` | `embedder = "..."` |
| `helix.stores` | `store = "..."` |
| `helix.graph_stores` | `graph_store = "..."` |
| `helix.extractors` | `extractor = "..."` |
| `helix.providers` | `llm.provider = "..."` |
| `helix.redactors` | `redactor = "..."` |
| `helix.connectors` | `connectors = [...]` |
| `helix.sync` | `sync.backend = "..."` |

**`helix.toml`**

```toml
embedder   = "fastembed"     # default, local, $0
store      = "sqlite"        # default
graph_store = "sqlite"
extractor  = "heuristic"
redactor   = "regex"

[llm]
provider = "null"            # no network calls by default
```

TS plugins register analogously through `package.json` `helix` manifest fields; the Node loader mirrors the Python registry.

---

## 3. Store Upgrade Path

The store interface (**ADR-018**) is the same for all four backends, so upgrading is a **migration, not a rewrite**. Pick the smallest store that fits the working set.

```
   SQLite          LanceStore        PgvectorStore        QdrantStore
   (default)   →   (embedded,     →  (shared Postgres, →  (dedicated ANN
   zero-dep        columnar ANN,     team / server)        service, scale-out)
   single file)    bigger local)
```

| Store | When | Tradeoff |
|-------|------|----------|
| `SQLiteStore` | Default. One project, single machine, `$0`. | Brute-force/IVF on small sets; fine to tens of thousands. |
| `LanceStore` | Larger local corpora, still embedded, no service. | Columnar, fast ANN, bigger disk footprint. |
| `PgvectorStore` | Team shares a Postgres; SQL ecosystem. | Needs a Postgres; ANN quality depends on index config. |
| `QdrantStore` | Large-scale / high-QPS ANN, payload filtering. | Runs a dedicated service; ops overhead. |

Migration command:

```bash
helix store migrate --to qdrant --url http://127.0.0.1:6333
# re-embeds only if the embedder changed; otherwise copies vectors + graph + metadata
```

Because **IDs are human-readable and stable** (see [API Reference](API_REFERENCE.md)), edges and citations survive migration unchanged.

---

## 4. Embedding Providers

| Provider | Network | Cost | Notes |
|----------|---------|------|-------|
| `fastembed` (default) | none | `$0` | Local ONNX models; the reason Helix is `$0` by default |
| `gemini` | yes | metered | Opt-in; needs `GEMINI_API_KEY` |
| `openai` | yes | metered | Opt-in; needs `OPENAI_API_KEY` |

The embedder is recorded in the **strand manifest** so a corpus is never silently re-embedded with a mismatched model on import.

```toml
embedder = "gemini"
[embedder.gemini]
model = "text-embedding-004"
# api key from env GEMINI_API_KEY — never written to config or logs
```

---

## 5. Agent Connectors

Each coding agent reads MCP server config from a **different file with a different top-level key**. The `AgentConnector` for each client knows its dialect and can write the right snippet via `helix connect <client>`.

| Client | Config file | Top-level key | Notable cap |
|--------|-------------|---------------|-------------|
| Claude Code | `.mcp.json` / `~/.claude.json` | `mcpServers` | ~25k-token tool output |
| Cursor | `.cursor/mcp.json` | `mcpServers` | — |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | `mcpServers` | **100-tool cap** |
| VS Code | `.vscode/mcp.json` | `servers` | **128 tools/request** |
| Gemini CLI | `~/.gemini/settings.json` | `mcpServers` | — |
| Zed | settings | `context_servers` | — |
| Codex CLI | `~/.codex/config.toml` | `[mcp_servers.<name>]` (TOML) | — |

**JSON dialect (Claude Code / Cursor / Windsurf / Gemini)**

```json
{
  "mcpServers": {
    "helix": { "command": "helix-mcp", "args": ["--stdio"] }
  }
}
```

**VS Code dialect** — same shape, different key:

```json
{ "servers": { "helix": { "command": "helix-mcp", "args": ["--stdio"] } } }
```

**Zed dialect** — `context_servers`:

```json
{ "context_servers": { "helix": { "command": "helix-mcp", "args": ["--stdio"] } } }
```

**Codex CLI dialect** — TOML:

```toml
[mcp_servers.helix]
command = "helix-mcp"
args    = ["--stdio"]
```

All of these point at the **stdio shim**, which proxies to the one local daemon (see [API Reference §1](API_REFERENCE.md)).

### 5.1 OpenAI-compatible "memory router" fallback (non-MCP agents)

Agents that **don't speak MCP** can still get memory via an **OpenAI-compatible memory router**: point the agent's base URL at Helix instead of the model provider, and Helix transparently recalls + injects memory before forwarding the completion. This is the **Supermemory-style base-URL swap** pattern, authenticated with `x-api-key`. (https://supermemory.ai/docs/memory-router/overview)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:7878/v1/openai/https://api.openai.com",  # prefix swap
    api_key="sk-...",
    default_headers={"x-api-key": "helix-local"},
)
# requests flow through Helix: recall → inject → forward → extract → persist
```

A REST/SDK surface in the **Mem0** style is also available for scripted use. (https://docs.mem0.ai/open-source/features/rest-api)

---

## 6. Worked Example — Writing a Plugin

A minimal third-party embedder.

**`pyproject.toml`**

```toml
[project]
name = "helix-cohere"
dependencies = ["helix-sdk>=1", "cohere"]

[project.entry-points."helix.embedders"]
cohere = "helix_cohere:CohereEmbedder"
```

**`helix_cohere/__init__.py`**

```python
from helix.plugins import Embedder, register   # stable plugin API (v1)
import cohere, os

class CohereEmbedder(Embedder):
    api_version = "1"                 # must match HELIX_PLUGIN_API
    name = "cohere"
    dim = 1024

    def __init__(self, config: dict):
        self._client = cohere.Client(os.environ["COHERE_API_KEY"])
        self._model = config.get("model", "embed-english-v3.0")

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embed(texts=texts, model=self._model,
                                  input_type="search_document")
        return resp.embeddings

register(CohereEmbedder)              # optional explicit registration
```

**Enable it**

```toml
embedder = "cohere"
[embedder.cohere]
model = "embed-english-v3.0"
```

```bash
pip install helix-cohere
helix doctor          # validates api_version, dim, env vars, round-trip embed
helix daemon restart
```

`helix doctor` rejects plugins whose `api_version` doesn't match the daemon's `HELIX_PLUGIN_API`, whose declared `dim` disagrees with a probe, or that touch the network when telemetry/offline mode forbids it.

---

## 7. Stability & Compatibility Policy

- **Plugin API is versioned** (`HELIX_PLUGIN_API`). Within a major version, interfaces are **additive-only**: new optional methods get safe defaults; existing signatures never change meaning.
- **Capability negotiation.** A plugin declares `api_version`; the daemon refuses to load mismatched majors rather than failing mysteriously at runtime.
- **Defaults stay `$0` and local.** A plugin that requires the network must declare `requires_network = True`; in offline/telemetry-off mode the daemon **will not load it** unless explicitly allowed.
- **Stores are forward-only.** The store interface (ADR-018) gains capabilities additively; migrations are one-way and re-use stable IDs so the graph survives.
- **Secrets stay in env.** Plugins read credentials from environment variables only; config and logs never carry keys (enforced by the `Redactor`; see [Observability](OBSERVABILITY.md) and [Security Model](SECURITY_MODEL.md)).

---

## Sources

- Supermemory OpenAI-compatible memory router (base-URL swap, `x-api-key`) — https://supermemory.ai/docs/memory-router/overview
- Mem0 open-source REST API — https://docs.mem0.ai/open-source/features/rest-api
- MCP client config dialects (mcpServers / servers / context_servers / TOML; tool caps) — https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

**See also:** [API Reference](API_REFERENCE.md) · [TSD](TSD.md) · [MCP Integration](MCP_INTEGRATION.md) · [Observability](OBSERVABILITY.md) · [Security Model](SECURITY_MODEL.md) · [Decisions](../DECISIONS.md)
