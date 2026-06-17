"""Fact extraction. Deterministic (default, $0) and LLM-backed (optional) engines."""

from .base import Extractor, LLMExtractor
from .deterministic import DeterministicExtractor

__all__ = ["Extractor", "DeterministicExtractor", "LLMExtractor"]
