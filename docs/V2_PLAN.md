# Helix v2 — Phase 2 Plan ("Git for your AI's memory")

> Status: **Proposed** · Authored 2026-06-19 · Supersedes the v2 sections of [`ROADMAP.md`](../ROADMAP.md)
> Research backing: eight parallel deep-research sweeps (memory frontier, competitive landscape,
> ecosystem/distribution, collaboration, retrieval, trust/compliance, business model, product/UX).
> Source appendix at the end. This doc is the contract for what v2 is and the order we build it.

---

## 0. TL;DR

Helix v1 shipped a genuinely strong, SOTA-aligned memory engine: extract → consolidate
(bi-temporal) → one SQLite `.dna` file → hybrid + graph retrieval → decay/reflection, served over
MCP, packaged as a signed + encrypted portable strand. The research is clear that this architecture
is *where the field landed in 2026* — so **v2 is additive, not a rewrite.**

The strategic move for v2 is a **positioning shift backed by features no competitor has**:

1. **"Git for your AI's memory."** Make `diff / merge / branch / rollback` on a portable, signed,
   encrypted `.dna` strand the headline. *No competitor offers this* — it's pure white-space and the
   natural extension of v1's team-sync.
2. **Coding-native, cross-tool, ownable.** One memory that follows a developer across Cursor →
   Claude Code → Windsurf, with per-fact provenance, that survives any vendor switch. The incumbents'
   cloud economics structurally *prevent* them from copying this.
3. **$0/offline stays the uncompromised default.** Every paid competitor degrades or paywalls
   offline (Mem0 gates graph memory at $249/mo; Cursor disables memory offline; Pieces caps
   retention at 9 months). Helix makes "$0 = the default, not a degraded mode" the contrast.
4. **The moonshot: become the open standard** — the "USB for AI memory." A 2026 research blueprint
   (*Portable Agent Memory*, arXiv 2605.11032) is nearly a 1:1 match for `.dna`, and MCP (now under
   the Linux Foundation) explicitly does **not** standardize a portable memory artifact. That gap is
   ours to own.

**The differentiation thesis in one line:** *Every well-funded competitor builds memory-as-a-service;
every aligned OSS project builds general-purpose memory. Helix v2 is the only coding-agent-native,
local-first memory you cryptographically own and can version, merge, and carry as a single signed
file.* That structural gap — not a feature list — is the moat.

---

## 1. Where Helix sits (positioning map)

```
                         LOCAL-FIRST
                              │
      Basic Memory ●          │          ● Cognee
      Pieces ●(closed)        │          ● Supermemory
      Windsurf ◐              │     ★ HELIX          ● Memobase
 ──── CODING ─────────────────┼────────────────────────── GENERAL ────
      Cursor ○                │
      Continue ◐ (frozen)     │          ● Mem0 / OpenMemory ◐
      ChatGPT/Claude/         │          ● Letta ◐
      Gemini ○ ───────────────┤          ● Zep / Graphiti ○
                            CLOUD          ● Memara ○
      (● OSS   ◐ open-core/partial   ○ proprietary)
```

Helix is the **sole occupant** of {local-first ∩ coding-native ∩ portable-signed-encrypted ∩ OSS-$0}.
The other axis no 2-D map shows — *portable / cryptographically ownable* — is occupied by **nobody**:
Claude offers raw export, Context Pack offers plaintext, Cloudflare offers exportable blobs; none are
signed, encrypted, offline, and mergeable. That is the axis v2 makes its home.

**Threats to defend against** (from the competitive sweep):
- **Native incumbents bundling "good enough" free memory** (Claude/Cursor/ChatGPT) — the existential
  risk. *Defense:* be the **vendor-neutral cross-tool layer**; only Helix's `.dna` survives a tool
  switch. Lean on Claude's own memory-export feature as third-party validation of the portability thesis.
- **Mem0's capital + distribution** ($24M Series A) commoditizing "memory MCP." *Defense:* don't
  compete on generic API memory — win on ownership + portability + coding-nativeness they can't
  retrofit without abandoning cloud-first economics.
- **Aligned OSS (Basic Memory, Cognee) adding crypto/coding features.** *Defense:* ship
  signing + encryption + git-ops + coding-typed-graph **now**, as the integrated default they'd have
  to bolt on against their general-purpose grain.

---

## 2. The eight v2 pillars

Each capability carries an effort tag (S/M/L) and a priority (P0 = v2.0 headline, P1 = v2.x, P2 = later/moonshot).
Everything marked "local-first: yes" runs at $0 with no network. Cloud is always opt-in.

### Pillar 1 — Memory Intelligence (the engine gets smarter)

The frontier has moved *past* v1's loop; these close the gap and are disproportionately valuable for a
*coding* product.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 1.1 | **Procedural / skill memory** (Voyager-style) | A new `procedure` type: verified, reusable how-to recipes (build/fix/codemod/review) keyed by trigger conditions — distinct from declarative facts. The single biggest gap for a *coding* agent: v1 stores facts about code, not *how to act*. Promotion is local — when an episode ends in an observed success signal (tests pass/build green), distill the trajectory into a skill; SM-2 becomes its reliability score. | L | **P0** |
| 1.2 | **Offline "sleep-time" consolidation** | Move reflection off the hot path into a scheduled `helix consolidate` job that abstracts clusters of raw episodes into durable semantic facts (CLS fast/slow split). Higher-quality memory at $0 live-latency. Guard against self-talk drift: every consolidated fact must cite ≥2 sourced episodes. | M | **P0** |
| 1.3 | **Staleness / implicit-invalidation detection** | Flag facts that are likely *no longer true* (dependency upgraded, API renamed, "we migrated to Postgres" should stale every SQLite snippet) — not just low-relevance. Closes the #1 named production gap ("confidently wrong" high-relevance memories). Advisory only, never auto-delete. | M | **P0** |
| 1.4 | **Change-as-event temporal facts** | Reify transitions ("switched X→Y at T") as first-class queryable edges, not silent overwrites. Answers "when/why did this change?" — where every memory benchmark collapses. Builds directly on v1's bi-temporal columns. | M | P1 |
| 1.5 | **Provenance + uncertainty + conflict surfacing** | Keep conflicting facts side-by-side with a `conflicts_with` edge and surface both with sources instead of silently auto-resolving. Cheapest trust win; aligns with "the user owns the memory." | S | **P0** |
| 1.6 | **Self-organizing A-MEM links** | At write time, auto-link a new memory to nearest neighbors with an LLM/heuristic rationale + tags. Upgrades graph expansion from purely structural to semantically justified. Cap out-degree + similarity floor to prevent link explosion. | M | P1 |
| 1.7 | **Auto-tuned write policy** (Memory-R1-lite) | Replace static ADD/UPDATE/NOOP thresholds with offline local calibration from outcome logs (was the memory later retrieved and led to a passing edit?). **Not** default RL — ship as threshold auto-tuning; full RL stays opt-in cloud. | L | P2 |

> Skeptic's flag carried from research: most 2025–26 "memory SOTA" wins are reported on *conversational*
> benchmarks (LoCoMo/LongMemEval). A coding product must build its own eval (skill-reuse rate,
> stale-fact catch rate, build-green-after-recall) rather than chase chat scores. See Pillar 1 → Eval.

### Pillar 2 — Retrieval & Reasoning 2.0

v1's pipeline is already well-aligned ("selective, distilled, ranked beats context-stuffing"). These
are gated, additive upgrades — default the expensive ones to *off* and trigger on detected complexity.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 2.1 | **Local cross-encoder reranker** | Optional `bge-reranker-v2-m3` / `mxbai-rerank-base-v2` over the top ~25 post-RRF candidates. ~+17% recall@5 for ~150ms CPU — the best effort/quality ratio in the whole retrieval sweep. Config-gated, off for tiny strands. | S–M | **P0** |
| 2.2 | **Embedding upgrade + compact storage** | Swap `bge-small` → **EmbeddingGemma-300M** or **nomic-embed-text-v2-moe**; add **`jina-embeddings-v2-base-code`** for code. Store with **int8 quantization + Matryoshka** (768 stored, search at 256) — ~4× smaller strands, near-lossless. Touches every query and every strand size. | S–M | **P0** |
| 2.3 | **Tighter context packing** | Position-aware ordering (highest-salience first/last, never the middle), a relevance *threshold* instead of fixed top-k, and aggressive near-neighbor dedup before packing (semantically-related distractors are the harmful ones). Cheap, deterministic, high-impact. | S–M | **P0** |
| 2.4 | **Proactive "current-file" surfacing** | Surface the top 1–3 highest-confidence, type-scoped memories for the open file / recent edits — behind a **hard confidence gate** (surface nothing rather than something marginal). Highest new-capability upside; net-negative if the gate is loose ("context rot": one distractor measurably lowers accuracy). | M | P1 |
| 2.5 | **Memory-search-as-a-tool + complexity-gated 2nd hop** | Keep memory search idempotent and re-callable by the agent (don't force internal loops); add a cheap heuristic complexity gate that only triggers a second graph-expansion hop on multi-hop queries. | S–M | P1 |
| 2.6 | **Lazy global/thematic query mode** | A broader cross-project "what are the themes" mode with summaries computed *on demand*, never as a batch indexing step. **Explicitly skip** Microsoft-GraphRAG community detection (3–5× indexing cost, pays off only above ~100k tokens — not the single-user case). | M | P2 |

> Hard rules from the packing research, baked into 2.3: accuracy peaks around ~3 docs then plateaus;
> effective context is often <50% of advertised; inject *atomic delimited facts, not prose*.
> **Skip ColBERT/late-interaction** (≈250× index bloat — fights the single-SQLite-file model).
> **Don't pick embeddings by MTEB** (negatively correlated with memory retrieval) — build a tiny
> real-strand eval.

### Pillar 3 — Collaboration & Multi-Agent (memory for teams & swarms)

Makes memory work across many agents and many people while staying local-first and privacy-preserving.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 3.1 | **Scoped / namespaced memory + redaction-on-share** | A `scope` + `visibility` (personal/team/public) tag per fact; a share manifest that selects a scope subtree; a redaction pass (Presidio + allowlist) before export; **Merkle selective disclosure** so a shared strand reveals only the chosen facts with inclusion proofs against the signed root. Hard rule: *personal identity facts never auto-share.* Unblocks both multi-agent and multi-person sharing. | M | **P0** |
| 3.2 | **Per-contributor signed provenance + TOFU quarantine** | Every imported fact carries an Ed25519-signed attestation (who distilled it, from what). Trust-on-first-use key-pinning; untrusted-key facts land in a **quarantine** zone, never auto-merged; retrieval down-weights low-trust facts. The biggest *trust* unlock — directly counters documented poisoning attacks (PoisonedRAG ~90% with ~5 docs; MINJA 95%+ query-only). | M | **P0** |
| 3.3 | **CRDT-semantics merge layer** | Add-wins OR-Sets for fact/edge existence + LWW-registers-over-Lamport-clocks for scalar fields, making the conflict-free 80% automatic, while keeping v1's semantic 3-way merge as the authoritative path for genuine contradictions. Compact tombstones at signed checkpoints to keep the portable file small. | L | P1 |
| 3.4 | **`helix propose` / `review` governance** | Incoming facts from other contributors arrive as a reviewable "memory PR"; a maintainer approves/vetoes before merge to a shared scope. Authority-weighted supersession (owner > contributor) with a required `supersede_reason`. Hash-chained Merkle audit log of every accept/reject/supersede (aligns with the chosen BLAKE3 Merkle design). | M | P1 |
| 3.5 | **MCP memory namespaces + handoff** | Per-agent `agent_scope` on the MCP surface; default **read-shared, write-scoped** (blackboard pattern) so sub-agents see team memory but write to their own namespace until promoted; `memory.handoff(facts, to_scope)` to pass a vetted subset between agents. Prevents cross-agent contamination. | M | P1 |
| 3.6 | **Optional p2p sync adapter** | An `automerge-repo`-style op-log sync over WebSocket/WebRTC/local-dir while the SQLite `.dna` stays the materialized signed artifact. Strengthens local-first multi-device without a cloud account. Gated behind config; v1 transports already cover the basic need. | L | P2 |

### Pillar 4 — Trust, Privacy & Compliance (earn the "you own it" claim)

Helix's architecture is a compliance *asset*: it stores discrete, addressable, deletable fact-embeddings
(not model weights) and already encrypts client-side. Almost everything below is defense-in-depth on a
boundary we already own.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 4.1 | **Erasure cascade + tombstones + DSAR/rectification** | Delete fact → delete embeddings → recompute edges → re-derive any consolidated facts that cited it, transactionally; tombstones that survive sync/merge (no resurrection); subject-scoped audit/provenance export; edit→re-embed→supersede. Satisfies GDPR Art. 16/17 + CCPA. **Differentiator:** "we delete vectors, not weights — no machine-unlearning needed." | L | **P0** |
| 4.2 | **Envelope encryption (DEK/KEK) + pluggable unlock** | One random data key encrypts the strand; wrap it with N key-encryption-keys (passphrase, **OS keychain** TPM/Secure-Enclave, **YubiKey FIDO2-PRF**, **SLIP-0039 Shamir social recovery**). Rotation re-wraps a small DEK, not the whole DB. Kills single-passphrase fragility. *Invariant:* never sync/hardware-wrap the live **signing** key — its portability stays an explicit user export. | M (per provider) | **P0** |
| 4.3 | **Quarantined dual-LLM extraction + injection hardening** | The LLM that reads untrusted docs has **no tool access** and emits only structured output; spotlight/datamark untrusted input; strip the *lethal trifecta* at ingest (auto-render markdown images, invisible-Unicode, raw URLs) so a stored fact can't become an exfil payload; pin/hash Helix's own MCP tool descriptions (anti-rug-pull). Defends the product's actual attack surface. | M–L | **P0** |
| 4.4 | **Per-fact in-toto/DSSE signatures + in-strand transparency log** | Sign each fact (not just the whole strand) so a recipient can verify/accept/reject on merge and detect mutation; embed tlog-tiles consistency-proof math in the `.dna` for serverless append-only history. Hosted Rekor stapling stays opt-in for a future "publish a strand" feature. | M | P1 |
| 4.5 | **Ingest secret-scanning + PII redaction** | Local gitleaks-rules + entropy as a *hard gate* so an API key never becomes a "fact"; Presidio analyzer+anonymizer (NER + checksums) before write. Highest-ROI, fully local, on-brand. | S–M | **P0** |
| 4.6 | **Opt-in E2EE cloud sync + region pinning** | If/when cloud sync ships, client-held keys + region pinning keep the relay holding only ciphertext (radically lowers GDPR transfer exposure). TEE (AWS Nitro) only as honestly-caveated defense-in-depth — *not* the real boundary (TEE.fail, Oct 2025, broke physical attestation; client-side encryption stays the boundary). | M–L | P1 |
| 4.7 | **AI-Act defensive docs** | An AI-component disclosure proving every LLM path has a deterministic local fallback ("deployer, not provider"), a downstream-customer doc pack, and an "AI-generated" label on LLM-derived facts. Mostly documentation. | S–M | P1 |

> Explicitly **research-only / theater to avoid as load-bearing:** general FHE over the graph,
> general-purpose zkVMs for per-fact proofs, leakage-free searchable encryption (doesn't exist at speed),
> Intel SGX (deprecated), federated learning, mandatory transparency logs, central-DP telemetry, and
> any prompt-filter/classifier used as the *sole* injection defense.

### Pillar 5 — Ecosystem & Distribution (be everywhere)

MCP already makes Helix "supported everywhere" nearly for free. v2's job is native memory *adapters*,
*discovery*, and new *capture surfaces*.

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 5.1 | **MCP Registry listing + `.mcpb` bundle** | `server.json` + GitHub-OAuth namespace + `mcp-publisher`; one publish propagates to PulseMCP/Glama/mcp.so. Add an `.mcpb` for one-click Claude Desktop install. Pure reach, nearly free. *(Note: the official registry is still preview, not GA — list anyway, it's cheap insurance.)* | S | **P0** |
| 5.2 | **CLI-as-a-tool hardening** | `--json` output, stable flags, POSIX exit codes, a 3–4 command "tool card." The many frameworks that shell out but don't speak MCP can then use Helix via an allowlisted `Bash(helix recall *)`. Best ROI of any surface. | S | **P0** |
| 5.3 | **Framework memory adapters** | `HelixStore(BaseStore)` for **LangGraph** (flagship; also captures the competing `langmem` ecosystem), `HelixMemory(Memory)` for **AutoGen/AG2** (cleanest interface, lowest effort — do first), `HelixSession` for **OpenAI Agents SDK**, `HelixStorage` for **CrewAI**, in-process MCP for the **Claude Agent SDK**. | M each | **P0** (LangGraph, AutoGen) / P1 (rest) |
| 5.4 | **VS Code extension** | Native tool registration (`vscode.lm.registerTool`) so memory surfaces in Copilot agent mode, a graph TreeView sidebar, capture commands, auto-install via `.vscode/mcp.json`. Largest agent-coding userbase. | M | P1 |
| 5.5 | **Browser extension** | MV3 content scripts on chatgpt.com / claude.ai with a "Save to Helix" that distills the visible conversation to localhost. Captures memory where users actually converse — a surface MCP can't reach. | M | P1 |
| 5.6 | **GitHub ingestion connector** | A GitHub App (fine-grained per-repo) distilling conventions (CONTRIBUTING/lint configs), decisions (merged-PR threads), ownership (CODEOWNERS) into the user's *own* strand. Highest-value durable facts for coding agents. Strictly opt-in, thin relay, nothing stored server-side. | M | P1 |
| 5.7 | **Helix Hub (memory packs)** | Distribute signed `.dna` packs via **OCI/ORAS** (push/pull from GHCR, no bespoke server — Ollama validates this model) with a HuggingFace-style "memory card" + Sigstore provenance. **Team-scoped onboarding primitive, not a public bazaar** (privacy + poisoning risk). Killer use case: senior exports repo-conventions `.dna`; new hire's agent imports instantly. | M → L | P2 |
| 5.8 | **Streamable-HTTP self-host transport + outbound relay** | An *alternate* MCP transport so the **user** can self-host a remote endpoint; the privacy-preserving "remote" answer is an outbound-only relay that sees only ciphertext — never host a copy of the strand. (Cautionary: Asana hosted-MCP cross-org leak; CVE-2025-6514 RCE in `mcp-remote`.) Needs an ADR. | M | P2 |

### Pillar 6 — Product, UX & the Magic Moment

v1 made memory portable and inspectable; v2 makes it **delightful to curate, observable, and trusted.**

| # | Capability | What it adds | Effort | Pri |
|---|---|---|---|---|
| 6.1 | **Memory copilot + "what do I know about X?"** | Chat over the strand ("what do you remember about the billing service?") returning **sourced, editable, local** answers; a scoped-subgraph entity view as its backbone. Highest-intuition surface; anchors onboarding. | M | **P0** |
| 6.2 | **Observability dashboard** | A GitHub-contribution-style "facts learned/day" heatmap, ≤3 hero numbers (**facts stored · facts to review · $ saved**), a decay heatmap. The **$0-cost meter** (queries served locally × cloud-equivalent token price) is genuine, ownable whitespace — no product ships a polished savings meter, and it dramatizes Helix's core rule. | S–M | **P0** |
| 6.3 | **Trust-first review queue + diff/merge UI with undo** | Stale/conflicting facts as a finite, prioritized queue (staleness × centrality × confidence); a 3-pane "yours / incoming / merged" diff with confidence + source per row, **always undoable**. Directly beats the documented distrust of ChatGPT/opaque memory. | M | **P0** |
| 6.4 | **Menubar/tray + voice quick-capture** | A global hotkey that distills a thought into a sourced fact via on-device Whisper — nothing leaves the machine. ~1-second capture, perfectly on-brand. | S–M | P1 |
| 6.5 | **Bitemporal timeline / time-travel debugging** | Scrub "what did the agent believe on March 1?" over the existing bitemporal data; plot *events* ("learned X," "X superseded"), not raw values. The viewer for belief-level time travel. | M | P1 |
| 6.6 | **60-second onboarding "wow"** | `helix init` ingests one real conversation/repo, the dashboard **animates a graph assembling itself** with ~10 sourced facts, ending on "Ask me what I know about your billing service" → the copilot answers with provenance. The magic moment is *seeing your agent's brain build itself, instantly, locally, $0.* | M | **P0** |
| 6.7 | **Mobile companion** | A thin MCP/SDK client to review the daily digest, approve/forget facts, browse the graph on the go. *Not* capture-everything. | L | P2 |

### Pillar 7 — Business Model & GTM (open-core that respects the rules)

The cleanest, most-proven adjacent model (Obsidian + Tailscale + Sentry-FSL) is the one that *respects*
the $0/local-first/ownership rules: **everything local is free forever and fully featured; you charge
only for the optional networked layer, and encryption is never the paywall** (it's a free trust signal).

- **License:** Apache-2.0 for the engine; a Sentry-style FSL→Apache only for the *hosted relay code*.
- **Helix Local — $0 forever:** full engine, CLI, MCP server, dashboard, all SDKs; unlimited local
  strands; full extraction/retrieval/consolidation; signed/encrypted `.dna` export-import; p2p pack
  sharing; bring-your-own-keys for any optional cloud LLM/embeddings. *No feature gated. This is the product.*
- **Helix Sync — ~$5–8/user/mo:** optional **E2E-encrypted** cross-device sync + hosted backup via a
  **blind relay** (Helix never sees plaintext — Tailscale/Obsidian model); version history; quota tiers.
- **Helix Team — ~$12–20/user/mo:** shared org memory graphs, merge governance, RBAC, audit logs,
  SSO/SAML (**not** SSO-taxed). "Free for individuals, paid for teams." Unlimited free local seats.
- **Enterprise — custom:** SOC 2 Type II, SCIM, data-residency, on-prem/air-gap, CMEK, DPA,
  contractual no-training + architectural ZDR, SLA. Build only on written request.
- **GTM:** one-command `uvx`/`npx` install + per-client copy-paste snippets + Add-to-Cursor/VS-Code
  buttons + `llms.txt`/MCP manifest for *agent self-selection*; seed a shareable-`.dna`-pack loop
  (one-command import) + an `awesome-helix` list; Discord; **track downloads/active use, not stars.**
- **Funding read:** local-first is **bootstrap-or-modest-seed shaped, not a VC rocket** — raise only if
  Sync/Team conversion proves out. (MCP registries drive ~0% of installs; one-command runners do.)

### Pillar 8 — The Standard (the moonshot worth a real bet)

**Make `.dna` *the* open standard for portable agent memory — the "USB for AI memory."** The arXiv
*Portable Agent Memory* blueprint already mirrors `.dna` (BLAKE3 Merkle-DAG + Ed25519 + capability-scoped
disclosure + typed framing), and Helix's **encrypt-at-rest** strand is *ahead* of the published spec
(sign-only). MCP is now neutral-governed (Linux Foundation, Dec 2025) but deliberately leaves the
memory-artifact gap open. v2 publishes the `.dna` format as an open spec with a reference implementation
and a conformance test — distribution via the signed Helix Hub. This is category-defining, not a feature.

---

## 3. Roadmap — three waves

Sequenced so each wave ships a coherent, demoable story. P0 items first; effort-balanced per wave.

### Wave A — "Git for your memory" (v2.0) — the headline release
The thesis made real + the highest-ROI engine/trust wins.
- **Collaboration:** 3.1 scoped/redacted sharing, 3.2 signed provenance + quarantine.
- **Memory intelligence:** 1.2 sleep-time consolidation, 1.3 staleness detection, 1.5 conflict surfacing.
- **Retrieval:** 2.1 reranker, 2.2 embedding+compact storage, 2.3 tighter packing.
- **Trust:** 4.1 erasure cascade, 4.2 envelope encryption (+ OS keychain), 4.5 secret/PII gates,
  4.3 dual-LLM extraction + trifecta hardening.
- **Product:** 6.1 copilot + entity view, 6.2 observability + $0 meter, 6.3 review/diff/merge UI,
  6.6 60-second wow.
- **Distribution:** 5.1 MCP registry + `.mcpb`, 5.2 CLI-as-tool, 5.3 LangGraph + AutoGen adapters.
- **Eval:** ship the coding-memory benchmark (skill-reuse, stale-catch, build-green-after-recall).

### Wave B — "Memory for teams & agents" (v2.1)
- 1.1 **procedural/skill memory** (the defining coding capability — large, lands here), 1.4 change-as-event, 1.6 A-MEM links.
- 3.3 CRDT merge layer, 3.4 propose/review governance, 3.5 MCP namespaces + handoff.
- 2.4 proactive surfacing, 2.5 memory-as-tool + 2nd hop.
- 4.4 per-fact signatures + transparency log, 4.6 opt-in E2EE sync, 4.7 AI-Act docs.
- 5.4 VS Code extension, 5.5 browser extension, 5.6 GitHub connector.
- 6.4 quick-capture, 6.5 timeline / time-travel.
- **Business:** stand up Helix Sync (blind relay) + Team tier.

### Wave C — "The standard & the ecosystem" (v2.2+)
- Pillar 8 open spec + conformance suite.
- 5.7 Helix Hub (OCI/ORAS signed packs), 5.8 self-host transport + relay.
- 1.7 auto-tuned write policy, 2.6 lazy global query mode, 3.6 p2p sync.
- 6.7 mobile companion. Enterprise tier hardening (SOC 2).

---

## 4. Success metrics (what "v2 worked" means)

- **Retrieval quality:** ≥ target on the *coding-memory* eval (not LoCoMo) — stale-fact catch rate,
  skill-reuse rate, build-green-after-recall, recall@k with reranker.
- **Trust:** 100% of facts deletable with verified embedding-level erasure; injection red-team
  (SpAIware/MINJA-style) blocked; per-fact signatures verify on merge.
- **Portability:** a `.dna` round-trips across ≥3 agents/tools with zero loss; merge of two diverged
  strands is conflict-free for the easy 80% and reviewable for the rest.
- **Adoption (track, don't vanity):** weekly active strands, pack imports, CLI/MCP invocations,
  framework-adapter installs — **not** GitHub stars.
- **$0 promise:** default config provably makes zero network calls; the $0 meter shows real savings.

## 5. Non-goals / guardrails (unchanged golden rules)

- No core path may *require* a network call or cloud account. Cloud is opt-in and degradable.
- Never store raw transcripts — distilled facts only.
- Don't add a graph-DB dependency — the field is converging *back* to built-in entity linking, which
  vindicates the single-SQLite-file choice.
- Don't chase conversational benchmarks; build the coding eval.
- Don't paywall any core memory feature; encryption is free and universal.
- Every new fact still carries `source · created_at · confidence · type`. No exceptions.
- Expanding beyond coding (PKM/research/support) rides the *same engine* — Helix stays agent-memory
  infrastructure, it does **not** become a note app. Lifelogging (record-everything) is rejected: it
  contradicts "distilled facts, not transcripts."

## 6. Top risks

1. **Native-incumbent bundling** (Claude/Cursor free memory) — mitigate by being the vendor-neutral
   cross-tool layer; ride Claude's own export endorsement.
2. **Scope explosion** — v2 is large; the wave plan + P0/P1/P2 gating is the defense. Ship Wave A as a
   complete story before B.
3. **Injection/poisoning** — the product's core loop *is* the attack surface; Pillar 4.3/3.2 are P0 for
   that reason, and defenses are defense-in-depth, never a single filter.
4. **Local-first monetization is unproven** — keep burn near-zero (bootstrap), only build cloud/team
   when conversion shows pull.
5. **Tombstone/metadata bloat** in a portable file — compact at signed checkpoints.

---

## Appendix — research sources (grouped)

**Memory frontier:** A-MEM (arXiv 2502.12110), Mem0/Mem0g (2504.19413), *State of AI Agent Memory 2026*
(mem0.ai), Zep/Graphiti (2501.13956), HippoRAG 2, Letta sleep-time compute, Voyager (2305.16291),
ProcMEM/SkillClaw, Memory-R1 (2508.19828), MemoryOS (EMNLP 2025), *Episodic Memory is the Missing Piece*
(2502.06975), STALE (2605.06527), CLS survey (2512.13564), ConflictBank (2408.12076).

**Competitive:** Mem0 Series A (mem0.ai/series-a), Zep SOTA (blog.getzep.com), Letta benchmarks/pricing
(docs.letta.com), Cognee (€7.5M seed), Supermemory, Memobase/Memara, Pieces (pieces.app), Basic Memory
(github.com/basicmachines-co), Cursor Memories changelog, Windsurf/Devin memories, Claude/ChatGPT/Gemini
native memory, Context Pack, Cloudflare Agent Memory.

**Ecosystem/distribution:** LangGraph BaseStore, langmem, OpenAI Agents SDK sessions, Claude Agent SDK
memory-tool, CrewAI memory, AutoGen/AG2 memory, Google ADK memory, LlamaIndex Memory, MCP Registry
preview (blog.modelcontextprotocol.io), MCP Apps SEP-1865, Streamable HTTP transport, MCP OAuth
(2025-06-18), Asana MCP leak, CVE-2025-6514, VS Code LM tools API, ORAS v1.3, Ollama OCI, Sigstore npm
provenance, GitHub App permissions, Linear/Notion/Jira/Slack OAuth.

**Collaboration:** Ink & Switch local-first, Automerge 3, Weidner CRDT survey, MRDTs (2203.14518),
automerge-repo, ElectricSQL/PowerSync/Jazz, blackboard LLM swarms (2510.01285), CrewAI/LangGraph memory,
Anthropic multi-agent system, ReBAC/Zanzibar/OpenFGA, Presidio, redactable signatures (scitepress 45070),
PoisonedRAG (2402.07867), AgentPoison (2407.12784), MINJA (2503.03704), A-MemGuard (2510.02373),
in-toto/SLSA, Sigstore Rekor, W3C PROV, TOFU, Gerrit/Wikipedia-pending-changes/Dolt/Wikidata-ranking.

**Retrieval:** GraphRAG (2404.16130) + dynamic community selection, LightRAG, nano-graphrag, HippoRAG 2
(2502.14802), Self-RAG (2310.11511), Adaptive-RAG, FLARE, IRCoT, ReAct, *context rot* (trychroma.com),
*Lost in the Middle*, RULER, EmbeddingGemma, nomic-embed-v2, jina-v2-code, embedding quantization (sbert),
RTEB, effective-context (2411.07396), Anthropic context-engineering.

**Trust/compliance:** EU AI Act (artificialintelligenceact.eu) + Commission AI-system guidelines, EDPB
Opinion 28/2024, GDPR Art. 16/17, CPRA, SpAIware/Gemini-persistence (embracethered.com), lethal trifecta
(simonwillison.net), MCP security best practices, spotlighting (2403.14720), TEE.fail, AWS Nitro/GCP
Confidential Space, Apple PCC/PIR/homomorphic-encryption, YubiKey PRF, SLIP-0039, age, in-toto/DSSE,
Rekor-v2/tlog-tiles, gitleaks, Presidio, OpenDP.

**Business:** Obsidian Sync/pricing, Tailscale control-vs-data-plane, Sentry FSL, PostHog/Cal.com/GitLab
pricing, Mem0/Zep/Letta pricing, Bessemer AI pricing playbook, ssotax.org, Superpowers pack, MCP-registry
install data (synscribe/digitalapplied), OSS funding (Tidelift, sponsorware, Caleb Porzio).

**Product/UX/moonshots:** Obsidian/Roam graph views, ChatGPT-memory distrust (simonwillison.net),
SlashNote quick-capture, Mem/Copilot Memory, Readwise/RescueTime digests, GitHub contribution graph,
Anki/FSRS, *Portable Agent Memory* (2605.11032), Skilldex (2604.16911), NVIDIA NGC model signing, OWASP
agentic risks, CrewAI agent config, TOKI/Graphiti bitemporal, generative agents (3586183.3606763),
aha-moment onboarding.
