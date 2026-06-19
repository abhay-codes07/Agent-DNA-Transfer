# Portable Agent Memory — an open standard ("USB for AI memory")

> Status: **Draft 1.0** · v2 plan §8. A vendor-neutral interchange format for moving an AI
> agent's memory between tools. Reference implementation: Helix (`helix export-portable`,
> `helix conform`, and `helix_core.standard`). The validator is pure stdlib so any project can
> vendor it.

## Why

Agent memory today is trapped — each vendor stores it in an opaque, proprietary way, and there's
no "export my brain and import it elsewhere." MCP standardized how agents *talk to* a memory
service, but deliberately does **not** standardize a portable memory *artifact*. This spec fills
that gap: a simple, human-readable JSON record format any tool can read or write, plus optional
integrity and signatures, plus an encrypted container for transport.

## Layers

1. **Record format** (this doc) — open JSON. The unit of interchange.
2. **Integrity** — a BLAKE2b Merkle root over per-fact fingerprints; tamper-evident.
3. **Signatures** — per-fact Ed25519 signatures; attributable, verifiable after a merge.
4. **Container** — the encrypted, signed `.dna` strand (XChaCha20-Poly1305 + Ed25519) for
   confidential transport. Out of scope for the JSON validator; Helix's `.dna` codec is the
   reference. (See [`DNA_FORMAT.md`](DNA_FORMAT.md).)

## Conformance levels

| Level | Requirement |
|---|---|
| **core** | Well-formed bundle; every record has `id`, `type`, `content`, `created_at`, `provenance`. |
| **signed** | Core **+** every record carries a verifiable `signature` **and** the bundle has a Merkle `integrity` root. |
| **encrypted** | Delivered inside a `.dna` container. |

## Bundle schema

```jsonc
{
  "format": "portable-agent-memory",   // required, exact
  "version": "1.0",                     // required
  "generator": "helix/0.1.0",           // who wrote it
  "created_at": "2026-06-20T12:00:00+00:00",
  "memories": [ /* records */ ],        // required, list
  "edges": [                            // optional: typed relations
    { "from": "<id>", "to": "<id>", "relation": "related_to" }
  ],
  "integrity": {                        // optional; required for "signed"
    "algo": "blake2b",
    "merkle_root": "<hex>"
  }
}
```

## Record schema

```jsonc
{
  "id": "<stable id>",                  // required
  "type": "decision",                   // required; one of the typed vocabulary below
  "content": "We chose Postgres…",      // required; the distilled, human-readable fact
  "scope": "project:billing",           // "global" or "project:<id>"
  "confidence": 0.8,                     // 0..1
  "importance": 0.7,                     // 0..1
  "valid_from": "2026-01-01T…",         // bi-temporal: when true in the world
  "valid_to": null,                      // null = still valid; set when superseded
  "created_at": "2026-01-01T…",         // required; transaction time
  "provenance": [                        // required (may be empty list); the chain of belief
    { "agent": "claude-code", "extractor": "deterministic", "origin": "user-asserted" }
  ],
  "signature": {                         // optional; required for "signed"
    "scheme": "ed25519",                 // or "local-mac"
    "signer": "<pubkey hex / key id>",
    "sig": "<hex>"
  }
}
```

### Typed vocabulary (`type`)

`identity · preference · project · decision · entity · convention · snippet · procedure ·
episode · fact`

A consumer that doesn't recognize a type SHOULD preserve it verbatim (forward-compatibility).

## Rules

- `format` MUST equal `portable-agent-memory`; unknown top-level keys MUST be preserved on
  round-trip, not dropped.
- Every record MUST carry `provenance` (possibly empty) — memory without a source is not portable
  trust. Producers SHOULD redact secrets/PII from `content` before export.
- `valid_from`/`valid_to` express bi-temporality; `created_at` is transaction time. A point-in-time
  view ("what did the agent believe on date D") selects records with `valid_from <= D` and
  (`valid_to` is null or `> D`).
- For **signed** bundles, `signature.sig` MUST verify over the canonical payload
  `"{type}|{content.strip()}"` using `signer`, and `integrity.merkle_root` MUST equal the BLAKE2b
  Merkle root (sorted leaves) of the per-record fingerprints `blake2b("{type}|{content.lower()}")`.

## Reference tooling (Helix)

```bash
helix export-portable mybrain.json          # write a conformant bundle (level: core)
helix export-portable mybrain.json --sign   # sign every fact (level: signed)
helix conform mybrain.json                  # validate any file against this standard
```

Programmatic: `helix_core.standard.validate(doc)` → `{valid, level, errors, count}` (pure stdlib).

## Prior art

Mirrors and extends the *Portable Agent Memory* research direction (arXiv 2605.11032): a typed,
provenance-bearing, signable memory artifact. Helix's contribution is a concrete, implemented,
encrypt-at-rest reference plus a reusable conformance validator — turning the idea into something
other tools can actually adopt.
