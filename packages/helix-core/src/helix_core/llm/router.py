"""LLM router — free-tier-first, and OPTIONAL (ADR-007, docs/COST_OPTIMIZATION.md §4).

Policy:
  1. If no provider/key -> deterministic path (caller falls back). $0.
  2. Prefer Gemini 2.0 Flash (free tier).
  3. Fall back to gpt-4o-mini on rate-limit/unavailable, or if the user prefers it.
  4. On any failure -> signal the caller to use the deterministic extractor. Never block.

Every call is cached (hash of prompt+inputs), batched where possible, and emitted as
structured JSON to minimize tokens. A monthly token budget can hard-disable paid calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config


@dataclass(slots=True)
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False


class BudgetExceeded(RuntimeError):
    """Raised when a paid call would exceed HELIX_MONTHLY_TOKEN_BUDGET."""


class LLMRouter:
    """Routes structured extraction/consolidation calls. Implemented in Phase 3."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def available(self) -> bool:
        """True only if the user opted into a provider and supplied a key."""
        return self._config.llm_enabled()

    def complete(self, prompt: str, *, json_schema: dict | None = None) -> LLMResult:
        """Run a structured completion via LiteLLM with cache + fallback.

        Raises BudgetExceeded when paid usage would exceed the configured ceiling, so the
        caller can degrade to the deterministic path instead of spending.
        """
        raise NotImplementedError(
            "Phase 3: LiteLLM call with cache(hash) -> Gemini free tier -> gpt-4o-mini"
        )
