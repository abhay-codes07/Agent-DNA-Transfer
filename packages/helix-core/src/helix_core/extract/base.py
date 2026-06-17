"""Extractor interface (TSD §6.2).

Two interchangeable engines behind one Protocol:
  - DeterministicExtractor: rules + embeddings + entity extraction. No key, $0, the floor.
  - LLMExtractor: structured-output prompt, batched. Used only when a key/Ollama is present
    and the gate decided extraction is worthwhile.

Any code path that calls a model MUST keep the deterministic fallback working (CLAUDE.md).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import CandidateFact


@runtime_checkable
class Extractor(Protocol):
    def extract(self, text: str, *, scope: str = "global") -> list[CandidateFact]:
        """Turn a (redacted) slice into candidate typed facts."""
        ...


class DeterministicExtractor:
    """No-LLM extractor — the $0 floor. (Implemented in Phase 1.)"""

    def extract(self, text: str, *, scope: str = "global") -> list[CandidateFact]:
        raise NotImplementedError("Phase 1: rules + embeddings + entity extraction")


class LLMExtractor:
    """LLM-backed extractor via the router. (Implemented in Phase 3.)"""

    def extract(self, text: str, *, scope: str = "global") -> list[CandidateFact]:
        raise NotImplementedError("Phase 3: structured JSON extraction, batched + cached")
