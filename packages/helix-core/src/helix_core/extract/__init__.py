"""Fact extraction. Deterministic (default, $0) and LLM-backed (optional) engines."""

from .base import DeterministicExtractor, Extractor, LLMExtractor

__all__ = ["Extractor", "DeterministicExtractor", "LLMExtractor"]
