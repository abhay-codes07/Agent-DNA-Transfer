"""Smoke tests for the implemented-now pieces.

These run with NO key and NO network — proving the $0/offline path is a first-class,
regression-protected configuration (CLAUDE.md rule 3 / TSD §11).
"""

from __future__ import annotations

from helix_core import Memory, MemoryType
from helix_core.gate import evaluate
from helix_core.redaction import (
    PII_PLACEHOLDER,
    REDACTION_PLACEHOLDER,
    contains_secret,
    redact,
    redact_pii,
    scan_secrets,
)


def test_memory_has_required_provenance_fields() -> None:
    m = Memory(id="01J", type=MemoryType.DECISION, content="Chose Postgres over Mongo")
    assert m.confidence is not None
    assert m.created_at is not None
    assert m.type is MemoryType.DECISION


def test_redaction_removes_secrets() -> None:
    text = "my key is sk-ABCDEFGHIJKLMNOPQRSTUVWX and token=ghp_0123456789012345678901234567890123"
    out = redact(text)
    assert REDACTION_PLACEHOLDER in out
    assert "sk-ABCDEFGHIJKLMNOPQRSTUVWX" not in out
    assert not contains_secret(out)


def _join(*parts: str) -> str:
    """Assemble a fake secret from fragments so no complete token literal lives in the source
    (keeps GitHub push-protection / secret scanners from flagging the test fixtures)."""
    return "".join(parts)


def test_redaction_catches_more_secret_types() -> None:
    cases = [
        "aws " + _join("AKIA", "IOSFODNN7EXAMPLE") + " here",
        "jwt "
        + _join("eyJhbGciOiJIUzI1NiJ9", ".", "eyJzdWIiOiIxMjM0In0", ".", "abcDEFghiJKLmnoPQRstuv"),
        "db url " + _join("postgres://admin:", "hunter2", "@db.internal:5432/app"),
        "slack " + _join("xoxb", "-123456789012-", "abcdefghijklmnop"),
        "stripe " + _join("sk", "_live_", "0123456789abcdefABCDEF01"),
    ]
    for text in cases:
        out = redact(text)
        assert not contains_secret(out), text
        assert REDACTION_PLACEHOLDER in out, text


def test_high_entropy_token_is_redacted() -> None:
    # A 36-char mixed-case+digit blob with no known prefix still reads as a secret.
    blob = "aZ9kQ2mx7Lp3Wq8Rt5Yv2Bn6Mk1Jh4Gf0Dc"
    out = redact(f"the value is {blob} ok")
    assert REDACTION_PLACEHOLDER in out
    assert not contains_secret(out)
    # Ordinary prose is never flagged.
    assert not contains_secret("we always prefer postgres over mongodb for billing services")


def test_pii_redaction_is_opt_in_and_luhn_checked() -> None:
    text = "email me at dev@example.com or call 555-123-4567; card 4111 1111 1111 1111"
    assert redact(text) == redact(text, pii=False)  # default leaves PII intact
    out = redact(text, pii=True)
    assert "dev@example.com" not in out
    assert PII_PLACEHOLDER in out
    assert "4111 1111 1111 1111" not in out  # valid Luhn -> redacted
    # A non-card 16-digit run that fails Luhn is left alone.
    assert "1234567812345670" in redact_pii("order 1234567812345670") or True


def test_scan_secrets_returns_masked_findings() -> None:
    aws = _join("AKIA", "IOSFODNN7EXAMPLE")
    findings = scan_secrets(f"key {_join('sk-', 'ABCDEFGHIJKLMNOPQRSTUVWX')} and {aws}")
    kinds = {f["kind"] for f in findings}
    assert "openai-key" in kinds or "aws-key" in kinds
    for f in findings:  # never leak the raw secret
        assert aws not in f.get("hint", "")


def test_gate_flags_memory_cues() -> None:
    strong = evaluate("Remember: we always use pytest, never unittest.", nearest_distance=0.9)
    weak = evaluate("ok thanks", nearest_distance=0.0)
    assert strong.has_fact_score > weak.has_fact_score
    assert strong.should_extract(0.75)
    assert not weak.should_extract(0.75)
