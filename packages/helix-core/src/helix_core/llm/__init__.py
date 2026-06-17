"""LLM router (optional). Free-tier-first; the engine works fully without it."""

from .router import BudgetExceeded, LLMResult, LLMRouter

__all__ = ["LLMRouter", "LLMResult", "BudgetExceeded"]
