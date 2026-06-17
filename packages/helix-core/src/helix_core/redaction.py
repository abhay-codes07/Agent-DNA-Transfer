"""Secret redaction — runs BEFORE any storage or model call (an invariant).

Removes API keys, tokens, private keys, and .env-style values so secrets never enter a
strand or reach an LLM provider. See docs/SECURITY_MODEL.md §5.

Pre-alpha: a representative starter ruleset. The real implementation adds entropy-based
detection and a configurable deny-list, and is covered by tests that assert no secret ever
reaches a strand.
"""

from __future__ import annotations

import re

REDACTION_PLACEHOLDER = "«redacted»"

# Starter patterns (extended in Phase 1). Order matters; most specific first.
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google API keys
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub tokens
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END[^\n]+-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*\S+"),
]


def redact(text: str) -> str:
    """Return text with detected secrets replaced by a placeholder."""
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTION_PLACEHOLDER, text)
    return text


def contains_secret(text: str) -> bool:
    """Cheap check used by tests/guards to assert the invariant holds."""
    return any(p.search(text) for p in _PATTERNS)
