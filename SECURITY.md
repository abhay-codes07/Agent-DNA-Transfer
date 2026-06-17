# Security Policy

Helix stores a user's most personal asset — their accumulated context and decisions — on
their own device. Security is foundational, not a feature. The full threat model lives in
[`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md); this file is the disclosure policy.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email the maintainers at **security@helix.dev** (placeholder — update before
launch) with:

- a description of the issue and its impact,
- steps to reproduce or a proof of concept,
- affected versions/components,
- any suggested remediation.

We aim to acknowledge within **72 hours** and to provide a remediation timeline within
**7 days**. Please give us a reasonable disclosure window before going public. We credit
reporters (unless you prefer to stay anonymous).

## Scope

In scope: the engine, CLI, MCP server, SDKs, `.dna` format, and crypto handling.
Especially interested in:

- ways to decrypt or forge a `.dna` strand without the key,
- signature bypasses on the manifest,
- secret/key leakage (logs, strands, telemetry, crash dumps),
- MCP surface abuse (a malicious agent exfiltrating memory it shouldn't),
- merge/import paths that corrupt or poison a strand.

Out of scope (for now): hosted/cloud sync (not yet built), social-engineering, and issues
requiring a fully compromised host.

## Our commitments

- Strands are encrypted at rest (XChaCha20-Poly1305; key via Argon2id from passphrase or
  device keychain).
- Manifests are signed (Ed25519); imports verify signatures before trusting content.
- Secrets are read from the environment only and are never logged, persisted, or written
  into a strand.
- Telemetry is **off by default** and local-only when enabled.
