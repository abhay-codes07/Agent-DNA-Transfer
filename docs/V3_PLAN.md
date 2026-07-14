# Helix v3 — Phase 3 Plan ("Memory that compounds")

> Status: **Proposed** · Authored 2026-07-14 · Builds on [`docs/V2_PLAN.md`](V2_PLAN.md)
> ("Git for your AI's memory") and the shipped v2 engine.
> Research backing: a July-2026 frontier sweep (agent-memory survey + arXiv preprints, coding
> long-horizon benchmarks, context-engineering/compaction, on-device embeddings). Source
> appendix at the end. This doc is the contract for what v3 is and the order we build it.

---

## 0. TL;DR

v1 made memory **local and ownable**. v2 made it **portable, signed, and mergeable** — *"Git for
your AI's memory."* The field has since moved again, and v3 answers where it went.

The 2026 research consensus is sharp and consistent across independent groups:

1. **Memory is becoming *active*, not a passive store.** The frontier is *Memory-as-Action* —
   the agent decides *when* to write, edit, compact, and forget as first-class actions, and
   *context compaction* (Anthropic's `compact-2026-01-12` API; CompactionRL; Self-Compacting
   agents) is now the dominant way long-horizon agents survive. The open question is where the
   dropped context *goes*. Today it evaporates. **That's Helix's opening: be the durable sink
   for compaction.**
2. **Experience must *compound*, with fair credit assignment.** Memory-R2, Fine-Mem, and
   DELTAMEM all attack the same problem: an agent should get *measurably better* from its own
   outcomes, and each memory should be rewarded/penalized in proportion to how much it actually
   helped. v2 shipped this for *procedures* (reliability grows on confirmed reuse). v3
   generalizes it to **every fact** — the strand demonstrably improves, and we can *prove it*.
3. **Temporal reasoning is the #1 unsolved gap.** Independent benchmarks (LongMemEval-V2,
   LoCoMo temporal split) show **up to 15-point accuracy gaps** on "when/why did this change?"
   queries — the single weakest axis across every memory architecture. Helix already stores
   bi-temporal columns almost nobody else has. v3 turns that latent asset into a **temporal
   reasoning surface** that answers belief-change queries directly.
4. **Coding memory needs its own eval, and long-horizon software evolution is the arena.**
   SWE-EVO and the "knowledge compounding / agentic ROI" line argue the metric that matters is
   not chat recall — it's *does the agent's stored experience make the next task cheaper and
   more likely to succeed?* v3 ships that benchmark.

**The v3 thesis in one line:** *v1 you own it, v2 you move it — v3 it **compounds**. Helix is
the only local-first, portable memory that makes your coding agent measurably better over time,
proves it with a coding-native benchmark, and is the durable place your agent's context goes
when it compacts.*

Like v2, **v3 is additive, not a rewrite.** The engine, `.dna` container, and MCP surface all
stand; v3 adds an experience/credit-assignment layer, a temporal-reasoning surface, a
compaction bridge, and the eval that scores them — every piece $0/offline by default.

---

## 1. Where the field moved (July-2026 frontier map)

```
        PASSIVE STORE ─────────────────────────────► ACTIVE / AGENTIC MEMORY
   (RAG-over-facts)                                (Memory-as-Action, self-editing)
        v1 ● ────────► v2 ● (portable/mergeable) ────────► ★ v3 (compounding + active)

   Axes the 2026 papers converged on, and where Helix stands:
   ┌────────────────────────────┬───────────────────────────────┬──────────────┐
   │ Frontier axis              │ SOTA direction (2026)         │ Helix today  │
   ├────────────────────────────┼───────────────────────────────┼──────────────┤
   │ Active / self-managing     │ Memory-as-Action, compaction  │ passive → v3 │
   │ Experience compounding     │ Memory-R2 credit assignment   │ procedures→v3│
   │ Temporal reasoning         │ bi-temporal + change events   │ columns → v3 │
   │ Long-horizon coding eval   │ SWE-EVO, agentic ROI          │ recall eval  │
   │ On-device embeddings       │ EmbeddingGemma / Qwen3 / jina │ bge-small    │
   └────────────────────────────┴───────────────────────────────┴──────────────┘
```

Helix keeps the two structural advantages no funded competitor can copy without abandoning
their cloud-first economics — **local-first ownership** and a **portable signed strand** — and
now claims a third the incumbents aren't even chasing yet: **memory that compounds and proves
it, offline.**

---

## 2. The five v3 pillars

Each capability carries an effort tag (S/M/L) and a priority (P0 = v3.0 headline, P1 = v3.x,
P2 = later). Everything runs at $0 with no network unless a row says otherwise; cloud stays
opt-in.

### Pillar 1 — Compounding memory (the headline: experience + credit assignment)

The defining v3 capability. v2 proved the mechanism on procedures; v3 makes *the whole strand*
learn from outcomes and dramatizes the result.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 1.1 | **Outcome-driven credit assignment for every fact** | Generalize `record_procedure_outcome` into `record_outcome(memory_ids, success)`: when recalled memories contribute to a task that succeeds/fails, each earns a Laplace-smoothed reliability `(wins+1)/(uses+2)` (Memory-R2-lite, fully offline/deterministic — **not** RL). Proven facts float up; repeatedly-unhelpful ones sink. | M | **P0** |
| 1.2 | **Experience-weighted ranking** | Fold reliability into the retrieval score as a *bounded, neutral-at-baseline* multiplier (0.5 reliability → ×1.0, so a fresh strand's ranking is unchanged). The recall pipeline stops being static and starts reflecting what actually worked. | S | **P0** |
| 1.3 | **The compounding meter** | A first-class metric — reuse rate, outcomes recorded, win rate, avg reliability, reliability trend — the v3 analogue of the $0 meter. Turns "your memory is getting smarter" from a claim into a number on the dashboard. | S | **P0** |
| 1.4 | **Skill distillation from successful trajectories** | When an episode ends in an observed success signal (tests pass/build green), auto-distill the trajectory into a `procedure` (Voyager/Fine-Mem). Extends v2's manual `learn_procedure` into automatic skill acquisition. | M | P1 |
| 1.5 | **Contradiction-aware decay of low-reliability facts** | A fact repeatedly present at *failures* is a candidate for the review queue (advisory, never auto-deleted) — the negative half of credit assignment, on-brand with "the user owns the memory." | S | P1 |

### Pillar 2 — Temporal reasoning (close the #1 benchmark gap)

Helix's bi-temporal columns are a latent asset; v3 exposes them as answers.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 2.1 | **`history_of(subject)` — belief timeline** | The ordered history of what Helix believed about a subject: current + superseded facts by `valid_from`, with each transition (from→to→when). Directly answers the temporal queries where every architecture loses 15 points. Builds on v2's `changes`/`as_of`. | M | **P0** |
| 2.2 | **Temporal query grammar** | Parse "as of", "when did", "before/after" phrasing in recall and route to the bitemporal path instead of pure semantic match — so an agent's natural question hits the right index. | M | P1 |
| 2.3 | **Change-point summaries** | On demand, summarize the arc of a decision ("Postgres→Mongo→Postgres, and why each time") from the supersession chain. LLM-optional; deterministic fallback lists the transitions. | S | P1 |

### Pillar 3 — The compaction bridge (be where context goes when it's dropped)

The single biggest *new* integration surface in 2026. When an agent compacts, the pruned
context is exactly the distilled-facts Helix exists to keep.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 3.1 | **`distill_session(messages)` — pre-compaction sink** | A named surface that takes an agent's about-to-be-dropped working context and distills durable facts from it (reuses batched extraction + the redaction/gate pipeline). The compaction handoff the ecosystem is standardizing around, made durable and local. | M | **P0** |
| 3.2 | **`memory_distill` / `memory_outcome` MCP tools** | Expose the compaction sink and the credit-assignment loop to agents over MCP — the two operations that make memory *active* from the agent's side (ADR-038, grows the surface 10→12, still small). | S | **P0** |
| 3.3 | **Compaction-aware provenance** | Facts distilled at compaction carry a `compaction` origin marker so the dashboard can show "learned while compacting session X" and the user can audit the automatic sink. | S | P1 |
| 3.4 | **Reflection-on-session** | After a session, synthesize the 1–3 durable lessons (not every turn) — sleep-time consolidation triggered by the session boundary rather than a cron. | M | P1 |

### Pillar 4 — Prove it (the coding-memory benchmark)

v2 promised a coding eval; v3 makes it the yardstick and scores the new capabilities.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 4.1 | **Compounding & temporal eval metrics** | Extend `helix eval` with: reuse-rate, build-green-after-recall proxy, stale-catch rate, **temporal-accuracy** (does `history_of` answer the change query?), and an **agentic-ROI** proxy (did recall make the second attempt cheaper?). | M | **P0** |
| 4.2 | **SWE-EVO-style scenario harness** | A small, local, multi-episode scenario (a project evolving over "sessions") that exercises compounding end-to-end — the honest coding analog to LongMemEval-V2's trajectory benchmark. | L | P1 |
| 4.3 | **Regression gate in CI** | Fail the build if compounding/temporal metrics drop below a floor — the eval becomes a contract, not a report. | S | P1 |

### Pillar 5 — Engine modernization (keep pace on the primitives)

Non-headline but overdue; each is gated and $0-preserving.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 5.1 | **Embedding refresh** | Wire **EmbeddingGemma-300M** / **Qwen3-Embedding** / **bge-code-v1** as opt-in fastembed models behind config, with int8 + Matryoshka storage (v2 §2.2 executed). bge-small stays the dependency-free default. | S–M | P1 |
| 5.2 | **Local LLM extraction path polish** | Make the Ollama/local-model extractor first-class for sleep-time consolidation so higher-quality distillation needs no API. | M | P1 |
| 5.3 | **Perf budgets in CI** | Recall p95 + strand-footprint budgets enforced (already listed in ROADMAP cross-phase; wire it). | S | P2 |

---

## 3. Roadmap — three waves

### Wave A — "Compounding memory" (v3.0) — the headline
The thesis made real, entirely $0/offline/deterministic:
- **Compounding:** 1.1 credit assignment for every fact, 1.2 experience-weighted ranking,
  1.3 the compounding meter.
- **Temporal:** 2.1 `history_of(subject)`.
- **Compaction bridge:** 3.1 `distill_session`, 3.2 `memory_outcome` + `memory_distill` MCP tools.
- **Prove it:** 4.1 compounding + temporal eval metrics.
- Full SDK parity + docs (ADR-038) + tests.

### Wave B — "Active & temporal" (v3.1)
- 1.4 auto-skill distillation, 1.5 low-reliability review, 2.2 temporal grammar, 2.3 change
  summaries, 3.3 compaction provenance, 3.4 reflection-on-session, 4.2 SWE-EVO harness,
  4.3 CI regression gate.

### Wave C — "Modernized primitives" (v3.2+)
- 5.1 embedding refresh, 5.2 local-LLM extraction, 5.3 perf budgets. Dashboard surfaces for the
  compounding meter + belief timeline.

---

## 4. Success metrics (what "v3 worked" means)

- **Compounding is real:** after recording outcomes, proven facts rank measurably higher and the
  compounding meter climbs across a scenario — verified in the eval, not asserted.
- **Temporal accuracy:** `history_of` answers belief-change queries the pure-semantic path misses
  (closes the documented 15-point gap on the local eval).
- **Compaction sink works:** a dropped working-context distills to durable, sourced, redacted
  facts — round-tripped in a test.
- **$0 promise intact:** every Wave-A capability makes zero network calls; the compounding meter,
  like the $0 meter, is computed locally.

## 5. Non-goals / guardrails (unchanged golden rules)

- No core path may require a network call or cloud account. Credit assignment is offline
  arithmetic, **not** RL; RL/auto-tuning stays opt-in cloud (v2 §1.7).
- Never store raw transcripts — `distill_session` distills, it does not log. The compaction sink
  keeps *facts*, not the dropped tokens.
- Credit assignment **never auto-deletes**; low reliability routes to the review queue. The user
  owns the memory.
- Every new fact still carries `source · created_at · confidence · type`; experience adds
  `reliability` without dropping any of them.
- Don't bloat the MCP surface: v3 adds exactly two agent-facing tools, both central to active
  memory, documented and ADR'd.

## 6. Top risks

1. **Credit-assignment noise** — a single outcome shouldn't swing ranking. Mitigate with Laplace
   smoothing + a bounded, neutral-at-baseline multiplier (Wave A ships conservative constants).
2. **Temporal surface complexity** — keep `history_of` deterministic over existing columns; defer
   the NL grammar (2.2) to Wave B.
3. **Compaction-sink over-capture** — the gate + redaction still apply; distill, never log; mark
   provenance so the user can audit.
4. **Eval over-fitting** — the coding eval is a floor and a compass, not a leaderboard to game;
   keep it honest and local.

---

## Appendix — research sources (July-2026 sweep)

**Agent-memory frontier:** *Memory in the Age of AI Agents: A Survey* (Agent-Memory-Paper-List),
Fine-Mem (arXiv 2601.08435), SAM: State-Adaptive Memory (2605.24468), Memory-R2 (2605.21768),
DELTAMEM (2606.03083), ACE: Adaptive Context Elasticizer (2606.31564), *Agentic Memory: Unified
Long/Short-Term Management*, *EverMemOS*, *Memory as Action: Autonomous Context Curation*,
*The State of AI Agent Memory in 2026* (vektor/mem0), 2026 Memory Literature Scan.

**Coding / long-horizon eval:** SWE-EVO (2512.18470), LongMemEval-V2 (2605.12493), LoCoMo +
temporal split, BEAM, LOCA-bench (2602.07962), *Knowledge Compounding / Agentic ROI* (2604.11243),
Hippocampus memory module (2602.13594), ByteRover 2.0 LoCoMo results.

**Context engineering / compaction:** Anthropic *Effective context engineering for AI agents* +
the compaction API (`compact-2026-01-12`), CompactionRL (2607.05378), Self-Compacting LM Agents
(2606.23525), Slipstream trajectory-grounded compaction (2605.08580), subagent context isolation.

**On-device embeddings:** EmbeddingGemma (arXiv 2509.20354), Qwen3-Embedding (2506.05176),
jina-embeddings-v3, BGE-M3 + BGE-reranker-v2, bge-code-v1, nomic-embed-text-v2; Matryoshka + int8
quantization; local-on-Apple-Silicon comparisons (June 2026).
