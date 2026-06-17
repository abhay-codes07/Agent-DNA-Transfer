"""Smoke tests for the implemented-now pieces.

These run with NO key and NO network — proving the $0/offline path is a first-class,
regression-protected configuration (CLAUDE.md rule 3 / TSD §11).
"""

from __future__ import annotations

from helix_core import Memory, MemoryType
from helix_core.gate import evaluate
from helix_core.redaction import REDACTION_PLACEHOLDER, contains_secret, redact


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


def test_gate_flags_memory_cues() -> None:
    strong = evaluate("Remember: we always use pytest, never unittest.", nearest_distance=0.9)
    weak = evaluate("ok thanks", nearest_distance=0.0)
    assert strong.has_fact_score > weak.has_fact_score
    assert strong.should_extract(0.75)
    assert not weak.should_extract(0.75)
