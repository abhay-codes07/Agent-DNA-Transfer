# Helix — Retrieval Pipeline

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [TSD](TSD.md) · [Memory Model](MEMORY_MODEL.md) · [Consolidation](CONSOLIDATION.md) · [Cost](COST_OPTIMIZATION.md) · [Decisions](../DECISIONS.md)

---

## 1. Overview & Latency Budget

Retrieval is the hot path. Every other Helix subsystem (ingest, [consolidation](CONSOLIDATION.md), graph maintenance) can be slow, async, and batched. Retrieval cannot. A coding agent calls `recall()` synchronously inside its reasoning loop, often several times per turn, and the latency stacks directly onto the user-visible response time.

The design therefore inverts the usual RAG cost model: **all expensive work — LLM expansion, summarization, graph construction, embedding — is pushed to ingest time. The query path does pure CPU vector math, lexical lookup, and graph traversal. No LLM call ever touches the query hot path in the default tier** (ADR-016).

**Hard constraints (honored throughout this document):**

| Constraint | Target | Why |
|---|---|---|
| Latency | **p95 < 150 ms** | Synchronous agent loop; multiple recalls per turn |
| Compute | **CPU only** | Local-first; no GPU assumed |
| Cost | **$0 default** | No paid API on query path |
| LLM on query path | **None** | Pushed to ingest (doc2query, summaries, KG) |
| Scale | **10⁵–10⁶ typed items** | Personal/project memory, not web-scale |

### Latency budget (p95, single recall, ~10⁶ items)

```
┌──────────────────────────────────────────────────────────────┐
│ TOTAL BUDGET: 150 ms (p95)                                     │
├──────────────────────────────────────────────────────────────┤
│ Stage                                  Budget   Cumulative     │
│ ─────────────────────────────────────  ──────   ──────────    │
│ 1. Query embed (int8, 384d)              8 ms      8 ms        │
│ 2. Scope / route (metadata filter)       3 ms     11 ms        │
│ 3a. Dense ANN top-100                    25 ms     36 ms       │
│ 3b. BM25 top-100 (parallel w/ 3a)       (15 ms)    36 ms       │
│ 4. RRF fuse (k=60)                        2 ms     38 ms       │
│ 5. Graph expansion (PPR / bounded BFS)   30 ms     68 ms       │
│ 6. Multi-signal ranking                   8 ms     76 ms       │
│ 7. MMR dedup / diversity                 10 ms     86 ms       │
│ 8. Token-budgeted packing                 6 ms     92 ms       │
│ ─────────────────────────────────────  ──────   ──────────    │
│ Headroom for GC / cold cache / I/O      ~58 ms    150 ms       │
└──────────────────────────────────────────────────────────────┘
```

The budget leaves ~40% headroom precisely because the killers — cross-encoder reranking and query-time LLM expansion — are **excluded from the default tier** and only available in opt-in tiers (§6, §7). A top-100 CPU cross-encoder rerank alone is 88–257 s, roughly **600–1700× the entire budget** ([Speed Showdown](https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077)); it is structurally impossible at p95<150ms and is never default.

---

## 2. The Default Pipeline

```
                          query string
                               │
            ┌──────────────────▼───────────────────┐
            │  1. QUERY EMBED  (bge-small int8 384d)│
            └──────────────────┬───────────────────┘
                               │
            ┌──────────────────▼───────────────────┐
            │  2. SCOPE / ROUTE                     │
            │  embedding router → {skip? · type ·  │
            │  project · time window · ACL}         │
            └──────────────────┬───────────────────┘
                               │   (skip-retrieval → empty set)
            ┌──────────────────▼───────────────────┐
            │  3. HYBRID RETRIEVE  (parallel)       │
            │  ┌───────────┐      ┌──────────────┐  │
            │  │ DENSE ANN │      │  BM25 / sparse│ │
            │  │ top-100   │      │  top-100      │  │
            │  └─────┬─────┘      └──────┬───────┘  │
            └────────┼───────────────────┼──────────┘
                     └─────────┬─────────┘
            ┌──────────────────▼───────────────────┐
            │  4. RRF FUSE  k=60  → ranked top-100  │
            └──────────────────┬───────────────────┘
                               │  (seed set)
            ┌──────────────────▼───────────────────┐
            │  5. GRAPH EXPANSION                    │
            │  Personalized PageRank over typed KG  │
            │  (HippoRAG-style) OR bounded 1–2 hop  │
            │  → adds multi-hop neighbors           │
            └──────────────────┬───────────────────┘
                               │  (~120–160 candidates)
            ┌──────────────────▼───────────────────┐
            │  6. MULTI-SIGNAL RANKING              │
            │  sim · recency · salience · conf ·    │
            │  graph-proximity  (weights per type)  │
            └──────────────────┬───────────────────┘
                               │
            ┌──────────────────▼───────────────────┐
            │  7. MMR DEDUP / DIVERSITY  λ=0.5      │
            │  (MinHash-LSH ~0.8 pre-dedup)         │
            └──────────────────┬───────────────────┘
                               │
            ┌──────────────────▼───────────────────┐
            │  8. TOKEN-BUDGETED PACKING            │
            │  lost-in-the-middle ordering          │
            └──────────────────┬───────────────────┘
                               │
                       ranked memory bundle
```

### Stage 1 — Query embed
The query is embedded once with the **same model used at ingest** (default `bge-small-en-v1.5`, 384d, int8; §6). int8 query embedding keeps this under ~8 ms on CPU. The full-precision query vector is retained in memory for the optional int8/binary **rescore** pass (§6) so we never pay accuracy loss on the asymmetric query side.

### Stage 2 — Scope / route
A cheap **embedding router** (~10× cheaper than LLM routing: 50–200 ms LLM vs sub-10 ms here) classifies the query against precomputed centroids to decide ([router cost](https://arxiv.org/abs/2310.11511)):
- **skip-retrieval** — Self-RAG-style; if the query needs no memory (e.g. pure arithmetic, "format this JSON"), return empty and save the whole pipeline ([Self-RAG](https://arxiv.org/abs/2310.11511)).
- **scope filters** — memory type(s), project, time window, ACL — applied as pre-filters on the ANN index so dense/BM25 only search the relevant partition.

### Stage 3 — Hybrid retrieve (dense + BM25), top-100 each
Dense ANN and BM25 run **in parallel**. Both are mandatory, not optional:
- **Dense** captures semantic paraphrase. DPR beats BM25 78.4% vs 59.1% top-20 on NQ ([DPR](https://arxiv.org/abs/2004.04906)).
- **BM25 is non-negotiable for personal/code memory.** Dense retrievers degrade out-of-domain while BM25 generalizes ([BEIR](https://arxiv.org/abs/2104.08663)), and personal memory is saturated with **proper nouns, file paths, identifiers, and verbatim error strings** that demand exact lexical match. SPLADE is an optional sparse-semantic upgrade ([SPLADE](https://opensearch.org/blog/improving-document-retrieval-with-sparse-semantic-encoders/)).

### Stage 4 — RRF fuse, k=60
Fuse the two ranked lists with **Reciprocal Rank Fusion**:

```
score(d) = Σ  1 / (k + rank_i(d))         k = 60
          i∈{dense, bm25}
```

RRF uses **ranks only**, sidestepping the fragility of normalizing two incomparable score distributions ([RRF explained](https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it)). `k=60` is the original Cormack SIGIR 2009 value ([Cormack RRF](https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf)) and matches Elasticsearch's `rank_constant=60`. **Implementation note:** Qdrant uses a zero-based `k=2` convention — always validate the rank-base per engine before assuming 60 (ADR-018).

### Stage 5 — Graph expansion
The RRF top-100 becomes the **seed set** for a single graph step over Helix's typed knowledge graph (built entirely at ingest). Two modes:
- **Personalized PageRank (default, HippoRAG-style)** — run PPR with the seed set as the personalization vector; this performs single-step multi-hop association in one classic, cheap CPU algorithm ([HippoRAG](https://arxiv.org/abs/2405.14831)). HippoRAG2 lifts 2Wiki Recall@5 from 76.5→90.4 ([HippoRAG2](https://arxiv.org/abs/2502.14802)).
- **Bounded traversal (fallback)** — for very large graphs or tight budgets, a 1–2 hop BFS capped at N neighbors per seed.

We explicitly **reject Microsoft GraphRAG** for the default path: its per-chunk + community-summary LLM indexing is ruinously expensive and global search issues ~40K-token prompts ([GraphRAG](https://arxiv.org/abs/2404.16130)); even LazyGraphRAG only cuts *indexing* cost ([LazyGraphRAG](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)). The whole point of HippoRAG-PPR is that **all LLM cost lives at ingest**, and the query is pure linear algebra. LightRAG (<100 tokens/query, incremental insert; [LightRAG](https://arxiv.org/abs/2410.05779)) and Graphiti (bi-temporal invalidation, ~300 ms P95; [Graphiti](https://arxiv.org/abs/2501.13956)) inform the ingest-side graph design — see [Memory Model](MEMORY_MODEL.md).

### Stage 6 — Multi-signal ranking
The fused + expanded candidate pool (~120–160 items) is scored by the blended formula in §3.

### Stage 7 — MMR dedup / diversity
Maximal Marginal Relevance removes near-duplicates and diversifies (§8).

### Stage 8 — Token-budgeted packing
Pack to the caller's token budget using lost-in-the-middle ordering (§8).

---

## 3. The Ranking Formula

Each signal is **min-max normalized within the candidate pool** to [0,1], then linearly combined. Normalize-then-blend is the standard, robust approach used by Mem0, which fuses vector + BM25 + entity signals after normalization ([Mem0](https://arxiv.org/html/2504.19413v1)).

```
score(d, q) =  w_sim   · sim(d, q)            // cosine, normalized
             + w_rec   · recency(d)           // exp decay from LAST ACCESS
             + w_sal   · salience(d)           // importance, set at ingest
             + w_conf  · confidence(d)         // source/verification trust
             + w_graph · graphprox(d, q)       // PPR mass / inverse hop dist
```

| Signal | Source | Notes |
|---|---|---|
| `sim` | cosine(query, doc) | The relevance backbone. From RRF-fused rank → score. |
| `recency` | `exp(-λ · Δt)` | **Decays from last *access*, not creation** ([LangChain TimeWeighted](https://python.langchain.com/v0.2/docs/how_to/time_weighted_vectorstore/)). Generative Agents use 0.995/hr ([Generative Agents](https://ar5iv.labs.arxiv.org/html/2304.03442)). |
| `salience` | importance score, ingest-time | Generative Agents use an LLM 1–10 importance; Helix computes it **at ingest** so the query path stays LLM-free. |
| `confidence` | source trust / verification | E.g. a user-confirmed decision > a speculative inference. |
| `graphprox` | PPR mass or 1/hop-distance | Rewards items pulled in by Stage 5 association. |

**Weights are tunable per memory type.** The generative-agents baseline sets recency = importance = relevance = 1 ([Generative Agents](https://ar5iv.labs.arxiv.org/html/2304.03442)); Helix generalizes this so each type can rebalance:

| Memory type | sim | recency | salience | confidence | graph | Rationale |
|---|---|---|---|---|---|---|
| **Episodic** (events, sessions) | 0.35 | 0.30 | 0.15 | 0.10 | 0.10 | Time matters most |
| **Semantic** (facts, entities) | 0.40 | 0.05 | 0.20 | 0.20 | 0.15 | Recency nearly irrelevant; trust matters |
| **Procedural** (how-tos, runbooks) | 0.45 | 0.10 | 0.25 | 0.15 | 0.05 | Relevance + importance dominate |
| **Decision/ADR** | 0.35 | 0.10 | 0.25 | 0.25 | 0.05 | Confidence weighted heavily |
| **Code/path refs** | 0.50 | 0.15 | 0.10 | 0.10 | 0.15 | Exact relevance + graph links |

Defaults ship as config; types and weights are overridable. See [Memory Model](MEMORY_MODEL.md) for type definitions.

---

## 4. Embeddings (ADR-017)

All embeddings computed at **ingest** and stored quantized. The query path embeds once and compares against the quantized index, with optional full-precision rescore on a small top-k.

### Default tier ($0, CPU, fast)
**`bge-small-en-v1.5`** — 384d, 33M params, MTEB 62.17 — the best-in-class small model and the Helix default ([bge-small](https://huggingface.co/BAAI/bge-small-en-v1.5)). Stored **int8** (4× memory reduction, ~99.3% quality retained with rescore; [quantization](https://huggingface.co/blog/embedding-quantization)).

| Model | dim | params | MTEB | Tier |
|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | 22.7M | ~56 | (legacy/tiny) |
| **bge-small-en-v1.5** | **384** | **33M** | **62.17** | **DEFAULT** |
| gte-small | 384 | — | 61.36 | alt small |
| e5-small | 384 | — | 59.93 | alt small |
| nomic-embed-text-v1.5 | 768 | — | 62.28 | MRL, 8K ctx |
| bge-base-en-v1.5 | 768 | — | 63.55 | mid |
| mxbai-embed-large-v1 | 1024 | — | 64.68 | **upgrade** |
| arctic-embed-l-v2.0 | 1024 | — | (multilingual) | **upgrade** |

### Upgrade tier (higher quality, still CPU-feasible)
**`mxbai-embed-large-v1`** (1024d, MTEB 64.68; [mxbai](https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1)) or **`arctic-embed-l-v2.0`** (1024d, multilingual; [Arctic 2](https://www.snowflake.com/en/engineering-blog/snowflake-arctic-embed-2-multilingual/)), both **Matryoshka-trained (MRL)**. Use MRL truncation to claw back the cost of the larger model:
- **Matryoshka truncation** — arctic-m@256d retains ~99% quality; nomic@256d loses only 1.24 MTEB ([Arctic MRL](https://github.com/Snowflake-Labs/arctic-embed), [nomic MRL](https://www.nomic.ai/news/nomic-embed-matryoshka)). Store a truncated prefix for the ANN scan, full dim for rescore.
- **Binary quantization** — 32× memory reduction and up to **32× faster** search, ~96% quality retained with a rescore pass ([quantization](https://huggingface.co/blog/embedding-quantization)). This is what makes a 1024d model viable at 10⁶ items on CPU: binary ANN scan → int8/float rescore of top-k.

**Rule of thumb:** binary for the first-pass scan, int8/full for rescore. Never compare quantized vectors without a rescore stage on the survivors.

---

## 5. Optional High-Quality Rerank Tier

Reranking is **off by default** because a naïve top-100 CPU cross-encoder is 88 s (bge-base) to 257 s (bge-v2-m3), 65–195× slower than GPU ([Speed Showdown](https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077)) — impossible at 150 ms. Two escapes make reranking feasible **on CPU** when the user opts in:

| Approach | Mechanism | CPU feasibility | Quality |
|---|---|---|---|
| **answerai-colbert-small-v1** | Late interaction (token-level), 33M | Marketed for **ms-scale CPU search over 100Ks of docs** ([ColBERT-small](https://www.answer.ai/posts/2024-08-13-small-but-mighty-colbert.html)); PLAID = 45× faster ColBERT on CPU ([PLAID](https://arxiv.org/abs/2205.09707)) | BEIR 53.79 |
| **int8 ONNX cross-encoder, top-20–30 only** | Quantized cross-encoder over a *tiny* survivor set | Feasible only if k ≤ 20–30 ([CE efficiency](https://sbert.net/docs/cross_encoder/usage/efficiency.html)) | High |

For reference, full cross-encoders score BEIR 53.94 (bge-reranker-v2-m3, 0.6B; [bge-rerank](https://huggingface.co/BAAI/bge-reranker-v2-m3)) and 57.49 (mxbai-rerank-large-v2; [mxbai-rerank](https://www.mixedbread.com/blog/mxbai-rerank-v2)) — excellent but GPU/cloud territory.

**Helix rule:** the only CPU-default-tier rerank option is **ColBERT late interaction**. The int8 ONNX cross-encoder is allowed **only on the top-20–30**, and any heavier reranker is pushed to the async/cloud tier (see [Cost](COST_OPTIMIZATION.md)).

---

## 6. Query Understanding

The dividing line is **index-time vs query-time**. Index-time expansion is latency-safe and $0-on-query; query-time LLM expansion violates the no-LLM-on-hot-path constraint.

| Technique | When | Effect | Verdict |
|---|---|---|---|
| **doc2query / docTTTTTquery** | **Ingest** | Recall@1000 85.3→89.3 at **~0 query cost** ([docTTTTTquery](https://cs.uwaterloo.ca/~jimmylin/publications/Nogueira_Lin_2019_docTTTTTquery-v2.pdf)) | **DEFAULT** — generate expansion queries at ingest, index them |
| **Embedding router** | Query | ~10× cheaper than LLM routing (sub-10 ms vs 500–2000 ms) | **DEFAULT** — Stage 2 routing |
| **Skip-retrieval** | Query | Self-RAG: skip when no memory needed ([Self-RAG](https://arxiv.org/abs/2310.11511)) | **DEFAULT** — Stage 2 |
| **HyDE** | Query | TREC DL19 61.3 vs 44.5, but loses to in-domain fine-tuning and adds +25–60% latency ([HyDE](https://arxiv.org/abs/2212.10496)) | **async/cloud tier only** |
| **Query2doc** | Query | +15 nDCG but **>2000 ms/query** ([Query2doc](https://arxiv.org/abs/2303.07678)) | **async/cloud tier only** |
| **Multi-query** | Query | Multiple LLM rewrites | **async/cloud tier only** |

**Net:** Helix gets the *recall* benefit of expansion via **doc2query at ingest** and the *routing* benefit via a cheap embedding router — both compatible with the budget. HyDE/Query2doc/multi-query are real wins but their latency (and LLM cost) confines them to the opt-in async/cloud tier described in [Cost](COST_OPTIMIZATION.md).

---

## 7. "Lost in the Middle" Packing

LLM accuracy on a relevant item drops from **75.8% → 53.8%** when that item sits in the middle of a long context ([Lost in the Middle](https://arxiv.org/abs/2307.03172)). Packing order is therefore a first-class ranking concern, not an afterthought.

```
  context window (token budget)
  ┌──────────────────────────────────────────────────────┐
  │ rank 1  │ rank 3 │ rank 5 │ … │ rank 6 │ rank 4 │ rank 2│
  │ (BEST)  │        │        │   │        │        │(2nd)  │
  └──────────────────────────────────────────────────────┘
     START  ◄─── most salient at BOTH ends ───►   END
                   (weakest items buried mid)
```

**Pre-packing dedup & diversity:**
1. **MinHash-LSH** near-dup removal at Jaccard threshold ~0.8 before any semantic merge.
2. **MMR** for diversity ([MMR](https://dl.acm.org/doi/10.1145/290941.291025)):

```
MMR = argmax [ λ · sim(d, q) − (1−λ) · max sim(d, dₛₑₗ) ]      λ = 0.5
       d∉S                          dₛₑₗ∈S
```

3. **Selective, budget-aware packing.** Don't pack everything. Mem0's selective approach yields +26% on LoCoMo, **91% lower p95, and ~90% fewer tokens** ([Mem0](https://arxiv.org/abs/2504.19413)). Fewer, better, well-ordered memories beat a stuffed context — this also directly serves [Cost](COST_OPTIMIZATION.md).

**Packing algorithm:** sort survivors by final score → place rank 1 at start, rank 2 at end, rank 3 next-to-start, rank 4 next-to-end, … (outside-in interleave) until the token budget is exhausted.

---

## 8. Twelve Opinionated Decisions

| # | Decision | Why | ADR |
|---|---|---|---|
| 1 | **No LLM on the query hot path, ever (default tier)** | Only way to hit p95<150ms at $0 | ADR-016 |
| 2 | **Hybrid dense + BM25 is mandatory, not optional** | Personal/code memory is full of paths, IDs, error strings; BM25 generalizes where dense degrades ([BEIR](https://arxiv.org/abs/2104.08663)) | ADR-016 |
| 3 | **RRF fusion, k=60, ranks-only** | Avoids score-normalization fragility ([RRF](https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it)); validate rank-base per engine | ADR-016 |
| 4 | **HippoRAG Personalized PageRank for graph hop** | Multi-hop in one cheap CPU pass; all LLM cost at ingest ([HippoRAG](https://arxiv.org/abs/2405.14831)) | ADR-016 |
| 5 | **Reject Microsoft GraphRAG for default** | Ruinous LLM indexing + 40K-token global queries ([GraphRAG](https://arxiv.org/abs/2404.16130)) | ADR-016 |
| 6 | **Cross-encoder reranking OFF by default** | 88–257 s on CPU for top-100 ([Speed Showdown](https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077)) | ADR-016 |
| 7 | **If rerank, use ColBERT late-interaction (CPU-ms) or int8 ONNX CE on top-20–30 only** | Only CPU-feasible rerank paths ([ColBERT-small](https://www.answer.ai/posts/2024-08-13-small-but-mighty-colbert.html), [CE efficiency](https://sbert.net/docs/cross_encoder/usage/efficiency.html)) | ADR-016 |
| 8 | **bge-small-en-v1.5 384d int8 as default embedder** | Best small MTEB (62.17); int8 = 4× mem, ~99.3% w/ rescore ([bge-small](https://huggingface.co/BAAI/bge-small-en-v1.5), [quant](https://huggingface.co/blog/embedding-quantization)) | ADR-017 |
| 9 | **Upgrade tier uses MRL truncation + binary quantization** | 32× mem, up to 32× faster, ~96% w/ rescore; makes 1024d viable at 10⁶ ([quant](https://huggingface.co/blog/embedding-quantization)) | ADR-017 |
| 10 | **Min-max normalize each signal, then linear blend; weights per type** | Robust fusion (Mem0); per-type recency/confidence balance ([Mem0](https://arxiv.org/html/2504.19413v1)) | ADR-016 |
| 11 | **Recency decays from LAST ACCESS** | Reinforces re-used memories ([LangChain](https://python.langchain.com/v0.2/docs/how_to/time_weighted_vectorstore/)) | ADR-016 |
| 12 | **Expansion at ingest (doc2query); HyDE/multi-query async-only** | doc2query +Recall at ~0 query cost; HyDE/Q2D cost >2000 ms ([docTTTTTquery](https://cs.uwaterloo.ca/~jimmylin/publications/Nogueira_Lin_2019_docTTTTTquery-v2.pdf), [Query2doc](https://arxiv.org/abs/2303.07678)) | ADR-016 |

---

## 9. Failure Modes

| Failure mode | Symptom | Mitigation |
|---|---|---|
| **Dense-only blind spot** | Misses exact path/ID/error-string queries | BM25 leg is mandatory (decision #2); never disable sparse |
| **Quantization drift** | Binary/int8 ANN returns wrong neighbors | Always rescore top-k with int8/full vectors before ranking |
| **RRF rank-base bug** | Silent quality loss from wrong `k` convention | Pin and test `k`; validate zero- vs one-based per engine (Qdrant k=2) |
| **Graph over-expansion** | PPR floods pool with weak neighbors, dilutes precision | Cap PPR mass / hop count; graphprox weight is small for semantic types |
| **Cold ANN cache** | First query of a session blows the budget | Warm index on session start; budget has ~58 ms headroom |
| **Lost-in-the-middle** | Relevant memory present but ignored by LLM | Outside-in packing; most-salient at both ends ([Lost in the Middle](https://arxiv.org/abs/2307.03172)) |
| **Over-packing** | High tokens, high latency, lower accuracy | Selective packing; cap memory count ([Mem0](https://arxiv.org/abs/2504.19413)) |
| **Recency runaway** | Stale-but-important facts buried by fresh noise | Per-type weights: low recency weight for semantic/decision types |
| **Skip-retrieval false negative** | Router skips when memory was needed | Conservative router threshold; cheap to retrieve, costly to miss |
| **Near-dup spam** | Same fact repeated N times wastes budget | MinHash-LSH ~0.8 pre-dedup + MMR diversity |
| **Reranker accidentally enabled on CPU** | p95 explodes to tens of seconds | Default off; guard rail caps CE input to top-20–30 |
| **Out-of-domain dense collapse** | Dense recall tanks on novel jargon | BM25 floor + ingest-time doc2query expansion |

---

## Sources

- DPR — Dense Passage Retrieval: https://arxiv.org/abs/2004.04906
- BEIR — heterogeneous IR benchmark: https://arxiv.org/abs/2104.08663
- SPLADE / sparse-semantic encoders: https://opensearch.org/blog/improving-document-retrieval-with-sparse-semantic-encoders/
- Cormack et al., Reciprocal Rank Fusion (SIGIR 2009): https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
- RRF — how it works / when to use: https://bigdataboutique.com/blog/reciprocal-rank-fusion-how-it-works-and-when-to-use-it
- Reranker speed showdown (CPU vs GPU): https://medium.com/@xiweizhou/speed-showdown-reranker-1f7987400077
- answer.ai — small-but-mighty ColBERT: https://www.answer.ai/posts/2024-08-13-small-but-mighty-colbert.html
- PLAID — efficient late interaction: https://arxiv.org/abs/2205.09707
- SBERT cross-encoder efficiency: https://sbert.net/docs/cross_encoder/usage/efficiency.html
- bge-reranker-v2-m3: https://huggingface.co/BAAI/bge-reranker-v2-m3
- mxbai-rerank-v2: https://www.mixedbread.com/blog/mxbai-rerank-v2
- Microsoft GraphRAG: https://arxiv.org/abs/2404.16130
- LazyGraphRAG: https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
- HippoRAG: https://arxiv.org/abs/2405.14831
- HippoRAG2: https://arxiv.org/abs/2502.14802
- LightRAG: https://arxiv.org/abs/2410.05779
- Graphiti: https://arxiv.org/abs/2501.13956
- HyDE: https://arxiv.org/abs/2212.10496
- Query2doc: https://arxiv.org/abs/2303.07678
- docTTTTTquery / doc2query: https://cs.uwaterloo.ca/~jimmylin/publications/Nogueira_Lin_2019_docTTTTTquery-v2.pdf
- Self-RAG: https://arxiv.org/abs/2310.11511
- bge-small-en-v1.5: https://huggingface.co/BAAI/bge-small-en-v1.5
- nomic-embed Matryoshka: https://www.nomic.ai/news/nomic-embed-matryoshka
- mxbai-embed-large-v1: https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1
- Snowflake Arctic Embed 2.0: https://www.snowflake.com/en/engineering-blog/snowflake-arctic-embed-2-multilingual/
- Arctic Embed (MRL): https://github.com/Snowflake-Labs/arctic-embed
- Embedding quantization (int8/binary): https://huggingface.co/blog/embedding-quantization
- Generative Agents (memory stream): https://ar5iv.labs.arxiv.org/html/2304.03442
- LangChain TimeWeightedVectorStore: https://python.langchain.com/v0.2/docs/how_to/time_weighted_vectorstore/
- Mem0: https://arxiv.org/abs/2504.19413 · https://arxiv.org/html/2504.19413v1
- Lost in the Middle: https://arxiv.org/abs/2307.03172
- MMR (Carbonell & Goldstein): https://dl.acm.org/doi/10.1145/290941.291025
