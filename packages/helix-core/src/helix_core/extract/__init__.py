"""Fact extraction. Deterministic (default, $0) and LLM-backed (optional) engines."""

from .base import Extractor
from .deterministic import DeterministicExtractor
from .llm import LLMExtractor

__all__ = ["Extractor", "DeterministicExtractor", "LLMExtractor"]
