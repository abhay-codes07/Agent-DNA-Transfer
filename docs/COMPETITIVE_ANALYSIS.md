# Helix — Competitive Analysis

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [PRD](PRD.md) · [Roadmap](../ROADMAP.md) · [Decisions](../DECISIONS.md)

> **What this document is.** A teardown of the AI-memory landscape as it stands mid-2026, scored against the six axes that define Helix's wedge. Star counts and pricing are point-in-time (mid-2026) and drift fast — treat them as directional, not authoritative. The thesis: every serious competitor optimizes for a *hosted, server-side, latest-truth-wins* memory service. Nobody ships a **local-first, coding-native, single-file portable, git-like mergeable, $0-default** memory layer. That gap is the entire reason Helix exists.

---

## 1. The market in one paragraph

There is no audited TAM for "AI memory" — every vendor estimate quietly bundles orchestration, RAG, and vector infrastructure, and the numbers don't reconcile (Mordor: $6.27B 2025 → $28.45B 2030; SkyQuest: → $69.13B 2033). The parent "AI agents" category is more defensible at ~$7.84B → $52.6B by 2030. But the qualitative trend is real and load-bearing: **AI amnesia is the bottleneck.** OpenAI shipped ChatGPT Memory GA in 2024 and expanded it April 2025; a16z's *Big Ideas 2026* explicitly names context/state as **the** enterprise-agent bottleneck (https://www.a16z.news/p/big-ideas-2026-part-1). Meanwhile **MCP** has become the de-facto standard (Anthropic Nov 2024, OpenAI Mar 2025, Google Apr 2025) — which means MCP is **table stakes, not differentiation**. Speaking MCP gets you in the room; it does not win the room.

---

## 2. Per-product teardowns

Each teardown below scores memory model, retrieval, storage, portability, license/stars, pricing, the single biggest strength, and **the gap Helix exploits**.

### 2.1 Mem0 / OpenMemory

| | |
|---|---|
| **Memory model** | LLM 2-phase: extract → `ADD`/`UPDATE`/`DELETE`/`NOOP`, latest-truth-wins. Discrete facts, **not** a graph. |
| **Retrieval** | Vector-first + BM25 / entity boosts. |
| **Storage** | Qdrant default + SQLite history. |
| **Portability** | OpenMemory MCP ran local via Docker but is **being sunset** for the self-host server; export is **managed-only**. |
| **License / stars** | Apache-2.0 · ~58.8k ⭐ (the category leader by adoption). |
| **Pricing** | Hobby $0 (10k) / Starter $19 / Growth $79 / Pro $249 / Ent. $24M total Series A, Basis Set, Oct 2025. |
| **Biggest strength** | Ubiquity and ease — the default pip-install answer to "give my agent memory." |
| **Gap Helix exploits** | Weak temporal reasoning (~49% LongMemEval vs Zep ~64%); lossy LLM extraction throws away source fidelity; **no portable signed artifact**, and export is gated behind the managed tier. Helix keeps the raw, owns the file, and signs it. |

URLs: https://github.com/mem0ai/mem0 · https://mem0.ai/pricing

### 2.2 Letta (MemGPT)

| | |
|---|---|
| **Memory model** | OS-paging tiers — `core` (self-editable, in-context) / `recall` / `archival`. The agent edits its **own** memory via tools. |
| **Retrieval** | Vector (`text-embedding-3-small`), **no graph**. |
| **Storage** | Postgres + pgvector / SQLite / TurboPuffer. |
| **Portability** | **Agent File `.af`** — open JSON of the *whole agent*, but **unsigned, unencrypted**, secrets not included. |
| **License / stars** | Apache-2.0 · ~23.4k ⭐. |
| **Pricing** | Self-host free; Cloud $20/mo + $0.10/agent + usage, BYOK. $10M seed, Felicis, Sept 2024, $70M post. |
| **Biggest strength** | Durable, self-managing agents + the ADE debugger for inspecting agent state. |
| **Gap Helix exploits** | **Framework lock-in** — Letta owns the agent loop, so memory comes bundled with their runtime. Python-only, costly context paging, no graph, no coding angle. The `.af` file is the right instinct executed weakly: unsigned plaintext JSON. Helix's signed + encrypted **`.dna`** leapfrogs it, and Helix is loop-agnostic (it's a memory layer, not an agent runtime). |

URLs: https://github.com/letta-ai/letta · https://docs.letta.com/guides/build-with-letta/pricing

### 2.3 Zep / Graphiti

| | |
|---|---|
| **Memory model** | Bi-temporal knowledge graph (valid time + transaction time; facts are **invalidated, not deleted**). Episode / entity / community tiers. |
| **Retrieval** | True hybrid: semantic + BM25 + graph BFS, with **no LLM at query time** (fast, deterministic, auditable). |
| **Storage** | FalkorDB / Neo4j / Neptune. |
| **Portability** | None — there is no portable artifact; you run a graph DB. |
| **License / stars** | Graphiti Apache-2.0 ~27.6k ⭐ · Zep ~4.7k ⭐. The OSS **Zep server is deprecated**; self-host = the Graphiti library. |
| **Pricing** | Graphiti free; Zep Cloud $0 → ~$104/mo cliff → ~$312 → Ent. ~$500K, YC W24. |
| **Biggest strength** | Best-in-class temporal accuracy + audit trail + fast retrieval (the no-LLM-at-query-time design is genuinely excellent). |
| **Gap Helix exploits** | You **must run a graph DB** — heavy, stateful, server-side. LLM-heavy ingestion. The turnkey self-host server is deprecated, pushing you to Cloud. **No portable artifact.** Helix steals the bi-temporal + no-LLM-at-query ideas without forcing a graph DB on a laptop. |

URLs: https://github.com/getzep/graphiti · https://www.getzep.com/pricing/

### 2.4 Cognee

| | |
|---|---|
| **Memory model** | ECL pipeline (Extract-Cognify-Load), graph + vectors; `memify` self-prunes. |
| **Retrieval** | Graph-vector hybrid, 14 search modes. |
| **Storage** | Kuzu + LanceDB + SQLite default (many backends supported). |
| **Portability** | Self-hostable, file-based + Cognee Cloud. |
| **License / stars** | Apache-2.0 · ~17.9k ⭐. |
| **Pricing** | $0 / Dev $35 / Team $200 / Ent. $7.5M seed, Pebblebed, Feb 2026. |
| **Biggest strength** | Ontology-grounded graph + vector — the most "knowledge-engineering-correct" of the bunch. |
| **Gap Helix exploits** | **Multi-DB operational complexity** (three+ stores to stand up), LLM-cost-heavy graph build, immature managed tier. Helix is a single signed file with zero infra to operate. |

URLs: https://github.com/topoteretes/cognee · https://www.cognee.ai/pricing

### 2.5 LangMem

| | |
|---|---|
| **Memory model** | Semantic / episodic / procedural (self-updating prompts); hot-path + background extraction. |
| **Retrieval** | Vector over a KV + embedding store. |
| **Storage** | InMemory / Postgres / Pinecone / Redis. |
| **License / stars** | MIT · ~1.5k ⭐. |
| **Pricing** | OSS free; LangSmith Plus $39/seat. |
| **Biggest strength** | Tri-type memory native to LangGraph. |
| **Gap Helix exploits** | ~60s p95 latency (batch-only), **LangChain coupling**, low traction. Coupled to one orchestration framework; Helix is framework-neutral and synchronous. |

URL: https://github.com/langchain-ai/langmem

### 2.6 Supermemory

| | |
|---|---|
| **Memory model** | Unified memory graph + a **Memory Router** drop-in (change one URL). |
| **Retrieval** | Hybrid vector + keyword + graph, sub-300ms (vendor claim: "10x Zep, 25x Mem0"). |
| **Storage** | Cloudflare + Postgres (cloud) + an embedded `./.supermemory` engine that runs offline with Ollama. |
| **License / stars** | MIT · ~27.2k ⭐. |
| **Pricing** | $0 ($5) / Pro $19 / Max $100 / Scale $399 / Ent. $2.6M seed, Oct 2025 (Susa, Browder, Jeff Dean angel). |
| **Biggest strength** | Raw speed + drop-in router (lowest integration friction in the category) + a genuinely free local self-host. |
| **Gap Helix exploits** | **No standard export**, self-host-at-scale needs the $399 tier, not coding-native, **no signed artifact**. The closest on "local + free" but it has no portable, verifiable memory object and no coding workflow. |

URLs: https://github.com/supermemoryai/supermemory · https://supermemory.ai/pricing/

### 2.7 Memobase

| | |
|---|---|
| **Memory model** | Structured per-user **profile** (schema attributes) + an event timeline; buffered batch extraction. |
| **Retrieval** | SQL profiles (<100ms) + vector events. **Not** a graph. |
| **Storage** | Postgres + Redis. |
| **License / stars** | Apache-2.0 · ~2.8k ⭐. |
| **Pricing** | Self-host free + cloud PAYG. |
| **Biggest strength** | Strong temporal numbers — **75.8% LoCoMo** vs Mem0 66.9%, with cheap SQL-fast profile reads. |
| **Gap Helix exploits** | **Rigid schema**, weak multi-hop reasoning, no graph, no export. Great if your memory fits a fixed profile shape; useless for open-ended coding context. |

URL: https://github.com/memodb-io/memobase

### 2.8 A-MEM *(feature source, not a competitor)*

| | |
|---|---|
| **Memory model** | Zettelkasten notes + **autonomous link generation** + **memory evolution** (new notes update old ones). |
| **Retrieval** | Vector + agentic linking. |
| **Storage** | ChromaDB. |
| **License / stars** | MIT · ~1.1k ⭐ (arXiv 2502.12110, Feb 2025). |
| **Biggest strength** | The most adaptive / self-organizing memory in the field. |
| **Gap Helix exploits** | Research-grade — **no infra, no sync, no auth**. We treat A-MEM as a **feature source**, not a rival: its self-evolving link generation is a capability to steal (see §4). |

URL: https://arxiv.org/abs/2502.12110

### 2.9 basic-memory *(closest philosophical rival)*

| | |
|---|---|
| **Memory model** | **Markdown-as-database** — frontmatter entities + observations + relations; Obsidian wikilinks form the graph. Humans **and** AI edit the same files. |
| **Retrieval** | SQLite FTS + FastEmbed vectors + graph traversal. |
| **Storage** | Plain Markdown → SQLite index; cloud Postgres + Tigris S3. |
| **Portability** | **Best portability in the category** — you own the Markdown; sync via Git or Syncthing; Obsidian-native; broad MCP support. |
| **License / stars** | **AGPL-3.0** · ~3.3k ⭐. |
| **Pricing** | Self-host free; cloud $15/mo. |
| **Biggest strength** | True file-ownership and human/AI shared editing — philosophically the closest to Helix. |
| **Gap Helix exploits** | File-indexing **scales poorly**; **AGPL-3.0 deters commercial embedding** (an agent vendor cannot ship it inside a closed product); **no encryption / signing**; not coding-specialized; everything is plaintext. Helix wins on a **signed + encrypted single artifact**, **coding-native** modeling, **git-like *semantic* merge** (not just file-level Git sync), and a **permissive license** an agent vendor can actually embed. |

URL: https://github.com/basicmachines-co/basic-memory

### 2.10 txtai *(architecture model for `.dna`)*

| | |
|---|---|
| **Memory model** | All-in-one embeddings database (vector + graph + SQL + keyword). |
| **Portability** | **Single compressed portable archive** via `save()` / `load()` — the literal model for the `.dna` artifact. |
| **License / stars** | Apache-2.0 · ~12.7k ⭐. |
| **Gap Helix exploits** | SQLite / Faiss core not built for distributed scale; **not framed as agent memory**. We borrow the single-archive portability pattern and wrap it with signing, encryption, and coding-native semantics. |

URL: https://github.com/neuml/txtai

### 2.11 Walrus + MemWal (Mysten / Sui)

| | |
|---|---|
| **Memory model** | Decentralized blob store (RedStuff erasure coding, ~4–5x replication; blobs are Sui objects). Base layer = **blob read only, no semantic search**. |
| **Retrieval** | MemWal SDK (May 2026) adds encrypted memory containers + semantic search + Sui access control on top. |
| **License / stars** | Apache-2.0 · ~375 ⭐ · WAL token. |
| **Biggest strength** | Cheap, verifiable, **content-addressed**, vendor-neutral, on-chain ownership (~450TB). |
| **Gap Helix exploits** | **Storage-only core**; MemWal is beta; the **blockchain conflicts directly with $0 + local-first** (a token requirement is a non-starter for a laptop-default dev tool). **Takeaway: adopt content-addressing + encryption + verifiability, drop the chain.** |

URL: https://github.com/MystenLabs/walrus

---

## 3. The 6-axis positioning table

Six axes define the wedge. The claim is simple and falsifiable: **no competitor checks all six.**

| Product | Local-first | Portable single-file | Coding-native | Git-like (semantic) merge | MCP | $0 default |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Helix** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Mem0 / OpenMemory | ⚠️ (sunsetting) | ❌ (export gated) | ❌ | ❌ | ✅ | ⚠️ (10k cap) |
| Letta (MemGPT) | ⚠️ | ⚠️ (`.af` unsigned) | ❌ | ❌ | ✅ | ✅ (self-host) |
| Zep / Graphiti | ❌ (graph DB) | ❌ | ❌ | ❌ | ✅ | ⚠️ (server deprecated) |
| Cognee | ⚠️ (multi-DB) | ❌ | ❌ | ❌ | ✅ | ✅ |
| LangMem | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ✅ |
| Supermemory | ✅ | ❌ | ❌ | ❌ | ✅ | ⚠️ ($399 at scale) |
| Memobase | ⚠️ | ❌ | ❌ | ❌ | ✅ | ✅ |
| A-MEM | ⚠️ | ❌ | ❌ | ❌ | ❌ | ✅ |
| basic-memory | ✅ | ⚠️ (plaintext MD) | ❌ | ⚠️ (file-level Git) | ✅ | ✅ |
| txtai | ✅ | ✅ (archive) | ❌ | ❌ | ❌ | ✅ |
| Walrus / MemWal | ❌ (chain) | ⚠️ (blob) | ❌ | ❌ | ❌ | ❌ (token) |

Legend: ✅ full · ⚠️ partial / conditional · ❌ none.

**Read-out.** basic-memory and Supermemory get closest on local-first + $0, but neither is coding-native, neither does *semantic* merge, and neither ships a signed/encrypted single artifact (basic-memory is plaintext under AGPL; Supermemory has no export). Letta's `.af` is the only true portable artifact among the leaders, and it's unsigned plaintext JSON bundled to a Python agent loop. **The all-six column is empty except for Helix.**

---

## 4. Helix's whitespace

The defensible whitespace is the **intersection of three things no competitor combines**:

1. **Coding-native memory.** Memory modeled around code work — files, symbols, decisions, repo context, agent task history — not generic "user facts." Every competitor models a chat user; none models a coding agent's working set.
2. **Git-like *semantic* merge.** Not file-level Git sync (basic-memory) and not latest-truth-wins overwrite (Mem0). A **three-way semantic merge** of memory: diff, conflict-detect, and reconcile memory the way you reconcile code. This is what makes the "review team memory like a PR" workflow possible (diff → approve → revert).
3. **Signed + encrypted single-file portability.** The **`.dna`** artifact: one file you own, that is content-addressed (à la Walrus, minus the chain), encrypted at rest, and **cryptographically signed** so its provenance is verifiable. Letta's `.af` is the closest prior art and it is unsigned, unencrypted, and loop-bound.

No competitor occupies this intersection. The leaders are racing toward hosted server-side memory-as-a-service; the whitespace is the local, coding, mergeable, portable corner they're all walking away from.

---

## 5. Ideas to steal

Good artists copy; this section is explicit about what to lift and from whom.

| Idea | From | What to take | What to drop |
|---|---|---|---|
| **Self-evolving links** | A-MEM | Autonomous link generation + memory evolution (new notes retroactively update old). | The research-grade ChromaDB-only plumbing; no infra/sync/auth. |
| **No-LLM-at-query-time + bi-temporal** | Zep / Graphiti | Deterministic, fast, auditable retrieval; facts invalidated (valid + transaction time) not deleted. | The mandatory graph DB and LLM-heavy ingestion. |
| **Content-addressing + encryption + verifiability** | Walrus / MemWal | Content-addressed, encrypted, signed, verifiable memory blobs. | **The blockchain** — a token requirement breaks $0 + local-first. |
| **Single portable archive** | txtai | `save()` / `load()` one-file archive pattern as the model for `.dna`. | The "embeddings DB, not agent memory" framing. |
| **File ownership + human/AI co-edit** | basic-memory | You own the artifact; humans and agents edit the same memory. | AGPL (un-embeddable), plaintext (no signing/encryption), file-indexing scale ceiling. |
| **Drop-in integration ergonomics** | Supermemory | One-line "Add to Cursor / Claude Code" install; near-zero integration friction. | Cloud-router dependency and the $399 self-host-at-scale gate. |

---

## 6. Bottom line

MCP is table stakes — every product here either has it or will. The category is consolidating around **hosted, server-side, latest-truth-wins** memory. Helix wins by refusing that frame: a **local-first, coding-native, semantically mergeable, signed + encrypted single-file ($0-default)** memory layer that an agent vendor can embed under a permissive license. The six-axis table has exactly one full row. That is the entire bet.

---

## Sources

- Mem0 / OpenMemory — https://github.com/mem0ai/mem0 · https://mem0.ai/pricing
- Letta (MemGPT) — https://github.com/letta-ai/letta · https://docs.letta.com/guides/build-with-letta/pricing
- Zep / Graphiti — https://github.com/getzep/graphiti · https://www.getzep.com/pricing/
- Cognee — https://github.com/topoteretes/cognee · https://www.cognee.ai/pricing
- LangMem — https://github.com/langchain-ai/langmem
- Supermemory — https://github.com/supermemoryai/supermemory · https://supermemory.ai/pricing/
- Memobase — https://github.com/memodb-io/memobase
- A-MEM — https://arxiv.org/abs/2502.12110
- basic-memory — https://github.com/basicmachines-co/basic-memory
- txtai — https://github.com/neuml/txtai
- Walrus / MemWal — https://github.com/MystenLabs/walrus
- MCP — https://www.anthropic.com/news/model-context-protocol
- a16z Big Ideas 2026 — https://www.a16z.news/p/big-ideas-2026-part-1

*Star counts and pricing are mid-2026 point-in-time snapshots and change frequently; re-verify before quoting externally.*
