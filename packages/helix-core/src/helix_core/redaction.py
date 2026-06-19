"""Secret + PII redaction — runs BEFORE any storage or model call (an invariant).

Removes API keys, tokens, private keys, connection strings, and (optionally) PII so secrets
never enter a strand or reach an LLM provider. See docs/SECURITY_MODEL.md §5 and ADR-025.

Two layers:
  * **Secrets** are ALWAYS redacted (high-confidence patterns + a conservative entropy gate).
    This is the hard, non-negotiable gate — `contains_secret` must be False after `redact`.
  * **PII** (emails, phones, card numbers, IPs, SSNs) is redacted when `pii=True`
    (the engine default, gated by `Config.redact_pii`). Card numbers are Luhn-checked to
    cut false positives.

Stdlib-only, deterministic, $0. `scan_secrets` adds an advisory entropy sweep for the
review queue / gate logging without changing the round-trip guarantee.
"""

from __future__ import annotations

import math
import re

REDACTION_PLACEHOLDER = "«redacted»"
PII_PLACEHOLDER = "«pii»"

# --- secret patterns (high-confidence; order matters, most specific first) ---
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----[\s\S]+?-----END[^\n]+-----"
    ),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),  # OpenAI (incl. project keys)
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google API keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),  # GitHub PAT / OAuth / refresh / server tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{60,}"),  # GitHub fine-grained PAT
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),  # Stripe
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),  # AWS temporary access key id
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"\bxapp-[0-9]-[A-Za-z0-9-]{10,}\b"),  # Slack app-level token
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),  # GitLab PAT
    re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),  # npm token
    re.compile(r"\bdop_v1_[a-f0-9]{64}\b"),  # DigitalOcean token
    re.compile(r"\bSG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b"),  # SendGrid
    re.compile(r"[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@[^\s]+"),  # creds in a connection URI
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b\s*[:=]\s*\S+"
    ),
]
# Back-compat alias (older imports referenced _PATTERNS).
_PATTERNS = _SECRET_PATTERNS

# --- PII patterns (only redacted when pii=True) ---
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3}[\s.-]?\d{4}(?!\d)")
_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")  # candidate card; Luhn-checked before redacting

# Tokens this long with high entropy and a mixed charset look like secrets even without a
# known prefix. Conservative thresholds keep English prose and IDs/hashes from tripping.
_ENTROPY_MIN_LEN = 24
_ENTROPY_MIN_BITS = 4.0
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=-]{%d,}" % _ENTROPY_MIN_LEN)


def _shannon(s: str) -> float:
    """Shannon entropy (bits per char) of a string."""
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _mixed_charset(s: str) -> bool:
    return bool(re.search(r"[a-z]", s)) and bool(re.search(r"[A-Z0-9]", s))


def _looks_secret(tok: str) -> bool:
    return (
        len(tok) >= _ENTROPY_MIN_LEN and _mixed_charset(tok) and _shannon(tok) >= _ENTROPY_MIN_BITS
    )


def _luhn_ok(digits: str) -> bool:
    ds = [int(c) for c in digits if c.isdigit()]
    if not 13 <= len(ds) <= 19:
        return False
    total, parity = 0, len(ds) % 2
    for i, d in enumerate(ds):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact(text: str, *, pii: bool = False, entropy: bool = True) -> str:
    """Return text with detected secrets (and, if `pii`, PII) replaced by placeholders.

    `entropy=True` also masks high-entropy secret-looking tokens that match no known prefix.
    """
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTION_PLACEHOLDER, text)
    if entropy:
        text = _TOKEN_RE.sub(
            lambda m: REDACTION_PLACEHOLDER if _looks_secret(m.group(0)) else m.group(0), text
        )
    if pii:
        text = redact_pii(text)
    return text


def redact_pii(text: str) -> str:
    """Redact common PII. Card numbers are Luhn-validated to avoid masking ordinary digit runs."""
    text = _EMAIL.sub(PII_PLACEHOLDER, text)
    text = _SSN.sub(PII_PLACEHOLDER, text)
    text = _CARD.sub(lambda m: PII_PLACEHOLDER if _luhn_ok(m.group(0)) else m.group(0), text)
    text = _IPV4.sub(PII_PLACEHOLDER, text)
    text = _PHONE.sub(PII_PLACEHOLDER, text)
    return text


def contains_secret(text: str) -> bool:
    """True if a known-pattern OR high-entropy secret remains. Round-trips with `redact`."""
    if any(p.search(text) for p in _SECRET_PATTERNS):
        return True
    return any(_looks_secret(t) for t in _TOKEN_RE.findall(text))


def scan_secrets(text: str) -> list[dict[str, str]]:
    """Advisory sweep: list detected secrets with a masked preview (for gate logs / review).

    Never returns the raw secret — only its kind and a short masked hint.
    """
    findings: list[dict[str, str]] = []
    names = [
        "private-key",
        "openai-key",
        "google-key",
        "github-token",
        "github-pat-fine",
        "slack-token",
        "stripe-key",
        "aws-key",
        "aws-temp-key",
        "jwt",
        "slack-app-token",
        "gitlab-pat",
        "npm-token",
        "do-token",
        "sendgrid-key",
        "connection-uri",
        "assignment",
    ]
    for name, pattern in zip(names, _SECRET_PATTERNS):
        if pattern.search(text):
            findings.append({"kind": name, "hint": "«detected»"})
    for tok in _TOKEN_RE.findall(text):
        if _looks_secret(tok):
            findings.append({"kind": "high-entropy", "hint": tok[:4] + "…" + tok[-2:]})
    return findings
