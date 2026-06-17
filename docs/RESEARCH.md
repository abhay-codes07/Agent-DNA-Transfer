# Helix — Research Survey & Source of Decisions

**Status:** Living doc · **Last updated:** 2026-06-18 · **Related:** [Decisions](../DECISIONS.md) · [Competitive Analysis](COMPETITIVE_ANALYSIS.md) · [Retrieval](RETRIEVAL.md) · [Consolidation](CONSOLIDATION.md) · [Sync](SYNC.md) · [Privacy](PRIVACY_COMPLIANCE.md) · [Evaluation](EVALUATION.md)

This is the consolidated literature/landscape survey behind Helix's design. Wave-2 ADRs
(012–030) in [`DECISIONS.md`](../DECISIONS.md) each trace back to a finding here. It is
organized by research stream; every stream ends with the decisions it drove. Full per-topic
detail lives in the dedicated docs linked above.

> Method: seven parallel deep-research streams (June 2026) — competitive landscape, memory
> science, retrieval SOTA, storage/infra, crypto/sync/CRDT, MCP/integrations, privacy/eval/
> business — each producing a cited dossier. Caveats: star counts and pricing are mid-2026
> point-in-time; no audited "AI memory" TAM exists; some vendor latency/accuracy numbers are
> contested (see [Evaluation](EVALUATION.md)).

---

## 1. Competitive landscape → positioning

The category is real and funded, but **no incumbent occupies Helix's corner**. Across Mem0
(~58.8k★, $24M), Letta/MemGPT (~23.4k★, $10M seed), Zep/Graphiti (~27.6k★, temporal-graph
leader), Cognee (~17.9k★, $7.5M), Supermemory (~27.2k★), LangMem, Memobase, A-MEM (research),
**basic-memory** (~3.3k★, Markdown, AGPL — the closest philosophical rival), txtai, and
**Walrus/MemWal** (the decentralized inspiration), none combine all six of: local-first ·
portable single-file · coding-native · git-like *semantic* merge · MCP · $0-default.

Key takeaways that shaped Helix:
- **Own a signed+encrypted single-file artifact.** Letta's `.af` is unsigned JSON;
  basic-memory is plaintext Markdown; txtai's archive is unsigned. `.dna` is genuine whitespace.
- **Git-like *semantic* merge is the moat** (basic-memory only gets file-level Git on plaintext).
- **Be aggressively coding-native** — every competitor is general-purpose.
- **Steal:** A-MEM self-evolving links; Zep's no-LLM-at-query-time + bi-temporal model;
  Walrus's content-addressing + verifiability **minus the blockchain**.
- **Avoid:** the graph-DB ops trap (Zep/Cognee), LLM-heavy ingestion, the AGPL embedding-killer,
  and treating MCP as differentiation (it's table stakes).
> **Drove:** [ADR-001](../DECISIONS.md), [ADR-002](../DECISIONS.md), [ADR-008](../DECISIONS.md), [ADR-013](../DECISIONS.md), [ADR-028](../DECISIONS.md). Detail → [Competitive Analysis](COMPETITIVE_ANALYSIS.md), [Business](BUSINESS.md).

## 2. Memory science → the cognitive model

Human memory splits into **working** (the live context window — never the system of record),
and long-term **episodic / semantic / procedural**, with an entity-relationship graph as the
semantic backbone. The **Complementary Learning Systems** framework (fast hippocampal episodic
store training a slow neocortical semantic store via offline replay) maps directly onto a
two-stage write path. Decay follows the **Ebbinghaus** exponential curve; **SM-2** spaced
repetition gives a reinforcement formula. **Generative Agents** contribute the
recency×importance×relevance retrieval score, LLM importance rating, and **reflection trees**;
**MemGPT** contributes virtual-context paging; **Letta** contributes sleep-time compute.
Failure modes — poisoning, catastrophic forgetting, hallucinated memories, recency bias,
context rot — are designed against explicitly.
> **Drove:** [ADR-012](../DECISIONS.md), [ADR-014](../DECISIONS.md), [ADR-015](../DECISIONS.md), [ADR-029](../DECISIONS.md). Detail → [Memory Model](MEMORY_MODEL.md), [Consolidation](CONSOLIDATION.md).

## 3. Retrieval SOTA → the recall pipeline

The p95<150 ms / CPU / $0 budget forbids any LLM call on the query hot path and pushes all
"intelligence" to ingest. Winning recipe: **hybrid dense + BM25** (personal memory is full of
identifiers BM25 must catch), fused with **RRF (k=60)**, **graph expansion via Personalized
PageRank** (HippoRAG — not Microsoft GraphRAG, which is too LLM-costly), **MMR** for diversity,
and **token-budgeted packing** with the most-salient items at head and tail (to beat "lost in
the middle"). Default embeddings: **bge-small-en-v1.5** (384d, MTEB 62.17) int8-quantized;
upgrade tier mxbai/arctic with Matryoshka truncation + binary quantization. Reranking is
optional and CPU-bounded (late-interaction ColBERT-small or int8 cross-encoder on top-20–30).
> **Drove:** [ADR-016](../DECISIONS.md), [ADR-017](../DECISIONS.md). Detail → [Retrieval](RETRIEVAL.md).

## 4. Storage/infra → one SQLite file

Benchmarks confirm **sqlite-vec brute-force** is fast enough at 10⁵–10⁶ with int8/binary
quantization; **Kùzu was abandoned Oct 2025** (so the graph stays relational + recursive CTEs +
NetworkX); **DuckDB-VSS HNSW persistence is experimental** (corruption risk). The strand is one
SQLite file (vectors + graph + metadata, transactional via WAL; checkpoint + atomic-rename
before export). A `MemoryStore` interface gives a clean team-scale upgrade path (LanceDB →
pgvector → Qdrant). Embeddings run in-process via **fastembed ONNX**; no background server in
the default.
> **Drove:** [ADR-005](../DECISIONS.md) (confirmed), [ADR-018](../DECISIONS.md), [ADR-030](../DECISIONS.md). Detail → [System Architecture](SYSTEM_ARCHITECTURE.md), [Plugins](PLUGINS.md).

## 5. Crypto / sync / CRDT → the `.dna` artifact

`.dna` is encrypted with **XChaCha20-Poly1305 secretstream** (64 KiB chunks), keys derived via
**Argon2id**, integrity via a **BLAKE3 Merkle tree**, authenticity via an **Ed25519** signature
over the Merkle root — **independently verifiable offline, no blockchain** (we keep Walrus's
verifiability, drop the chain). Keys use **wrap-don't-encrypt** with OS keychain + passphrase +
recovery code + optional Shamir/hardware. Optional sync is **E2E, bring-your-own-storage**, with
**1Password-style two-secret derivation**. Merge = **Automerge-style CRDT** for convergence +
**git 3-way semantic merge** for contradictions, over a **bi-temporal**, content-addressed
(Prolly/Merkle, Dolt-style) store.
> **Drove:** [ADR-008](../DECISIONS.md) (refined), [ADR-013](../DECISIONS.md), [ADR-019](../DECISIONS.md), [ADR-020](../DECISIONS.md), [ADR-021](../DECISIONS.md), [ADR-022](../DECISIONS.md). Detail → [.dna Format](DNA_FORMAT.md), [Sync](SYNC.md), [Security](SECURITY_MODEL.md).

## 6. MCP / integrations → the agent interface

MCP is now the de-facto standard (Anthropic Nov 2024 → OpenAI/Google/Microsoft 2025), so being
MCP-native is table stakes, not differentiation. Architecture: **one local daemon (Streamable
HTTP on 127.0.0.1) + a thin stdio shim**, leading with **Tools** (~5) plus **Resources**, every
result **token-budgeted** (a gap no competitor fills), **human-readable IDs**, idempotent writes,
`isError`-in-result handling, stable names. Security: treat memory as the **private-data leg of
the lethal trifecta**; treat returned memory as untrusted; static audited tool descriptions;
OAuth 2.1 for any remote endpoint. Non-MCP fallback: an OpenAI-compatible **memory-router** proxy
+ REST/SDK. `helix connect` templates per client dialect (`mcpServers` / `servers` /
`context_servers` / TOML).
> **Drove:** [ADR-003](../DECISIONS.md) (refined), [ADR-023](../DECISIONS.md), [ADR-024](../DECISIONS.md). Detail → [MCP Integration](MCP_INTEGRATION.md), [API Reference](API_REFERENCE.md).

## 7. Privacy / evaluation / business

**Privacy:** tiered redaction (regex/checksum → detect-secrets + gitleaks entropy → Presidio
NER) at **ingest and outbound**; retrieval-only (never fine-tune) + provenance-cascade erasure
answers GDPR Art. 17 on derived data (EDPB Opinion 28/2024); local-first is the strongest legal
posture. **Evaluation:** don't trust LoCoMo; build on **LongMemEval** (temporal, knowledge-
update, abstention) and **define the missing coding-agent memory benchmark**. **Business:**
Apache-2.0 forever (permissive + patent grant is the embedding unlock; AGPL/SSPL would be
self-defeating); never charge to read your own memory; monetize only server-side infra; the
"review team memory like code" flow is the paid trigger, growth loop, and a poisoning defense
at once.
> **Drove:** [ADR-009](../DECISIONS.md) (refined), [ADR-025](../DECISIONS.md), [ADR-026](../DECISIONS.md), [ADR-027](../DECISIONS.md), [ADR-028](../DECISIONS.md), [ADR-029](../DECISIONS.md). Detail → [Privacy](PRIVACY_COMPLIANCE.md), [Evaluation](EVALUATION.md), [Business](BUSINESS.md).

---

## Consolidated sources

**Competitors / market.** mem0ai/mem0 · arxiv 2504.19413 · letta-ai/letta · arxiv 2310.08560 ·
getzep/graphiti · arxiv 2501.13956 · topoteretes/cognee · langchain-ai/langmem ·
supermemoryai/supermemory · memodb-io/memobase · arxiv 2502.12110 (A-MEM) ·
basicmachines-co/basic-memory · neuml/txtai · MystenLabs/walrus · arxiv 2505.05370 (Walrus) ·
anthropic.com/news/model-context-protocol · a16z.news/p/big-ideas-2026-part-1

**Memory science.** simplypsychology.org/declarative-memory · PMC4526749 (systems
consolidation) · pnas.org/doi/10.1073/pnas.2123432119 (CLS) · pubmed 22141588 ·
en.wikipedia.org/wiki/SuperMemo (SM-2) · ar5iv 2304.03442 (Generative Agents) · arxiv 2310.08560
(MemGPT) · letta.com/blog/sleep-time-compute · arxiv 2512.16962 / christian-schneider.net
(poisoning) · indium.tech/blog/agent-memory-compression-failure-modes

**Retrieval.** arxiv 2004.04906 (DPR) · arxiv 2104.08663 (BEIR) · cormack RRF SIGIR'09 · arxiv
2405.14831 / 2502.14802 (HippoRAG) · arxiv 2404.16130 (GraphRAG) · arxiv 2410.05779 (LightRAG) ·
answer.ai/posts/2024-08-13-small-but-mighty-colbert · arxiv 2212.10496 (HyDE) · docTTTTTquery ·
huggingface.co/BAAI/bge-small-en-v1.5 · huggingface.co/blog/embedding-quantization · arxiv
2307.03172 (Lost in the Middle) · MMR (Carbonell & Goldstein 1998)

**Storage.** alexgarcia.xyz/blog sqlite-vec · github.com/asg017/sqlite-vec · docs.lancedb.com ·
theregister.com/2025/10/14/kuzudb_abandoned · duckdb.org/docs vss · sqlite.org/wal ·
tigerdata.com/blog/pgvector-vs-qdrant · lib.rs/crates/fastembed

**Crypto / sync.** en.wikipedia.org/wiki/ChaCha20-Poly1305 · doc.libsodium.org · C2SP age.md ·
OWASP Password Storage Cheat Sheet (Argon2id) · BLAKE3 · agilebits.github.io/security-design
(1Password) · standardnotes.com/help/security/encryption · tarsnap.com/crypto · automerge.org ·
mattweidner.com CRDT survey · v1-docs.xtdb.com bitemporality · docs.dolthub.com git-for-data

**MCP.** modelcontextprotocol.io/specification/2025-06-18 (+/2025-11-25) · invariantlabs.ai
(tool poisoning) · simonwillison.net/2025/Jun/16 (lethal trifecta) · code.claude.com/docs/en/mcp ·
anthropic.com/engineering/writing-tools-for-agents · supermemory.ai/docs/memory-router

**Privacy / eval / business.** github.com/microsoft/presidio · truefoundry.com pii-redaction ·
edpb.europa.eu Opinion 28/2024 · unit42.paloaltonetworks.com indirect-prompt-injection ·
arxiv 2410.10813 (LongMemEval) · blog.getzep.com lies-damn-lies (LoCoMo critique) ·
termsfeed.com source-available-license-risks · oneuptime.com open-core ·
thenewstack.io open-source-original-plg

*(Per-topic docs carry the full inline citations; this list is the index.)*
