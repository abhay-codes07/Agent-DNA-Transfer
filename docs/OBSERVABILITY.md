# Helix — Observability & Cost Telemetry
**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD](TSD.md) · [MCP Integration](MCP_INTEGRATION.md) · [Decisions](../DECISIONS.md) · [Cost](COST_OPTIMIZATION.md) · [Security](SECURITY_MODEL.md)

Helix's observability story exists to **prove two claims**: that it costs `$0` by default, and that it never leaks. Telemetry is **off by default**, **local-only when on**, and **secrets are never logged**.

> Design authority: **ADR-007** (telemetry posture) and **ADR-025** (cost dashboard / budget guardrail). See [Decisions](../DECISIONS.md).

---

## 1. Principles

1. **OFF by default.** No metrics, no logs leave the machine — and by default nothing is even collected beyond what `--verbose` prints. Telemetry is an explicit opt-in.
2. **Local-only when on.** When telemetry is enabled it writes to a **local** store and a **local** `/metrics` endpoint. There is **no default phone-home**.
3. **Secrets never logged.** The `Redactor` runs *before* anything is persisted or printed. API keys, tokens, and detected PII are replaced with `‹redacted›`. (See [Security Model](SECURITY_MODEL.md).)
4. **Redacted logs everywhere.** Even at `DEBUG`, memory *content* is summarized/hashed, not dumped, unless `--unsafe-log-content` is set explicitly.
5. **Cost is observable, not estimated after the fact.** Every LLM/embedding call is metered at call time so the dashboard is always current.

---

## 2. Local Metrics

Collected in-process and exposed locally. Nothing here requires a network.

```
   ┌──────────────────────── helixd ────────────────────────┐
   │  recall path     write path      consolidation worker  │
   │   p50/p95 lat    gate drop-rate   op-mix (merge/super…) │
   │   cache hits     tokens/cost      store sizes           │
   └───────────────┬─────────────────────────────────────────┘
                   ▼
            local metrics registry  ──▶  GET /metrics (Prometheus text)
                   │
                   ▼
            helix cost   (terminal dashboard)
```

**What's measured**

- **Recall latency** — `p50` / `p95` of `memory.search` + `memory.context`.
- **Gate drop-rate** — fraction of candidate memories dropped by the relevance/budget gate (the lever that keeps token spend near zero).
- **LLM usage** — calls, prompt/completion tokens, **estimated cost** per provider/model.
- **Embedding** — calls, tokens, and **cache hit rate** (a cache hit is a `$0` embed).
- **Store sizes** — memory count, vector bytes, graph edges, on-disk bytes per store.
- **Consolidation op mix** — counts of `merge` / `supersede` / `tombstone` / `noop` from the worker.

---

## 3. The Cost Dashboard (proving "$0")

`helix cost` renders the numbers that back the `$0`-default claim and a **monthly token-budget guardrail** (ADR-025, [Cost Optimization](COST_OPTIMIZATION.md)).

```
$ helix cost --period month
HELIX COST  ·  2026-06  ·  provider: null (local fastembed)
────────────────────────────────────────────────────────────
LLM calls ............ 0            tokens ........ 0
Embedding calls ...... 1,284        tokens .. 412,909   (local, $0)
Embedding cache hits . 71%          → 3,140 embeds avoided
Gate drop-rate ....... 63%          → tokens kept out of context
Estimated spend ...... $0.00        budget: $0.00 / mo   ✔ under
────────────────────────────────────────────────────────────
Guardrail: token budget  0 / 2,000,000 paid tokens   ▱▱▱▱▱  0%
```

When a paid provider is enabled, the same view shows real spend and trips the guardrail:

```
Estimated spend ...... $1.84        budget: $5.00 / mo   ✔ under
Guardrail: token budget  730k / 2,000,000 paid tokens  ▰▰▱▱▱  37%
```

The **gate drop-rate** is the headline cost-control metric: a high drop-rate means Helix is aggressively keeping irrelevant memory out of the token budget, which is *why* `$0`/cheap is achievable. The **monthly token-budget guardrail** warns and can **hard-stop** paid calls when exceeded.

---

## 4. Structured Logging

JSON lines, leveled, redacted.

| Level | Use |
|-------|-----|
| `ERROR` | failed writes/recalls, plugin load failures, store errors |
| `WARN` | budget guardrail tripped, gate dropped unusually high, slow recall |
| `INFO` | daemon lifecycle, migrations, connector writes, consolidation summaries |
| `DEBUG` | per-call timings, gate decisions, cache hits (content **redacted/hashed**) |
| `TRACE` | wire-level JSON-RPC framing (loopback only; never includes secrets) |

```json
{"ts":"2026-06-18T10:12:04Z","level":"INFO","evt":"recall",
 "scope":"project","took_ms":18,"p":"p50","hits":8,"dropped":14,
 "tokens_used":1180,"query":"‹redacted›"}
```

`query` and memory content are redacted by default; set `--unsafe-log-content` only for local debugging.

---

## 5. Metrics Catalog

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `helix_recall_latency_seconds` | histogram | `op{search,context}` | recall p50/p95 |
| `helix_gate_dropped_total` | counter | `scope` | memories dropped by the gate |
| `helix_gate_candidates_total` | counter | `scope` | candidates considered (drop-rate = dropped/candidates) |
| `helix_llm_calls_total` | counter | `provider`,`model` | LLM invocations |
| `helix_llm_tokens_total` | counter | `provider`,`model`,`dir{prompt,completion}` | LLM tokens |
| `helix_llm_cost_usd_total` | counter | `provider`,`model` | estimated spend |
| `helix_embed_calls_total` | counter | `provider` | embedding calls |
| `helix_embed_cache_hits_total` | counter | `provider` | cache hits (= `$0` embeds) |
| `helix_store_bytes` | gauge | `store`,`kind{vector,graph}` | on-disk size |
| `helix_memories_total` | gauge | `scope` | live memory count |
| `helix_consolidation_ops_total` | counter | `op{merge,supersede,tombstone,noop}` | worker op mix |
| `helix_budget_tokens_used` | gauge | `period` | paid tokens vs monthly guardrail |

---

## 6. The `/metrics` Endpoint

The daemon optionally serves a **Prometheus-style text endpoint** — **local only**, bound to `127.0.0.1`, subject to the same `Origin` validation as the rest of the daemon (see [API Reference §1](API_REFERENCE.md)).

```bash
curl -s 127.0.0.1:7878/metrics | head
# HELP helix_recall_latency_seconds Recall latency
# TYPE helix_recall_latency_seconds histogram
helix_recall_latency_seconds_bucket{op="search",le="0.01"} 402
helix_gate_dropped_total{scope="project"} 9381
helix_embed_cache_hits_total{provider="fastembed"} 3140
helix_llm_cost_usd_total{provider="null",model="none"} 0
```

Disabled unless `telemetry.metrics = true`. There is no remote scrape target by default; you opt in by pointing your *own* local Prometheus at loopback.

---

## 7. Opt-in Aggregate Sharing

Helix never exfiltrates by default. If — and only if — a user runs `helix telemetry share --aggregate`, Helix may send **coarse, non-content aggregates** (e.g., recall p95 bucket, gate drop-rate band, store-size class). Rules:

- **No memory content, no queries, no IDs, no keys** ever leave the machine.
- Payloads are **redacted and bucketed** before send; reviewable via `helix telemetry preview`.
- **Revocable** at any time (`helix telemetry share --off`); default remains **off**.

---

## 8. Opinionated Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Telemetry **OFF by default** | Local-first trust; nothing leaks unless asked (ADR-007) |
| 2 | Metrics & logs are **local-only** | No default phone-home; you own the data |
| 3 | **Redactor runs before persist & log** | Secrets/PII never reach disk or stdout (ADR-024) |
| 4 | **Gate drop-rate** is a first-class metric | It's the lever that proves `$0`/cheap |
| 5 | **Cost metered at call time**, not estimated later | Dashboard is always current; guardrail can hard-stop |
| 6 | **Monthly token-budget guardrail** with hard-stop option | Bounds worst-case spend for paid providers (ADR-025) |
| 7 | **Embedding cache hit rate** surfaced | Cache hits are `$0` embeds — the default-cost story |
| 8 | `/metrics` is **opt-in, loopback, Origin-validated** | Observability without opening an attack surface |

---

## Sources

- MCP Transports — local bind `127.0.0.1` + Origin validation (DNS-rebinding defense) — https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- Writing tools for agents — token-budget discipline informs the cost dashboard — https://www.anthropic.com/engineering/writing-tools-for-agents

**See also:** [API Reference](API_REFERENCE.md) · [Plugins](PLUGINS.md) · [TSD](TSD.md) · [MCP Integration](MCP_INTEGRATION.md) · [Cost Optimization](COST_OPTIMIZATION.md) · [Security Model](SECURITY_MODEL.md) · [Decisions](../DECISIONS.md)
