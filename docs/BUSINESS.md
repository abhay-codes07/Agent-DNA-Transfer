# Helix — Business Model & GTM

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [PRD](PRD.md) · [Roadmap](../ROADMAP.md) · [Decisions](../DECISIONS.md) · [Evaluation](EVALUATION.md)

> **Decisions of record.** This document operationalizes **ADR-028** (business model & pricing principles) and **ADR-009** (Apache-2.0 license choice). Where this document and those ADRs disagree, the ADRs win. Pricing and competitor numbers are mid-2026 point-in-time and should be re-verified before any external use.

---

## 1. Thesis in one paragraph

Helix is a **$0-default, local-first, coding-native** memory layer. The local tool is and stays free — **reading your own memory on your own machine is never a paid action.** Revenue comes exclusively from **true server-side infrastructure** that only makes sense as a hosted service: team sync, hosted encrypted backup / cross-device, org policy / audit / RBAC / SSO, and managed cloud. Because the default is a local tool, **marginal cost per free user is ~0**, which makes a perpetual free tier not a loss leader but the **growth engine**. The license is **Apache-2.0 on purpose** — an embeddable dev tool that agent vendors must be able to ship inside closed products cannot be AGPL/SSPL/BSL. The primary paid trigger and growth loop is the same motion: **review team memory like code** (diff → approve → revert), which is simultaneously a collaboration feature, a memory-poisoning defense, and the wedge into per-seat/per-org billing.

---

## 2. The open-core playbook and its failure mode

Open-core means a permissively-licensed core with proprietary paid add-ons. The well-documented failure mode is the **"free→paid cliff"**: the free tier is generous enough to never convert, or the jump to paid is a vertical wall with nothing in between, so adoption never becomes revenue (https://oneuptime.com/blog/post/2026-03-03-open-source-vs-open-core-whats-the-difference/view).

Two specific traps to avoid:

1. **Adoption without conversion.** Open source is the original product-led growth motion — stars, contributions, and sharing are viral loops, and champions pull the tool into their teams (https://thenewstack.io/is-open-source-the-original-product-led-growth/). But virality without a paid trigger wired into the **daily workflow** just produces a large free base and no ARR (https://www.productmarketingalliance.com/developer-marketing/how-open-source-tools-fuel-product-led-growth/). The fix: the paid trigger (team review) must live inside the everyday loop, not in a settings page.
2. **The license rug-pull.** Elastic, HashiCorp, Redis, and MongoDB all relicensed from OSI-approved licenses to **SSPL / BSL** when cloud providers out-competed them. These are **not OSI-approved**, carry legal uncertainty, and torched community trust (https://www.termsfeed.com/blog/legal-risks-source-available-licenses/ · https://en.wikipedia.org/wiki/Open-core_model). Helix's defense is structural, not reactive — see §3.

---

## 3. Why Apache-2.0 is *required* (ADR-009)

Helix is an **embeddable dev tool**. The single most important strategic fact about an embeddable dev tool is that **agent vendors must be able to embed it in closed-source products.** That constraint eliminates the copyleft and source-available families:

| License | Patent grant? | Can an agent vendor embed it in a closed product? | Verdict for Helix |
|---|:---:|:---:|---|
| **Apache-2.0** | **Yes** | **Yes** | **Required.** |
| MIT | No | Yes | Permissive but **no patent grant** — leaves embedders exposed. |
| AGPL-3.0 | Yes (copyleft) | **No** (network copyleft) | Self-defeating — basic-memory's AGPL is exactly why it can't be embedded. |
| SSPL | — | **No** | Not OSI-approved; un-embeddable; trust-destroying. |
| BSL | — | **No / time-delayed** | Source-available, not open source; un-embeddable. |

The decisive detail is the **patent grant**: Apache-2.0 includes an explicit patent license that **MIT lacks**. For a tool that vendors will embed at scale, that grant is the unlock — it removes the patent-exposure objection from every embedder's legal review (https://www.opensourcealternatives.to/blog/open-source-license-guide). AGPL/SSPL/BSL are **self-defeating for an embeddable component**: the network-copyleft or source-available terms are precisely what stops a vendor from shipping the tool inside Cursor, Claude Code, or their own agent.

**Public no-relicense commitment.** To pre-empt the Elastic/HashiCorp/Redis/Mongo rug-pull fear, Helix makes a **public, durable commitment never to relicense the core away from Apache-2.0.** This is a feature, not a footnote: it is the thing that lets a vendor bet their product on embedding Helix. The commitment is the moat that the relicensing incumbents destroyed for themselves.

---

## 4. How comparable products monetize

The pattern across the category is consistent: **free volume cap → paid sophistication.** The thing you pay for is not "memory," it's a *capability* or a *limit lift*.

| Vendor | The paid trigger | The "cliff" |
|---|---|---|
| **Mem0** | **Graph memory is gated to the $249 Pro tier** — you pay for sophistication, not volume. | Hobby $0 (10k) → real graph requires $249. |
| **Zep** | Hosted bi-temporal graph + audit. | **Flex ~$125/mo, 50K-credit cliff** — a hard step up (https://agentmarketcap.ai/blog/2026/04/10/agent-memory-vendor-landscape-2026-letta-zep-mem0-langmem). |
| **Letta** | **Tool-time billing ~$0.00015/sec** + $0.10/agent. | Usage-metered; cost scales with agent activity. |
| **Supermemory** | Scale / self-host-at-scale features. | $0 ($5) → Pro $19 → … → **Scale $399** for self-host at scale. |
| **basic-memory** | Hosted sync / cloud. | Self-host free → cloud **$15/mo** (flat, gentle). |

The lesson: monetize **sophistication and hosted infrastructure**, keep the local/volume floor genuinely usable, and **make the step up gradual** so you don't recreate the free→paid cliff that Zep's ~$125/mo and Mem0's $0→$249 jump exemplify.

---

## 5. Pricing principles (ADR-028)

These are the load-bearing rules. Each is a constraint, not a suggestion.

1. **Never charge to read your own local memory.** Reading, writing, and merging memory on your own machine is free forever. Charging for it would break the local-first promise and hand the wedge to a free competitor.
2. **Monetize only true server-side infrastructure** — things that genuinely cannot exist on one laptop:
   - **Team sync** (multi-writer reconciliation across people).
   - **Hosted encrypted backup / cross-device** restore.
   - **Org policy / audit / RBAC / SSO.**
   - **Managed cloud** (run-it-for-me).
3. **Bill per-seat / per-org, never per-memory.** Per-memory pricing punishes the product's core value (remembering more) and recreates the volume-cap cliff. Per-seat/per-org aligns price with team value and is what enterprises already budget for.
4. **No paywall inside the daily local loop.** The paid trigger lives at the *team* boundary (collaboration, governance), never inside an individual's workflow.

---

## 6. Unit economics

The economics follow directly from "$0-default local tool":

- **Marginal cost per free user ≈ 0.** A local tool runs on the user's machine; Helix pays no compute, storage, or LLM cost for free usage. (Contrast Letta, where every paged context and tool-second has a real cost the vendor must either eat or bill.)
- **Therefore the free tier is permanent and unbounded** — it is a **growth engine**, not a loss leader. There is no financial pressure to throttle free users, which is what lets the viral loops in §7 run at full volume.
- **Paid cost-to-serve is real but bounded** to the hosted layer (sync, backup, cloud). Gross margin on paid is high because the free base — the expensive part for everyone else — costs ~nothing here.
- **CAC trends toward ~0** because acquisition is developer-led (§7), not sales-led, for everything below the org tier.

This is the structural advantage: competitors who run *server-side memory for free users* are paying to acquire users who may never convert. Helix isn't.

---

## 7. Developer-led growth loops

Open source **is** the original PLG motion (https://www.bvp.com/atlas/how-developer-platforms-scale-with-product-led-growth-strategies). The loops:

1. **Install → value → share.** `pipx install` → memory "just works" in the user's coding agent → they tell a teammate. Zero-friction first run is the top of the funnel.
2. **Stars / contributions / forks → credibility → more installs.** GitHub social proof compounds (see the category: Mem0 ~58.8k ⭐, Supermemory ~27.2k ⭐ drive adoption directly).
3. **Champion → team pull.** An individual dev who relies on Helix daily pulls it into their team — which is exactly where the **team-review** paid trigger lives. The free individual tool manufactures the champion; the team feature converts the champion's org.
4. **Portable `.dna` → network spread.** Because memory is a single portable artifact, sharing memory *is* sharing the tool — the artifact itself is a distribution vector.

The critical discipline (§2): wire the paid trigger into the daily workflow so these loops convert instead of just inflating the free base.

---

## 8. The wedge: "review team memory like code"

This is the **primary paid trigger, the primary growth loop, and the primary safety mechanism — all at once.**

When a team shares memory, you cannot let any agent silently mutate the shared brain. So team memory changes flow through a **PR-style review**: **diff → approve → revert.** This single feature does three jobs:

- **Paid trigger.** Review/approval is inherently a *team* capability (multi-person, governance, audit) — it sits naturally above the free local tool and is the first thing a team will pay for. It maps cleanly to per-seat/per-org billing (§5).
- **Growth loop.** Reviewing memory like code is a workflow developers already know and trust. It makes shared memory legible, which makes teams comfortable adopting it, which pulls more seats in.
- **Poisoning defense.** Memory poisoning (a compromised or hallucinating agent writing bad memory) is the top safety risk for shared agent memory. A mandatory human/peer review gate is the mitigation — bad writes get caught at the diff before they enter the shared `.dna`.

This only works because Helix has **git-like *semantic* merge** (see [Competitive Analysis](COMPETITIVE_ANALYSIS.md) §4): you can't review a diff you can't compute. The technical capability and the business model are the same bet.

---

## 9. GTM channels

Distribution is developer-native and self-serve top-to-bottom:

| Channel | Motion |
|---|---|
| **PyPI / pipx** | `pipx install helix` — the canonical one-command install. |
| **GitHub** | The home base: README, stars, issues, contributions — the PLG flywheel. |
| **MCP directories** | Listed in MCP registries; MCP is table stakes (see Competitive Analysis), so presence here is mandatory, not optional. |
| **"Add to Cursor / Claude Code" one-liners** | Copy-paste install snippets that drop Helix into the agent the developer already uses — the Supermemory-style near-zero-friction integration. |

The whole funnel is self-serve until the **org/enterprise tier** (SSO, RBAC, audit, procurement), where a light sales-assist motion kicks in.

---

## 10. Phased monetization timeline

| Phase | Focus | What ships | Monetization |
|---|---|---|---|
| **Phase 0 — Free core** | Adoption | Local-first tool, `.dna` artifact, MCP, coding-native memory, semantic merge. | **$0.** Pure growth; no billing surface. |
| **Phase 1 — Team sync + review** | First revenue | Multi-writer team sync + PR-style memory review (diff/approve/revert). | **Per-seat** team plan. The wedge (§8) turns on here. |
| **Phase 2 — Hosted backup + cross-device** | Expand paid | Hosted encrypted backup, cross-device restore. | Add-on / higher per-seat tier. |
| **Phase 3 — Org governance** | Enterprise | RBAC, SSO, audit, org policy. | **Per-org / enterprise**, sales-assisted. |
| **Phase 4 — Managed cloud** | Run-it-for-me | Fully managed hosted Helix. | Managed-cloud subscription. |

Each phase only ever charges for server-side infrastructure (§5); the local tool stays $0 across all phases.

---

## 11. Risks

| Risk | Why it bites | Mitigation |
|---|---|---|
| **Adoption without conversion** | Large free base, no ARR — the classic open-core trap. | Paid trigger (team review) wired into the daily workflow; gentle, gradual step-up pricing (avoid the Zep/Mem0 cliff). |
| **Free tier cannibalizes paid** | If free does *too* much, teams never upgrade. | Keep the free/paid line at the **team boundary** — individual = free, multi-person governance = paid. Per-seat, not per-memory. |
| **License-trust skepticism** | Devs have been burned by Elastic/HashiCorp/Redis/Mongo relicensing. | **Public no-relicense commitment** to Apache-2.0 (§3) — turn the incumbents' betrayal into our differentiator. |
| **MCP commoditization** | MCP is table stakes; it differentiates nothing. | Compete on the whitespace (coding-native + semantic merge + signed/encrypted `.dna`), not on protocol support. |
| **A vendor embeds and never pays** | Apache-2.0 lets anyone embed the free core. | That's the *point* — embedding is top-of-funnel. Revenue is the hosted team/org layer, which embedding doesn't replace. |
| **Incumbent free local clone** | Supermemory/basic-memory already do local + $0. | Out-execute on the intersection none of them hold (coding-native + semantic merge + signed single-file + permissive license). |
| **Unclear TAM** | No audited memory TAM; estimates conflict wildly. | Anchor to the real, named bottleneck (a16z Big Ideas 2026: context/state) and the agents market ($7.84B → $52.6B), not vendor TAM fan-fiction. |

---

## Sources

- Open-core vs open-source / free→paid cliff — https://oneuptime.com/blog/post/2026-03-03-open-source-vs-open-core-whats-the-difference/view
- License legal risk (SSPL/BSL) — https://www.termsfeed.com/blog/legal-risks-source-available-licenses/
- Open-core model & relicensing history — https://en.wikipedia.org/wiki/Open-core_model
- License guide (Apache patent grant vs MIT) — https://www.opensourcealternatives.to/blog/open-source-license-guide
- Agent memory vendor landscape & pricing — https://agentmarketcap.ai/blog/2026/04/10/agent-memory-vendor-landscape-2026-letta-zep-mem0-langmem
- Open source as original PLG — https://thenewstack.io/is-open-source-the-original-product-led-growth/
- Developer platforms & PLG — https://www.bvp.com/atlas/how-developer-platforms-scale-with-product-led-growth-strategies
- Open-source tools fuel PLG (conversion discipline) — https://www.productmarketingalliance.com/developer-marketing/how-open-source-tools-fuel-product-led-growth/
- a16z Big Ideas 2026 (context/state as the bottleneck) — https://www.a16z.news/p/big-ideas-2026-part-1
- Vendor pricing pages — https://mem0.ai/pricing · https://www.getzep.com/pricing/ · https://docs.letta.com/guides/build-with-letta/pricing · https://supermemory.ai/pricing/

*Pricing and competitor figures are mid-2026 point-in-time snapshots; re-verify before external use.*
