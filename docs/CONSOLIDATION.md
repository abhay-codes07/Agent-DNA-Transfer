# Helix — Memory Consolidation, Decay & Reflection

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [Memory Model](MEMORY_MODEL.md) · [Retrieval](RETRIEVAL.md) · [TSD](TSD.md) · [Security](SECURITY_MODEL.md) · [Decisions](../DECISIONS.md)

This document specifies what happens to a memory *after* it is first written: how Helix **consolidates** raw episodes into durable knowledge, how unused memories **decay**, how recalled memories are **reinforced**, and how the system **reflects** to synthesize higher-level insight. The initial write path (capture, embedding, taxonomy, storage) lives in [Memory Model](MEMORY_MODEL.md); read-time scoring lives in [Retrieval](RETRIEVAL.md). This is the lifecycle layer that sits between them and runs over time, much of it offline.

Helix is local-first, coding-agent-first, portable, and `$0`-by-default. Every mechanism below is designed to run on a developer laptop against a SQLite-class store with no mandatory cloud dependency, and to degrade gracefully when no LLM budget is available (decay is pure arithmetic; reflection and sleep-time consolidation are optional enrichers, not load-bearing).

---

## 1. Why a lifecycle at all

A naive agent memory is an append-only log that is embedded and retrieved by similarity. It rots. Three things go wrong, and all three are documented failure modes (see [§10](#10-failure-modes)): the log grows without bound so retrieval drowns in stale context (**context rot**); compression heuristics over-weight whatever is recent or loud (**catastrophic forgetting**, [Indium](https://www.indium.tech/blog/agent-memory-compression-failure-modes/)); and self-edits accumulate drift and injected falsehoods that **persist and self-reinforce** ([MemoryGraft](https://arxiv.org/html/2512.16962v1)).

Human memory solves the analogous problem with structure, not storage. It separates a fast, cheap, one-shot capture system from a slow, integrative system that distills structure across many episodes, and it lets unused traces fade while keeping useful ones through repeated recall. Helix copies that architecture deliberately. The biological mapping is not decoration — it is the design rationale, and each borrowed mechanism has a concrete computational form below.

---

## 2. Complementary Learning Systems: the two-stage architecture (ADR-012)

Systems consolidation in the brain moves memories from the **hippocampus** (fast, sparse, one-shot binding of an event to its time and place) to the **neocortex** (slow, distributed, integrating across many episodes to extract semantic structure), with offline replay — especially during sleep — driving the transfer ([systems consolidation review](https://pmc.ncbi.nlm.nih.gov/articles/PMC4526749/); [CLS, PNAS](https://www.pnas.org/doi/10.1073/pnas.2123432119); [McClelland-lineage CLS](https://pubmed.ncbi.nlm.nih.gov/22141588/)). The Complementary Learning Systems (CLS) framing is explicit: you *want* two systems with different speeds, because a single system fast enough to learn one-shot would catastrophically overwrite its own generalizations.

Helix adopts this as a **two-stage architecture** (ADR-012):

```
   ONLINE  (fast, cheap, "hippocampus")          OFFLINE (slow, generalizing, "neocortex")
  ┌───────────────────────────────────┐         ┌─────────────────────────────────────────┐
  │  Episodic capture                  │  replay │  Consolidation worker                    │
  │  • one-shot, append-only           │ ───────▶│  • clusters episodes                     │
  │  • cheap importance rating (1–10)  │         │  • distills semantic facts               │
  │  • bind to time / place / session  │         │  • distills procedural playbooks         │
  │  • NEVER blocks the agent          │         │  • builds reflection trees               │
  │  live context window = working mem │         │  • stronger/slower model, idle-time      │
  └───────────────────────────────────┘         └─────────────────────────────────────────┘
        system of record: episodic log                 derived, regenerable: semantic/procedural
```

**Stage 1 — online episodic capture (hippocampus).** Every salient observation is written immediately to the episodic event log as a discrete, timestamped record bound to its session and context. Writes are one-shot and must never block the agent's turn. The only model call on this path is a *cheap* importance rating ([§7](#7-importance-rating-at-write-time)). The live context window is treated as **working memory** in the Baddeley sense — it manipulates, it is never the system of record (see [Memory Model](MEMORY_MODEL.md)).

**Stage 2 — offline generalizing consolidation (neocortex).** A background worker replays clusters of recent episodes and distills them into **semantic facts** and **procedural playbooks**. The canonical example: ten separate episodes of *"had to activate the venv before running pytest"* collapse into one semantic rule — *"this project requires activating `.venv` before test commands"* — plus, if the steps are stereotyped, a procedural script. This is generalization across episodes, exactly what neocortex does. The derived memories are **regenerable**: if you delete every semantic fact, a re-run of consolidation over the surviving episodic log reconstructs them. The episodic log is the system of record; everything downstream is a cache with provenance.

This separation is what makes the rest of the document coherent: decay rates differ by stage, reinforcement targets the derived layer, reflection runs in stage 2, and anti-poisoning gates the episodic→semantic boundary.

---

## 3. Consolidation triggers

Consolidation is expensive (LLM calls, possibly a larger model) so it is event-driven, not continuous. Two triggers fire it; either is sufficient.

| Trigger | Condition | Rationale |
|---|---|---|
| **Accumulated-importance threshold** | Running sum of importance scores of episodes since the last consolidation exceeds **150** | Borrowed directly from Stanford Generative Agents' reflection trigger ([Generative Agents](https://ar5iv.labs.arxiv.org/html/2304.03442)); yields ~2–3 consolidations/day under typical load, scaling with *significance* of activity rather than raw volume |
| **Session boundary** | Always, when an agent session ends (or on explicit `helix flush`) | Guarantees the episodic log never carries an unconsolidated session into the next; bounds worst-case context rot; gives a natural "sleep" point |

The importance-budget trigger is the load-balancer: a quiet session of trivial observations may never reach 150 and only consolidates at the boundary, while a dense debugging session crosses 150 mid-stream and consolidates early. The session-boundary trigger is the floor that guarantees forward progress. Pseudocode:

```
on_episode_write(e):
    log.append(e)
    budget += e.importance
    if budget >= 150:
        enqueue_consolidation(reason="importance_budget")
        budget = 0

on_session_end():
    enqueue_consolidation(reason="session_boundary")
    budget = 0
```

Enqueued jobs are drained by the sleep-time worker ([§8](#8-sleep-time-consolidation-agent)) during idle time, so the trigger firing never stalls the agent.

---

## 4. The decay model (ADR-014)

Memories that are never used should fade out of *default* retrieval. Helix models this on the Ebbinghaus forgetting curve, which is approximately exponential — roughly 42% of new material is lost within ~20 minutes and about two-thirds within a day if never revisited ([Ebbinghaus](https://memia.app/en/resources/blog/ebbinghaus-forgetting-curve)). The standard form is `R(t) = e^(−t/S)` where `S` is *stability*; the half-life of a trace is `S·ln2`, and successful recall increases `S` ([forgetting curve / stability](https://sesen.ai/forgetting-curve)).

Helix combines decay with importance into a single **salience** score:

```
   salience(m, now) = importance(m) · e^( −λ · Δt_last_access )

   where  Δt_last_access = now − m.last_access_time
          λ              = ln2 / half_life(m.type, m)
```

`importance(m)` is the cached 1–10 poignancy from write time ([§7](#7-importance-rating-at-write-time)). The exponential term is the decay factor: it equals 1.0 at the moment of access and halves every `half_life`. Note the clock is reset by *access*, not by *creation* — a frequently recalled memory effectively never decays, which is the whole point and the hook for reinforcement ([§5](#5-reinforcement-on-recall-sm-2-adr-014)).

### Per-type half-lives

Decay rate is a function of memory **type**, because episodes are perishable and skills are not:

| Type | Default half-life | λ = ln2/half\_life | Behavior |
|---|---|---|---|
| **Episodic** | ~7 days | ≈ 0.099 / day | Events are perishable; an un-recalled episode is near-floor within ~2–3 weeks. The raw event still exists on disk (archival, [§9](#9-forgetting-is-archival-not-deletion)); it just drops from default retrieval. |
| **Procedural** | ~90 days | ≈ 0.0077 / day | Skills and playbooks are sticky; a learned procedure survives months of disuse before fading. |
| **Semantic** | **non-decaying** (λ ≈ 0) until contradicted | ≈ 0 | A fact stays at full salience indefinitely. Facts don't expire with time — they expire when **contradicted** (see contradiction detection, [§10](#10-failure-modes) / [Security](SECURITY_MODEL.md)). |

Semantic non-decay is the payoff of consolidation: the perishable episodes that *grounded* a fact may all decay out of default retrieval, but the distilled fact they produced persists, because the cost of one-shot capture was paid by episodic memory and the durable generalization was paid by neocortex. This is precisely the CLS division of labor from [§2](#2-complementary-learning-systems-the-two-stage-architecture-adr-012).

Half-lives are defaults, not constants. Reinforcement grows a memory's *effective* half-life ([§5](#5-reinforcement-on-recall-sm-2-adr-014)), so a frequently-used episode can behave more like a procedure over time.

---

## 5. Reinforcement on recall: SM-2 (ADR-014)

Recall is a vote of confidence. When a memory is actually retrieved *and used*, Helix strengthens it, mirroring how successful retrieval raises stability on the forgetting curve. The mechanism is adapted from SuperMemo's **SM-2** algorithm, the spaced-repetition scheme behind Anki ([SuperMemo / SM-2](https://en.wikipedia.org/wiki/SuperMemo)).

Each reinforceable memory carries an **easiness factor** `EF` (default 2.5). On a successful recall event with quality `q` (0–5, where `q` is derived from whether the retrieved memory was used / led to a good outcome), update:

```
   EF' = EF + ( 0.1 − (5 − q) · ( 0.08 + (5 − q) · 0.02 ) )
   EF' = max(EF', 1.3)                      # clamp: EF never drops below 1.3
```

The clamp at **1.3** is load-bearing — it prevents a string of poor recalls from driving a memory's interval to collapse, which is the same protection SM-2 uses to stop "leeches" from thrashing.

On reinforcement Helix then does three things:

1. **Reset Δt.** Set `last_access_time = now`, so the decay clock restarts and the exponential factor returns to 1.0.
2. **Grow the effective half-life.** Multiply the memory's effective half-life by `EF'` (equivalently, divide λ by `EF'`):
   `half_life_eff ← half_life_eff · EF'`. SM-2's expanding interval schedule (`I(1)=1`, `I(2)=6`, `I(n)=round(I(n−1)·EF)` days) becomes a continuously growing half-life rather than a discrete review date — every successful recall pushes the next "fade" further out, super-linearly for repeatedly-useful memories.
3. **Persist** the new `EF`, `half_life_eff`, and `last_access_time`.

Net effect: a memory recalled and used many times asymptotes toward non-decaying, regardless of its type default; a memory never recalled rides its type's base half-life to the floor.

---

## 6. Three-factor retrieval scoring tie-in

Consolidation and decay exist to feed retrieval. Helix scores candidate memories at read time with the Generative Agents three-factor formula ([Generative Agents](https://ar5iv.labs.arxiv.org/html/2304.03442)), and the lifecycle machinery above is *what supplies two of the three factors*:

```
   score(m, query) = α_recency · recency(m)
                   + α_importance · importance(m)
                   + α_relevance · relevance(m, query)

   default α_recency = α_importance = α_relevance = 1   (all factors min-max normalized to [0,1])
```

- **recency(m)** — exponential decay since last access, `0.995` per hour in the original; in Helix this is the same `e^(−λΔt)` decay factor from [§4](#4-the-decay-model-adr-014), so reinforcement's Δt-reset directly boosts recency.
- **importance(m)** — the cached 1–10 poignancy from [§7](#7-importance-rating-at-write-time).
- **relevance(m, query)** — cosine similarity between the query embedding and the memory embedding.

The full read-time pipeline (normalization windows, candidate generation, MMR diversification, hybrid lexical+vector) is specified in [Retrieval](RETRIEVAL.md) and [TSD](TSD.md). The contract here: **salience drives what is eligible and recency-weighted; relevance is supplied by the query at read time.** Low-salience memories aren't deleted, they simply lose the recency and importance contributions and fall below the default cutoff.

---

## 7. Importance rating at write time

Every captured memory gets a single **importance / poignancy score from 1 to 10**, assigned by a cheap LLM call at write time, following Generative Agents' "rate the likely poignancy" prompt ([Generative Agents](https://ar5iv.labs.arxiv.org/html/2304.03442)) — 1 for mundane chatter ("listed the files in a directory"), 10 for pivotal events ("the user changed the project's database from Postgres to SQLite"). This score is the `importance(m)` term used by both salience ([§4](#4-the-decay-model-adr-014)) and retrieval ([§6](#6-three-factor-retrieval-scoring-tie-in)).

Constraints that keep it `$0`-friendly and non-blocking:
- **Cached.** The score is computed once and stored on the memory; it is never recomputed at read time.
- **Cheap model, online.** Importance rating uses the small/fast model, on the hippocampal path. It must not stall the agent's turn; if the budget is `$0`, fall back to a heuristic (length, presence of decisions/errors, entity density) and let the sleep-time worker upgrade scores later.
- **Distinct from confidence.** Importance is "how much should I weight this," not "how true is this." Truth is tracked separately as confidence + provenance ([§10](#10-failure-modes), [Security](SECURITY_MODEL.md)).

---

## 8. Reflection trees (ADR-015)

Consolidation distills facts; **reflection** synthesizes *insight*. When the importance-budget trigger ([§3](#3-consolidation-triggers)) fires, the worker runs the Generative Agents reflection procedure ([Generative Agents](https://ar5iv.labs.arxiv.org/html/2304.03442)):

1. Take the most important recent episodes.
2. Ask the model to generate the few most salient high-level **questions** about them.
3. Retrieve memories relevant to each question.
4. Synthesize **insights** that answer them, each citing the memories that grounded it.

The insights are stored as **first-class memories** (typically semantic), **linked back to their source memories**. Because insights can themselves be inputs to later reflection, the structure is a **tree**: leaves are raw observations, interior nodes are progressively higher-level abstractions.

```
        (insight)  "I work best in small, test-driven increments on this repo"
            ▲                         ▲
        (insight)                 (insight)
    "tests gate my PRs"     "I refactor after green, not before"
        ▲      ▲                  ▲        ▲
     (obs)   (obs)             (obs)    (obs)      ← leaves = episodic observations
```

Targets ~**2–3 reflections per day** under normal load, the same cadence the 150-budget produces in Generative Agents. Every node retains links to its supporting leaves — those links are what the integrity gate ([§10](#10-failure-modes)) validates and what makes a synthesized claim auditable rather than a free-floating assertion.

---

## 9. Sleep-time consolidation agent (ADR-015)

The offline stage runs as a **sleep-time consolidation agent**: a background worker that shares the primary agent's memory store and rewrites/derives memory asynchronously during **idle time**, using a **stronger but slower model** than the online path. This is the Letta "sleep-time compute" pattern — background agents that share the primary agent's memory and rewrite memory blocks asynchronously while the foreground agent is idle ([Letta blog](https://www.letta.com/blog/sleep-time-compute), [Letta docs](https://docs.letta.com/guides/agents/architectures/sleeptime/)).

| Property | Online (hippocampus) | Sleep-time (neocortex) |
|---|---|---|
| When | During the agent's turn | Idle time / session boundary / queued |
| Model | Small, fast, cheap | Larger, slower, more capable |
| Latency budget | Must not block the turn | Unbounded; can take seconds–minutes |
| Work | One-shot capture, cheap importance | Cluster, distill, reflect, contradiction-check, score upgrades |
| Blocking? | Never blocks foreground | Never blocks foreground |

The conceptual lineage also includes MemGPT's virtual-context paging — main vs. external context with function-call "page faults" to move memory in and out ([MemGPT](https://arxiv.org/abs/2310.08560)). Helix's working memory (the live context window) is the *main* context; the episodic/semantic/procedural stores are *external* context; consolidation and retrieval are the paging machinery. The sleep-time agent is, in effect, the process that decides what gets paged *out* and rewritten while no one is looking.

Because the foreground path needs none of this to function, sleep-time consolidation is fully optional under a `$0` budget — it just means weaker generalization and importance scores until compute is available.

---

## 10. Anti-poisoning & integrity guardrails (ADR-029)

A memory that can be written and later self-edited is an attack surface. Memory poisoning (e.g. **MemoryGraft**) injects a false memory that then **persists and self-reinforces** across sessions ([MemoryGraft](https://arxiv.org/html/2512.16962v1); [persistent memory poisoning](https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents/)). Reconstructive memory theory predicts the broader risk: schemas aid recall but *introduce distortion*, and stereotyped scripts can overwrite specifics ([Bartlett schema theory](https://www.academica-group.com/en/knowledge/bartletts-schematheory)). Helix's consolidation pipeline is therefore the *most* dangerous place to be sloppy, because it is exactly where one episode becomes a durable, generalized, self-reinforcing semantic fact.

Guardrails, all enforced at the episodic→semantic boundary (full spec in [Security](SECURITY_MODEL.md)):

- **Provenance + confidence on every memory.** No memory exists without a record of where it came from and how much we trust it. This is the metacognitive layer; it also explicitly records *gaps* ("I don't know X") rather than fabricating.
- **Validation gate — grounding requirement.** A consolidated/semantic fact must **cite ≥1 grounding episode**. A "fact" with no supporting episode in the log is rejected (or quarantined at low confidence). This makes consolidation strictly *derivative* of the episodic system of record and kills free-floating injected assertions.
- **Contradiction detection flags, never silently overwrites.** When a new fact conflicts with an existing one, Helix raises a flag for resolution and lowers confidence on both; it does not silently clobber. (This is also what "non-decaying until contradicted" in [§4](#4-the-decay-model-adr-014) hooks into — contradiction is the *only* thing that expires a semantic fact.)
- **Separate user-asserted vs. agent-ingested provenance.** A fact the *user* stated is trusted differently from a fact the *agent* inferred or ingested from a tool/web source. Provenance class is first-class metadata and gates how easily a memory may be promoted, reinforced, or used to overwrite.
- **Reflection inherits the gate.** Synthesized insights ([§8](#8-reflection-trees-adr-015)) must keep their links to supporting leaves; an insight whose grounding is deleted is demoted, not retained.

---

## 11. Forgetting is archival, not deletion

Helix is local-first, so disk is cheap and trust matters more than space. **Forgetting never deletes.** When a memory's salience falls below the retrieval floor, it is **dropped from default retrieval** but **stays on disk** and remains **searchable on demand** (explicit "deep recall" / full-text scan). Three reasons:

1. **Reconstructability.** The episodic log is the system of record; deleting it would make consolidated facts ungroundable and break the [§10](#10-anti-poisoning--integrity-guardrails-adr-029) validation gate.
2. **Reversibility of decay.** A faded memory can be reinforced ([§5](#5-reinforcement-on-recall-sm-2-adr-014)) back into default retrieval if it turns out to matter again; deletion is irreversible, decay is not.
3. **Auditability.** Security and provenance review need the full history, including memories that fell out of working use.

Below-floor memories are candidates for **consolidation** (roll several stale episodes into one semantic summary) — but the originals are archived, not erased. Hard deletion is reserved for explicit user action (`helix forget --hard`) and secrets redaction, both covered in [Security](SECURITY_MODEL.md).

---

## 12. Failure modes

These are the named risks the design above is built to resist; each maps to a specific mitigation.

| Failure mode | What it looks like | Mitigation in Helix |
|---|---|---|
| **Catastrophic forgetting** | Compression over-weights recent / high-salience memories and silently drops the rest ([Indium](https://www.indium.tech/blog/agent-memory-compression-failure-modes/)) | Archival-not-deletion ([§11](#11-forgetting-is-archival-not-deletion)); episodic log is system of record; consolidation summarizes rather than discards; reinforcement rescues important-but-old memories |
| **Hallucinated memories / semantic drift** | Self-edits accumulate falsehoods; facts drift from their evidence over successive rewrites | Grounding gate (≥1 source episode), provenance + confidence, contradiction flagging ([§10](#10-anti-poisoning--integrity-guardrails-adr-029)); derived layer is regenerable from the immutable episodic log |
| **Memory poisoning** | Injected false memory persists and self-reinforces across sessions ([MemoryGraft](https://arxiv.org/html/2512.16962v1)) | User-asserted vs. agent-ingested provenance split; validation gate on promotion; no silent overwrite; confidence decay on contradiction ([§10](#10-anti-poisoning--integrity-guardrails-adr-029)) |
| **Recency bias** | Newest memories dominate retrieval regardless of importance | Three-factor scoring with independent, equally-weighted importance and relevance terms ([§6](#6-three-factor-retrieval-scoring-tie-in)); importance cached from write time, not inferred from age |
| **Context rot** | Irrelevant accumulated context in the window degrades performance | Working memory is never the system of record; consolidation + salience floor keep default retrieval small; session-boundary trigger bounds unconsolidated backlog ([§3](#3-consolidation-triggers)) |

---

## 13. Opinionated decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Two-stage CLS architecture is mandatory**, not an optimization | One-shot + generalization in one system is catastrophic forgetting by construction (ADR-012) |
| D2 | **Episodic log is the only system of record**; semantic & procedural are regenerable caches | Lets us delete/rebuild derived memory safely and ground every fact |
| D3 | **Decay is `salience = importance · e^(−λΔt_last_access)`**, clock reset by *access* not creation | Frequently-used memories never fade; unused ones do — the desired behavior in one formula (ADR-014) |
| D4 | **Per-type half-lives**: episodic ~7d, procedural ~90d, semantic non-decaying-until-contradicted | Perishability differs by kind; facts expire on contradiction, not on a timer (ADR-014) |
| D5 | **Reinforcement via SM-2 with `EF ≥ 1.3` clamp**, growing effective half-life by `EF` | Proven spaced-repetition curve; clamp prevents thrash/leeches (ADR-014) |
| D6 | **Importance is a cached 1–10 LLM poignancy score**, computed once at write | Stable retrieval weight; no per-read cost; `$0` heuristic fallback (ADR-015) |
| D7 | **Consolidate at importance-sum > 150 OR at every session boundary** | Significance-scaled cadence with a guaranteed floor (ADR-012/015) |
| D8 | **Reflection produces first-class, source-linked insight trees** (~2–3/day) | Auditable abstraction; insights are memories, not throwaway summaries (ADR-015) |
| D9 | **Heavy work runs in a sleep-time agent**, stronger/slower model, idle-time, never blocks foreground | Buy quality with latency we have, not latency the user feels (ADR-015) |
| D10 | **Forgetting = archival, never deletion**; low-salience drops from default retrieval, stays searchable on disk | Local-first; decay must be reversible and auditable |
| D11 | **Every memory carries provenance + confidence; user-asserted ≠ agent-ingested** | Trust is per-source; gates promotion and overwrite (ADR-029) |
| D12 | **Consolidated facts must cite ≥1 grounding episode; contradictions flag, never silently overwrite** | Kills hallucinated/injected memories at the consolidation boundary (ADR-029) |

---

## Sources

- Declarative memory taxonomy — https://www.simplypsychology.org/declarative-memory.html
- Episodic / procedural / semantic memory — https://www.tutor2u.net/psychology/reference/episodic-procedural-and-semantic-memory
- Systems consolidation (hippocampus→neocortex) — https://pmc.ncbi.nlm.nih.gov/articles/PMC4526749/
- Complementary Learning Systems (PNAS) — https://www.pnas.org/doi/10.1073/pnas.2123432119
- Complementary Learning Systems (McClelland lineage) — https://pubmed.ncbi.nlm.nih.gov/22141588/
- Ebbinghaus forgetting curve — https://memia.app/en/resources/blog/ebbinghaus-forgetting-curve
- Forgetting curve & stability (recall raises S) — https://sesen.ai/forgetting-curve
- SuperMemo / SM-2 algorithm — https://en.wikipedia.org/wiki/SuperMemo
- Stanford Generative Agents (memory stream, reflection, three-factor retrieval) — https://ar5iv.labs.arxiv.org/html/2304.03442
- MemGPT (virtual context paging) — https://arxiv.org/abs/2310.08560
- Letta sleep-time compute (blog) — https://www.letta.com/blog/sleep-time-compute
- Letta sleep-time architecture (docs) — https://docs.letta.com/guides/agents/architectures/sleeptime/
- Bartlett schema & script theory — https://www.academica-group.com/en/knowledge/bartletts-schematheory
- MemoryGraft / persistent memory poisoning (paper) — https://arxiv.org/html/2512.16962v1
- Persistent memory poisoning in AI agents — https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents/
- Agent memory compression failure modes — https://www.indium.tech/blog/agent-memory-compression-failure-modes/
