# Helix — Evaluation & Benchmarks

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [Retrieval](RETRIEVAL.md) · [Consolidation](CONSOLIDATION.md) · [PRD](PRD.md) · [Decisions](../DECISIONS.md)

Helix is a local-first, coding-agent-first, portable, $0-default AI memory layer. A memory layer is only worth shipping if we can prove it makes an agent *measurably* better — more correct, faster, cheaper in tokens — without quietly poisoning itself. This document specifies how we measure memory quality: which external benchmarks we trust (and which we don't), the benchmark *gap* we intend to fill for coding agents, and the internal eval harness that gates every release.

Per **ADR-027 (evaluation strategy)**, Helix standardizes on **LongMemEval over LoCoMo** as the primary external instrument, and commits to **defining and publishing a coding-agent memory benchmark** that does not currently exist. The rationale follows.

---

## 1. The benchmark landscape

There is no single benchmark that measures what Helix actually does. The conversational-memory benchmarks measure *some* of it (extraction, multi-session reasoning, knowledge updates), the coding benchmarks measure end-task correctness but assume *zero* cross-task memory, and vendor leaderboards are an actively contested mess. We triage them here.

### 1.1 LoCoMo — the most-cited, most-criticized

LoCoMo (Long-term Conversational Memory) is the de-facto reference benchmark: **1540 questions** across four categories — single-hop, multi-hop, open-domain, and temporal — over long synthetic multi-session dialogues. It is the number everyone quotes.

It is also the number you should stop quoting. The Zep teardown ([blog.getzep.com](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/)) documents structural flaws that make LoCoMo a weak discriminator of memory quality:

| Documented flaw | Why it breaks the benchmark |
|---|---|
| **Conversations are tiny** | Individual conversations are only **~16K–26K tokens** — well within a modern model's context window. A "long-term memory" benchmark that fits in context isn't testing memory. |
| **A full-context baseline wins** | Dumping the *entire* conversation into the prompt scores **~73% (J / LLM-judge)** — beating specialized memory systems. If naïve full-context beats your memory layer, the benchmark isn't rewarding memory. |
| **No knowledge-update questions** | LoCoMo never asks "what is the *current* value of a fact that changed?" — so it cannot measure contradiction handling or staleness, the hardest and most valuable part of real memory. |
| **Data-quality errors** | Mislabeled and ambiguous gold answers inflate noise and let scoring methodology swing results by 20+ points. |

The category we care about most — **knowledge updates** — is simply absent. We use LoCoMo only as a legacy sanity check, never as a quality signal.

### 1.2 Vendor LoCoMo numbers are contested — do not trust them

The published LoCoMo leaderboard is a vendor brawl, not a measurement. A non-exhaustive timeline:

| Claim | Source |
|---|---|
| Mem0 ~**66.9%** LLM-judge, **91% lower p95** latency, **~90% token savings** (~**1.8K vs 26K** tokens/conversation) | [arxiv.org/abs/2504.19413](https://arxiv.org/abs/2504.19413), [mem0.ai/research](https://mem0.ai/research) |
| Zep claims **75.14%** (corrected methodology) vs Mem0's reported 66% | [blog.getzep.com](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/) |
| Mem0 counters: Zep's own number drops **84% → 58.44%** under corrected scoring | [github.com/getzep/zep-papers/issues/5](https://github.com/getzep/zep-papers/issues/5) |

The lesson is not "who is right" — it's that **the same benchmark produces wildly different numbers depending on who runs the scoring**, which is the signature of a benchmark that doesn't constrain its evaluation methodology. **Helix policy: we do not cite vendor LoCoMo scores as evidence of anything, including our own.** The one number worth retaining is the **~1.8K vs 26K token yardstick** — not as a leaderboard rank, but as a *target*: memory must save tokens versus full-context (see §3).

### 1.3 LongMemEval — the better instrument

LongMemEval (ICLR 2025) is what LoCoMo should have been: **500 human-curated questions** over realistic long histories, with **LongMemEval_S at ~115K tokens** and **LongMemEval_M up to ~1.5M tokens** — large enough that you *cannot* cheat with full-context ([arxiv.org/abs/2410.10813](https://arxiv.org/abs/2410.10813)). Crucially, it measures the five capabilities that map directly onto Helix's value proposition:

| Capability | What it tests | LoCoMo? |
|---|---|---|
| **Information extraction** | Pull a specific fact stated once across a long history | partial |
| **Multi-session reasoning** | Synthesize facts spread across many sessions | partial |
| **Temporal reasoning** | Reason about *when* things happened / ordering | weak |
| **Knowledge updates** | Return the **current** value of a fact that changed; detect the contradiction | **absent** |
| **Abstention** | Refuse to answer when the information is genuinely absent | **absent** |

The last two — knowledge updates and abstention — are exactly the capabilities LoCoMo ignores and exactly the failures that make a memory layer dangerous in production (stale facts, confident hallucination). LongMemEval is therefore our **primary external benchmark** per ADR-027.

### 1.4 MemBench & BEAM — operation coverage

LongMemEval is QA-shaped; it does not exercise the full *operation* surface of a memory system (write, update, delete, conflict resolution, forgetting). **MemBench** and **BEAM** extend coverage toward explicit memory operations ([mem0.ai/blog/ai-memory-benchmarks-in-2026](https://mem0.ai/blog/ai-memory-benchmarks-in-2026)). We track these as **secondary** instruments to stress the edit/forget and contradiction paths that QA accuracy alone hides (the same paths our internal harness targets in §3).

---

## 2. The coding-agent memory eval GAP

Here is the whitespace. **No mature memory benchmark exists for coding agents.** Every serious coding benchmark — SWE-bench, RepoBench, LongCodeBench, SWE Context Bench, SWE-EVO, SWE-Bench-CL — evaluates each task as an **independent episode** with **no memory carried between tasks**. The agent solves issue *N*, the harness resets, and issue *N+1* starts from a blank slate. The literature is blunt about it: *"every coding benchmark treats tasks as independent episodes with no memory between them"* ([arxiv.org/html/2602.08316v3](https://arxiv.org/html/2602.08316v3), [arxiv.org/pdf/2507.00014](https://arxiv.org/pdf/2507.00014), [arxiv.org/pdf/2512.13564](https://arxiv.org/pdf/2512.13564)).

That stateless framing is precisely the thing a coding-agent memory layer is supposed to fix. A benchmark that resets between tasks **cannot, by construction, measure the value of memory.** So the headline question Helix exists to answer is unmeasured by anyone:

> **Does remembering project conventions, decisions, and prior mistakes across sessions reduce repeat mistakes and tokens on the *next* task?**

### 2.1 Helix's whitespace: define & publish the benchmark

Helix will **define and publish a coding-agent memory benchmark** (working name: **HelixCodeMem**) that measures cross-task carryover rather than single-task solve rate. Design principles:

- **Task *sequences*, not task sets.** Episodes are ordered within a repo so that earlier tasks establish conventions, decisions, and corrections that later tasks can exploit (or repeat-fail).
- **Memory-on vs memory-off A/B.** Every sequence is run with Helix enabled and with a no-memory control. The benchmark's score *is the delta*, not the absolute.
- **Repeat-mistake rate.** Did the agent re-make a mistake the human/agent already corrected in an earlier session (e.g., wrong import style, deprecated API, ignored ADR)?
- **Convention adherence.** After a convention is established once (naming, error-handling pattern, test layout), is it followed in later tasks without being re-specified in the prompt?
- **Decision recall.** Are prior architectural decisions (the project's own ADRs) respected instead of relitigated?
- **Token cost of carryover.** Memory must reduce total tokens-to-solve across the sequence versus re-deriving context every task (ties to §3 tokens-per-retrieval).

The scoring axes mirror LongMemEval where they transfer (extraction, temporal/decision ordering, knowledge updates when a convention *changes* mid-sequence, abstention when a "remembered" convention does not actually apply). Publishing this is both an evaluation asset and a positioning asset: it is the eval that does not exist.

---

## 3. The internal eval harness

External benchmarks gate *positioning*; the internal harness gates *releases*. It runs in CI (§4) and produces the results table (§5). It has two layers — **retrieval quality** (did we surface the right memories?) and **end-task quality** (did surfacing them make the agent right?) — plus the hard-mode suites that distinguish a memory layer from a glorified cache.

### 3.1 Retrieval quality of surfaced memories

Against labeled `(query, gold-memories)` sets, we score the ranked list of memories Helix surfaces:

| Metric | Measures | Why it matters |
|---|---|---|
| **precision@k** | fraction of surfaced memories that are relevant | poisoning the prompt with junk costs tokens and accuracy |
| **recall@k** | fraction of gold memories surfaced in top-k | a missed memory = a repeated mistake |
| **MRR** | rank of the first relevant memory | agents read top-down; position matters |
| **nDCG** | graded relevance, position-discounted | the realistic "some memories matter more" case |

### 3.2 End-task correctness (LLM-as-judge + human audit)

Retrieval metrics are necessary but not sufficient — the only thing that ultimately matters is whether the downstream task came out right. We score end-task correctness with **LLM-as-judge**, explicitly acknowledging that **judges are noisy**: every judged run is calibrated against a **human-audited subset**, and we report judge–human agreement alongside the score. If judge/human agreement drops, the judge prompt is suspect, not the system under test.

### 3.3 Contradiction & knowledge-update handling

We seed timelines where a fact **changes** over time (e.g., "the project switched from REST to gRPC", "the lint rule was relaxed"). Scoring checks two things: (a) does retrieval return the **current** value, not a stale one, and (b) does the system **detect and surface the contradiction** rather than silently serving both. This is the LongMemEval "knowledge updates" capability, run on Helix's own store.

### 3.4 Edit/forget cascade correctness (incl. derived embeddings)

A delete is only real if everything *derived* from the record also disappears. The forget suite issues an erase and then verifies, via the **provenance cascade** (see [Consolidation](CONSOLIDATION.md)), that the source record **and** its derived embeddings, summaries, and consolidated abstractions are gone. We measure:

- **Residual leakage:** can any derived artifact still surface the forgotten fact? (Target: zero.)
- **Cascade latency:** wall-clock to fully propagate the deletion.

This is the suite that catches the classic memory-system bug: the row is deleted but the embedding/summary still answers the query.

### 3.5 Abstention / false-positive recall

Tied directly to poisoning resistance (§3.7). We measure **false-positive recall**: when the answer is genuinely *not* in memory, does Helix abstain, or does it confidently surface a plausible-but-wrong memory? High false-positive recall is how a memory layer becomes a hallucination amplifier.

### 3.6 Latency & tokens-per-retrieval (must BEAT full-context)

| Metric | Target |
|---|---|
| **Retrieval latency p50 / p95** | tracked per release; regressions gate |
| **Tokens-per-retrieval** | must be **strictly less** than the full-context baseline |

The token budget is non-negotiable and is the one number we inherit from the LoCoMo wars: Mem0's **~1.8K tokens vs ~26K full-context** is the *yardstick*. If Helix surfaces memory that costs more tokens than just pasting the relevant context would, the memory layer is a net negative. "Memory should SAVE tokens" is an acceptance criterion, not an aspiration.

### 3.7 Adversarial poisoning suite (security)

Memory is a write-back attack surface: anything ingested can resurface later, with authority, in a future session. The poisoning suite ingests a labeled set of **adversarial / poisoned inputs** (prompt-injection-laden commits, malicious "conventions", fake decisions) and measures:

- **Reach:** how many poisoned items pass ingestion filtering into **durable** memory?
- **Fire rate:** of those, how many actually **surface later** and influence a downstream task?

Both are tracked over time; a regression here is a security regression, not a quality nit.

---

## 4. Methodology

The harness is only trustworthy if its inputs are labeled, its timelines are deterministic, and it runs automatically on every change — including in the configuration most users will actually run.

- **Labeled `(query, gold-memories)` sets.** Retrieval metrics (§3.1) require human-labeled gold sets per scenario. These are versioned alongside the code so a metric movement is attributable to a code change, not a silent dataset change.
- **Seeded, changing-fact timelines.** Knowledge-update and contradiction tests (§3.3) use deterministic seeds so that "the fact changed at session 4" is reproducible across runs and machines.
- **Regression gating in CI.** Each suite has thresholds; a release that regresses precision@k/recall@k, end-task correctness, p95 latency, tokens-per-retrieval, forget-cascade leakage, abstention, or poisoning reach/fire **fails the build**. Benchmarks that don't gate CI rot.
- **The $0 / offline config is tested as first-class.** Helix's default is local-first, $0, fully offline (local embeddings + local store). That configuration — not a hosted/premium variant — is the one the harness runs against by default. We never let the free/offline path silently degrade because the "real" tests ran against a paid backend.
- **Judge calibration.** LLM-as-judge runs always carry a human-audited subset and report agreement (§3.2).

---

## 5. Results-tracking table template

One row per release, committed alongside the tag. Numbers are illustrative placeholders; `Δ vs full-ctx` and the memory-on/off delta are the load-bearing columns.

| Date | Helix ver | Suite | precision@k | recall@k | MRR | nDCG | End-task (judge) | Judge↔human | Knowledge-update acc | Forget leakage | Abstention (FP-recall) | p50 / p95 (ms) | Tokens/retrieval | Δ tokens vs full-ctx | Poison reach / fire | Gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-06-18 | 0.1.0 | LongMemEval_S | — | — | — | — | — | — | — | 0 | — | — / — | — | — | — / — | ☐ |
| 2026-06-18 | 0.1.0 | HelixCodeMem | — | — | — | — | — | — | — | 0 | — | — / — | — | — | — / — | ☐ |
| 2026-06-18 | 0.1.0 | $0/offline | — | — | — | — | — | — | — | 0 | — | — / — | — | — | — / — | ☐ |

---

## 6. Opinionated decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **LongMemEval is primary; LoCoMo is legacy sanity only** | LoCoMo fits in context, lacks knowledge-update Qs, and a full-context baseline beats memory systems on it (ADR-027). |
| 2 | **Never cite vendor LoCoMo numbers — including ours** | The same benchmark yields 58–84% depending on who scores; it's a brawl, not a measurement. |
| 3 | **Keep the ~1.8K vs 26K token yardstick** | Discard LoCoMo's ranking but keep its one durable number: memory must beat full-context on tokens. |
| 4 | **Define & publish HelixCodeMem** | Coding benchmarks are stateless by construction; the cross-task-memory eval simply doesn't exist — so we build it. |
| 5 | **Score the memory-on/off *delta*, not absolute solve rate** | The value of memory is the carryover; absolute solve rate hides it. |
| 6 | **Tokens-per-retrieval beating full-context is an acceptance gate** | A memory layer that costs more tokens than pasting context is a net negative — fail the build. |
| 7 | **Forget = zero residual leakage, including derived embeddings** | A delete that leaves a live embedding is a privacy and correctness bug; provenance cascade must be verified, not assumed. |
| 8 | **Abstention/false-positive recall is a first-class metric** | Confidently surfacing a wrong memory turns a memory layer into a hallucination amplifier. |
| 9 | **LLM-as-judge is always backed by a human-audited subset** | Judges are noisy; report judge↔human agreement or the score is uninterpretable. |
| 10 | **The $0/offline config is the default test target** | If the free/local path isn't the one CI gates, it will silently rot — and that's the path most users run. |
| 11 | **Adversarial poisoning (reach + fire) is a CI security gate** | Memory is a write-back attack surface; poisoned ingestion that resurfaces later is a vulnerability, not a quality nit. |

---

## Sources

- Zep, *"Lies, Damn Lies, and Statistics: Is Mem0 Really SOTA in Agent Memory?"* (LoCoMo teardown; full-context baseline ~73% J; ~16–26K-token convos; data-quality errors) — https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/
- Mem0 paper (LoCoMo ~66.9% LLM-judge, 91% lower p95, ~90% token savings, ~1.8K vs 26K tokens) — https://arxiv.org/abs/2504.19413
- Mem0 research hub — https://mem0.ai/research
- Zep ↔ Mem0 scoring dispute (84% → 58.44% corrected) — https://github.com/getzep/zep-papers/issues/5
- LongMemEval (ICLR 2025): 500 Qs; _S ~115K / _M ~1.5M tokens; extraction, multi-session, temporal, knowledge-updates, abstention — https://arxiv.org/abs/2410.10813
- Mem0, *"AI Memory Benchmarks in 2026"* (MemBench, BEAM; operation coverage) — https://mem0.ai/blog/ai-memory-benchmarks-in-2026
- Coding benchmarks treat tasks as independent episodes (no cross-task memory) — https://arxiv.org/html/2602.08316v3 · https://arxiv.org/pdf/2507.00014 · https://arxiv.org/pdf/2512.13564
