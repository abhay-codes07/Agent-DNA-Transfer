# Helix — Privacy, PII & Compliance

**Status:** Draft v1 · **Last updated:** 2026-06-18 · **Related:** [Security](SECURITY_MODEL.md) · [Memory Model](MEMORY_MODEL.md) · [.dna Format](DNA_FORMAT.md) · [Decisions](../DECISIONS.md)

Helix is a local-first, coding-agent-first, portable, $0-default AI memory layer (Apache-2.0). A memory layer is, by definition, an accreting store of whatever your agent reads, writes, and reasons over — which makes it the single highest-density concentration of PII and secrets in your toolchain. This document specifies how Helix keeps that store legally defensible and operationally safe: a tiered redaction pipeline, a GDPR/CCPA posture rooted in local-first architecture, deterministic right-to-erasure across *derived* data, and defenses against memory-poisoning prompt injection.

Two non-negotiable design commitments anchor everything below:

1. **Secrets never leave your machine — literally.** Every outbound LLM payload is redacted on-device before transmission (ADR-025). The cloud sees redacted text or nothing.
2. **Helix never fine-tunes on your memory** (ADR-026). Retrieval-only architecture sidesteps the unsolved machine-unlearning problem and makes erasure a deterministic cascade-delete.

---

## 1. Threat & data model

Helix stores three classes of data, each with distinct privacy properties:

| Class | Examples | Privacy risk | Erasure difficulty |
|---|---|---|---|
| **Source records** | Conversation turns, code snippets, user-asserted facts, ingested docs | Direct PII/secrets | Trivial — delete the row |
| **Derived artifacts** | Embeddings, summaries, knowledge-graph nodes/edges | PII *reconstructable* from source; still in GDPR scope | Hard without provenance — see §4 |
| **Indexes / metadata** | Vector index, FTS index, provenance links, signatures | Pointers to the above | Cascade from source/derived |

The dominant risk in a *coding* memory store is **secrets** (API keys, tokens, private keys), not classical PII. Coding agents routinely paste `.env` contents, CI logs, and connection strings. Secret leakage is therefore treated as a first-class, highest-severity failure mode, and the redaction pipeline orders its cheapest, highest-precision secret detectors first.

---

## 2. The redaction pipeline (ADR-025)

Redaction runs at **two boundaries**, both on-device:

- **INGEST** — before any text becomes a durable memory record (write path).
- **OUTBOUND** — before any payload leaves the device for a cloud LLM (network path).

Both boundaries share the same tiered detector stack. Microsoft explicitly warns that no PII tool guarantees catching all PII ([microsoft/presidio](https://github.com/microsoft/presidio)), so this is **defense-in-depth, not a single gate** — each tier is independently fallible and they are layered so that a miss in one is likely caught by another.

### 2.1 Tiered detector stack

| Tier | Technique | Catches | Latency | Tool |
|---|---|---|---|---|
| **1. Regex / checksum** | Pattern + Luhn/MOD-97 validation | Credit cards, SSN, IBAN, phone | sub-ms | [Presidio](https://microsoft.github.io/presidio/) pattern recognizers |
| **2. Entropy secret-scan** | Known-format regex **+** Shannon-entropy on high-randomness blobs | AWS keys, GitHub tokens, private keys, generic high-entropy secrets | low ms | [detect-secrets](https://github.com/Yelp/detect-secrets) (Yelp) + [gitleaks](https://github.com/gitleaks/gitleaks) |
| **3. NER** | spaCy / transformer models | Names, locations, orgs — *context-dependent* PII | tens of ms | Presidio NER recognizers |
| **4. Mask** | Replace span with typed placeholder + provenance | n/a (action) | sub-ms | Helix masking layer |

Pipeline order is deliberate: **regex/checksum → entropy secret-scan → NER → mask before write**. Cheap, high-precision deterministic tiers run first and short-circuit; expensive probabilistic NER runs last only on text that survived. Tier 2 sits *before* NER because secrets are the dominant coding-memory risk and entropy scanning is both cheap and high-recall for the exact threat class NER cannot see.

Detected spans are replaced with **typed, reversible-on-device placeholders** (e.g. `‹CREDIT_CARD:a1f3›`, `‹AWS_SECRET:7b20›`). The mapping from placeholder to original is stored only in the local, access-controlled store (see [Security](SECURITY_MODEL.md)) and is *never* serialized into outbound payloads.

### 2.2 Why application-layer, not gateway

Helix redacts in the application layer rather than via an LLM gateway. App-layer redaction is cheaper and structurally safer: the raw secret never reaches a network component at all, so there is no gateway honeypot accumulating plaintext, and no trust boundary crossed before masking ([TrueFoundry: PII redaction — gateway vs application](https://www.truefoundry.com/blog/pii-redaction-llm-gateway-vs-application)). For a local-first tool, the gateway pattern would *reintroduce* the central-aggregation risk that local-first exists to avoid.

### 2.3 Outbound: "secrets never leave your machine" is literally true

Every outbound LLM payload passes through the same stack at the OUTBOUND boundary. The client perturbs/redacts **before** data leaves the device, so only redacted text reaches the cloud — the on-device analogue of differential-privacy/local-redaction semantics for off-device processing ([Google Privacy Sandbox: DP semantics for ODP](https://privacysandbox.google.com/protections/on-device-personalization/differential-privacy-semantics-for-odp); [Privacy Guides: differential privacy](https://www.privacyguides.org/articles/2025/09/30/differential-privacy/)). Combined with INGEST redaction (the store itself holds masked text), this makes the claim *secrets never leave your machine* an enforced property of the data path, not a policy aspiration. Placeholders are re-hydrated locally only when the model's response returns and is rendered to the user.

---

## 3. Why local-first is the strongest legal posture

Local-first is not just a performance choice; it is the single most consequential compliance decision Helix makes. Because raw data never leaves the device:

| Property | Local-first (Helix) | Typical cloud memory SaaS |
|---|---|---|
| **Controller/processor** | User is **sole controller**; Helix vendor is *not a processor* of user data | Vendor is a processor; DPA required |
| **Cross-border transfer** | **None** — data stays on device | Transfer mechanisms (SCCs/adequacy) needed |
| **Breach surface** | The **device** the user already controls | Central honeypot aggregating many users |
| **Data minimization (Art. 5(1)(c))** | Native — nothing collected centrally | Must be engineered against default collection |
| **Purpose limitation (Art. 5(1)(b))** | Native — data used only on the device for the user's own purpose | Contractual + technical controls required |

There is **no third-party processor relationship** for stored memory and **no cross-border transfer**, which removes two of the most expensive and litigated compliance obligations entirely. The residual breach surface is the user's own machine — the same surface that already holds their source code, SSH keys, and browser profile — rather than a new central repository attractive to attackers. This is why Helix treats local-first as the *foundation* of its posture, and the redaction pipeline as defense-in-depth on top of it.

### 3.1 CCPA / CPRA

Under CCPA/CPRA, a tool that does not collect, sell, or share personal information off-device is largely outside the statute's collection-and-sale machinery for the stored memory. Helix's $0-default, no-telemetry posture means there is no "sale" or "sharing" of personal information to disclose, and the consumer rights (access, deletion) are satisfied trivially because the consumer holds the only copy. Any outbound LLM call uses redacted payloads (§2.3), keeping personal information from being disclosed to the model provider.

---

## 4. Right to erasure across derived data (GDPR Art. 17 / ADR-026)

Deleting a *record* is easy. The legal danger is **derived data** — embeddings, summaries, graph nodes — that may still encode the personal data of the deleted record.

### 4.1 Derived artifacts are still personal data

Per **EDPB Opinion 28/2024 (Dec 2024)**, AI artifacts are "anonymous" only if the likelihood of (a) *extracting* personal data from the model/artifact **and** (b) *regurgitating* it from queries is "insignificant" — assessed case-by-case ([EDPB opinion](https://www.edpb.europa.eu/news/news/2024/edpb-opinion-ai-models-gdpr-principles-support-responsible-ai_en); [IAPP analysis](https://iapp.org/news/a/edpb-weighs-in-on-key-questions-on-personal-data-in-ai-models)). An embedding from which the source text can be reconstructed therefore **remains personal data and stays in GDPR scope**. Helix does not assume its embeddings are anonymous; it assumes the opposite and engineers erasure accordingly.

### 4.2 The machine-unlearning trap Helix avoids

If derived data lived in *model weights* (i.e., if Helix fine-tuned on user memory), erasure would require **machine unlearning of weights — an unsolved problem that may not satisfy regulators** ([Machine unlearning survey, arXiv:2412.06966](https://arxiv.org/pdf/2412.06966)). Helix sidesteps this entirely:

> **Helix never fine-tunes on user memory (ADR-026).** Memory is retrieval-only. Personal data lives in deletable records and deletable derived artifacts — never baked into weights.

### 4.3 Provenance-linked deterministic cascade

Every derived artifact carries a **provenance link** to the source record(s) it was computed from. Erasure of a source record is therefore a deterministic cascade-delete:

```
erase(record R) ⇒ delete R
              ⇒ delete every embedding derived from R
              ⇒ delete / recompute every summary that consumed R
              ⇒ delete every graph node/edge sourced solely from R
              ⇒ purge R from vector + FTS indexes
              ⇒ tombstone the provenance entry (auditable, reversible window)
```

Because the provenance graph is explicit and maintained at write time, no scan or heuristic is needed to find "what did this record touch" — the answer is a graph traversal. Summaries that mixed multiple sources are recomputed from the surviving sources rather than left to leak the erased one. This is the operational meaning of ADR-026's *erasure cascade*.

---

## 5. Data minimization & purpose limitation mapping

| GDPR principle | Helix mechanism |
|---|---|
| **Lawfulness/consent** | User initiates every ingest; $0-default, opt-in capture |
| **Purpose limitation (5(1)(b))** | Memory used only locally, for the user's own agent sessions; no secondary use, no training |
| **Data minimization (5(1)(c))** | Redaction-at-ingest strips secrets/PII before storage; only what the agent needs is retained |
| **Accuracy (5(1)(d))** | Human-reviewable, reversible memory (§7); user can correct/delete |
| **Storage limitation (5(1)(e))** | Local TTL/retention policy; user-owned lifecycle |
| **Integrity & confidentiality (5(1)(f))** | On-device encryption + signing (see [Security](SECURITY_MODEL.md)) |
| **Accountability (5(2))** | Provenance graph + audit tombstones provide demonstrable erasure |

---

## 6. Differential-privacy / on-device redaction semantics for LLM calls

Helix's outbound contract mirrors the *local* model of privacy protection: transform data on the client **before** it leaves, so the off-device processor only ever sees protected text ([Google Privacy Sandbox: DP semantics for ODP](https://privacysandbox.google.com/protections/on-device-personalization/differential-privacy-semantics-for-odp); [Privacy Guides: differential privacy](https://www.privacyguides.org/articles/2025/09/30/differential-privacy/)). Concretely:

- **Redaction is mandatory and pre-network.** The detector stack (§2) runs against every outbound payload; unredacted spans are masked, not transmitted.
- **Placeholders are semantically typed** so the model retains enough structure to reason (`‹EMAIL›`, `‹AWS_SECRET›`) without seeing values.
- **Re-hydration is local-only**, applied to the response on the user's device.
- This is *not* a formal (ε, δ)-DP guarantee over query results; it is on-device redaction with DP-style *local* semantics — the protection is applied at the source, before the trust boundary, which is the property that matters for "nothing sensitive leaves the machine."

---

## 7. Memory poisoning & persistent prompt injection

A memory layer introduces a threat that stateless agents do not have: **persistent, durable corruption**. If an attacker can get malicious instructions written into long-term memory, those instructions are silently re-injected into future sessions.

### 7.1 The attack class (cited)

- **Unit 42 (Palo Alto)** demonstrated poisoning the long-term memory of **Amazon Bedrock Agents** via *indirect* prompt injection: corrupting session-summarization so attacker instructions are written to persistent memory and silently re-injected later ([Unit 42](https://unit42.paloaltonetworks.com/indirect-prompt-injection-poisons-ai-longterm-memory/)).
- **MINJA** achieves **>95% injection success / ~70% attack success rate** against memory-augmented agents.
- **MemoryGraft** is an *"attack that waits"* — temporally decoupled, planting a payload that triggers in a later, unrelated session ([Schneider: persistent memory poisoning](https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents/); [arXiv:2601.05504](https://arxiv.org/abs/2601.05504); [Lakera: agentic AI threats](https://www.lakera.ai/blog/agentic-ai-threats-p1)).

**Local-first reduces but does not eliminate this** — your own browsing history and repositories can carry injection payloads into memory just as a multi-tenant system can.

### 7.2 Mitigations

| Mitigation | Mechanism |
|---|---|
| **Untrusted-by-default ingestion** | Externally-ingested content (web pages, docs, tool output) is treated as untrusted; **never written durably without sanitization** |
| **Provenance tags** | Every record is tagged **user-asserted** vs **agent-ingested**; retrieval and trust decisions can weight by origin |
| **Injection-scan before commit** | Candidate writes are scanned for injection patterns/imperative-to-the-model content *before* they become durable |
| **Human-reviewable + reversible** | Memory writes are inspectable and undoable; no silent durable mutation of behavior-shaping memory |
| **Integrity / signing** | Records are signed; tampering and provenance forgery are detectable (see [Security](SECURITY_MODEL.md)) |

The combination of provenance tagging and untrusted-by-default ingestion is the structural defense: agent-ingested external text can never be silently promoted to user-asserted trust, which is exactly the promotion the Unit 42 and MemoryGraft attacks rely on.

---

## 8. Compliance checklist

- [ ] Redaction runs at **both** INGEST and OUTBOUND boundaries, on-device.
- [ ] Tier order enforced: regex/checksum → entropy secret-scan → NER → mask.
- [ ] detect-secrets + gitleaks entropy scan covers generic high-entropy blobs, not just known formats.
- [ ] No raw secret/PII is ever serialized into an outbound LLM payload.
- [ ] No fine-tuning on user memory — retrieval-only confirmed (ADR-026).
- [ ] Every derived artifact (embedding/summary/graph node) carries a provenance link.
- [ ] `erase(record)` cascades to all derived artifacts + indexes deterministically (Art. 17).
- [ ] Summaries mixing multiple sources are recomputed, not orphaned, on erasure.
- [ ] No central data store, no processor relationship, no cross-border transfer.
- [ ] No telemetry / silent collection by default ($0-default posture).
- [ ] All durable writes from external content pass injection-scan + sanitization.
- [ ] Records tagged user-asserted vs agent-ingested; memory is human-reviewable and reversible.
- [ ] Records signed; integrity/provenance verifiable.
- [ ] Erasures produce auditable tombstones (accountability, Art. 5(2)).

---

## 9. Opinionated decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | **Redact at app layer, not LLM gateway** | Raw secret never reaches a network component; no gateway honeypot ([TrueFoundry](https://www.truefoundry.com/blog/pii-redaction-llm-gateway-vs-application)) |
| 2 | **Secrets-first tier ordering** (entropy scan before NER) | Secrets are the dominant coding-memory risk; cheap + high-recall |
| 3 | **Defense-in-depth, never a single gate** | MS warns no PII tool catches everything ([Presidio](https://github.com/microsoft/presidio)) |
| 4 | **Redact every outbound payload** | Makes "secrets never leave your machine" literally enforced, not aspirational |
| 5 | **Never fine-tune on user memory (ADR-026)** | Avoids the unsolved machine-unlearning trap ([arXiv:2412.06966](https://arxiv.org/pdf/2412.06966)) |
| 6 | **Treat derived artifacts as personal data** | Embeddings can reconstruct source ⇒ in scope per [EDPB 28/2024](https://www.edpb.europa.eu/news/news/2024/edpb-opinion-ai-models-gdpr-principles-support-responsible-ai_en) |
| 7 | **Provenance-link every derived artifact (ADR-025/026)** | Makes Art. 17 erasure a deterministic cascade, not a heuristic scan |
| 8 | **Local-first as the legal foundation** | Sole controller, no processor, no transfer, no central honeypot |
| 9 | **Untrusted-by-default external ingestion** | Blocks the poisoning promotion path ([Unit 42](https://unit42.paloaltonetworks.com/indirect-prompt-injection-poisons-ai-longterm-memory/)) |
| 10 | **Human-reviewable + reversible + signed memory** | Counters temporally-decoupled "attack that waits" ([MemoryGraft](https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents/)) |
| 11 | **$0-default, no telemetry** | No "sale/sharing" under CCPA; minimization by construction |

---

## Sources

- Microsoft Presidio — https://github.com/microsoft/presidio · https://microsoft.github.io/presidio/
- Yelp detect-secrets — https://github.com/Yelp/detect-secrets
- gitleaks — https://github.com/gitleaks/gitleaks
- TrueFoundry, *PII redaction: LLM gateway vs application* — https://www.truefoundry.com/blog/pii-redaction-llm-gateway-vs-application
- EDPB Opinion 28/2024 (AI models & GDPR) — https://www.edpb.europa.eu/news/news/2024/edpb-opinion-ai-models-gdpr-principles-support-responsible-ai_en
- IAPP, *EDPB on personal data in AI models* — https://iapp.org/news/a/edpb-weighs-in-on-key-questions-on-personal-data-in-ai-models
- *Machine unlearning* survey, arXiv:2412.06966 — https://arxiv.org/pdf/2412.06966
- Google Privacy Sandbox, *DP semantics for ODP* — https://privacysandbox.google.com/protections/on-device-personalization/differential-privacy-semantics-for-odp
- Privacy Guides, *Differential privacy* — https://www.privacyguides.org/articles/2025/09/30/differential-privacy/
- Unit 42 (Palo Alto), *Indirect prompt injection poisons AI long-term memory* — https://unit42.paloaltonetworks.com/indirect-prompt-injection-poisons-ai-longterm-memory/
- Christian Schneider, *Persistent memory poisoning in AI agents* — https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents/
- MemoryGraft, arXiv:2601.05504 — https://arxiv.org/abs/2601.05504
- Lakera, *Agentic AI threats (Part 1)* — https://www.lakera.ai/blog/agentic-ai-threats-p1
