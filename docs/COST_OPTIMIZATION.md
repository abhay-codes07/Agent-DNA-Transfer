# Helix — Cost Optimization

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD §8](TSD.md) · [ADR-006](../DECISIONS.md) · [ADR-007](../DECISIONS.md)

**Goal: the default configuration costs $0 and ≥ 90% of active users never incur API spend
(PRD §9), without crippling the product.** Cost is treated as an architectural invariant, not
a tuning afterthought.

---

## 1. Where cost would come from (and how we remove it)

| Cost source | Naive approach | Helix approach | Result |
|---|---|---|---|
| Embeddings (highest volume) | Cloud embedding per memory | **Local** `fastembed` bge-small | $0, offline |
| Fact extraction | LLM call per message | **Heuristic gate** drops most; LLM only when needed | ~0 calls for most turns |
| Which LLM, when used | Premium model always | **Gemini 2.0 Flash free tier** → `gpt-4o-mini` fallback | free-tier-first |
| Repeated/identical work | Re-call every time | **Response cache** keyed by input hash | pay once |
| Many small calls | One call per turn | **Batch** buffered turns into one call | fewer, bigger, cheaper calls |
| Verbose prompts/outputs | Free-form text | **Structured JSON** + compact prompts | minimal tokens |
| Runaway spend | Unbounded | **Token budget guardrail** (`0` = no paid calls) | hard ceiling |

## 2. The pipeline (cost view)

```
 slice
   │
   ▼
 [Redaction]                         local, $0
   │
   ▼
 [Heuristic gate] ── "no durable fact" ─────────────► DROP   (most slices end here, $0)
   │  "maybe a fact"
   ▼
 [Cache lookup] ── hit ─────────────────────────────► reuse  ($0)
   │ miss
   ▼
 [Extractor]
   ├─ no key            → deterministic (rules+embeddings)    $0
   ├─ Ollama present    → local LLM                            $0
   ├─ Gemini key        → Gemini 2.0 Flash (free tier)         ~$0
   └─ OpenAI fallback   → gpt-4o-mini                          tiny $, only if needed
   │
   ▼
 [Embed] → local by default                                   $0
```

The two biggest levers are at the top: **local embeddings** make the highest-volume operation
free, and the **heuristic gate** ensures the LLM is rarely invoked at all.

## 3. The heuristic gate (primary lever)

Before any model runs, a cheap local check estimates "is there a durable, novel fact here?"
Signals:

- **Cues:** "remember", "always/never", "I prefer", "we decided", "the convention is".
- **Structure:** presence of entities, decisions, imperatives; slice length/type.
- **Novelty:** embedding distance to the nearest existing memory — if it's basically a
  duplicate, there's nothing to learn.

If the gate isn't confident there's a fact (`< HELIX_HEURISTIC_CONFIDENCE_CUTOFF`), the slice
is dropped with **zero** model calls. Most conversation turns don't contain durable new facts,
so most are dropped here — which is what keeps default cost at ~$0 even with an LLM enabled.

## 4. Free-tier-first LLM router

Policy (LiteLLM under the hood, [ADR-007](../DECISIONS.md)):

1. If `HELIX_LLM_PROVIDER=none` or no key → **deterministic** extractor (always $0).
2. Else prefer **Gemini 2.0 Flash** (free tier) for extraction/consolidation.
3. On rate-limit/unavailable, or if the user prefers it → **gpt-4o-mini**.
4. On any failure → fall back to deterministic (degrade quality, never lose data or block).

Every call is **cached** (hash of prompt + inputs), **batched** where possible, and emitted as
**structured JSON** to minimize tokens.

## 5. Guardrails

- `HELIX_MONTHLY_TOKEN_BUDGET` — hard ceiling on paid tokens; `0` disables paid calls entirely
  (free tier + local only). When the ceiling is hit, the router transparently degrades to the
  deterministic path.
- **Cost telemetry (local):** the dashboard shows calls, tokens, estimated spend, and
  gate-drop rate, so a user can *see* they're at $0.
- **No surprise upgrades:** raising default cost requires an ADR ([CLAUDE.md](../CLAUDE.md) rule 3).

## 6. Quality ladder (you choose where to sit)

| Tier | Setup | Cost | Extraction quality |
|---|---|---|---|
| **Floor** | nothing (default) | $0, offline | good — heuristics + rules + embeddings |
| **Local LLM** | install Ollama | $0, offline | better — local model extraction |
| **Free cloud** | Gemini free key | ~$0 | great — frontier-ish quality |
| **Paid fallback** | OpenAI key | tiny | great — only when free tier is exhausted |

The product is genuinely useful at the **floor**; keys only *raise* quality. Free should feel
first-class, not like a teaser (PRD §8).

## 7. What we deliberately avoid

- Cloud embeddings by default (the silent budget-killer).
- An LLM call per message.
- Storing/Re-embedding things that didn't change (decay + content hashing avoid churn).
- Premium models for routine extraction.

## 8. Validation

Cost integrity is a tracked metric (PRD §9): **≥ 90% of active users on the $0 path.** CI
includes the no-key/offline configuration as a first-class test target so the free path can
never silently regress.
