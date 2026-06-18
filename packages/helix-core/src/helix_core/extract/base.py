"""Extractor interface (TSD §6.2).

Two interchangeable engines behind one Protocol:
  - DeterministicExtractor (deterministic.py): rules + cues. No key, $0, the floor.
  - LLMExtractor (llm.py): structured-output prompt via the router, with deterministic fallback.

Any code path that calls a model MUST keep the deterministic fallback working (CLAUDE.md).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import CandidateFact


@runtime_checkable
class Extractor(Protocol):
    def extract(
        self, text: str, *, scope: str = "global", force: bool = False
    ) -> list[CandidateFact]:
        """Turn a (redacted) slice into candidate typed facts."""
        ...

    def extract_batch(
        self, texts: list[str], *, scope: str = "global", force: bool = False
    ) -> list[list[CandidateFact]]:
        """Extract from many slices at once (LLM: one call; deterministic: a loop)."""
        ...
