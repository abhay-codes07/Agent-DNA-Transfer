"""LLM router — free-tier-first, optional, cached, budgeted (ADR-007, ADR-031).

Policy:
  1. If no provider/key -> not available; callers use the deterministic path. $0.
  2. Prefer Gemini 2.0 Flash (free tier); fall back to gpt-4o-mini; or local Ollama.
  3. Cache by hash(model, system, prompt) so identical work is never paid for twice.
  4. A monthly token budget hard-caps PAID usage; when exhausted, paid providers are skipped
     and the caller degrades to deterministic extraction (never blocks, never overspends).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import Config
from .cache import LLMCache, cache_key
from .providers import (
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    ProviderError,
)


class LLMUnavailable(RuntimeError):
    """No provider could satisfy the request (none configured, or all failed)."""


class BudgetExceeded(RuntimeError):
    """A paid call would exceed HELIX_MONTHLY_TOKEN_BUDGET and no free path remained."""


@dataclass(slots=True)
class LLMResult:
    text: str
    model: str
    cached: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def build_providers(config: Config) -> list[Provider]:
    provs: list[Provider] = []
    p = config.llm_provider
    if p == "gemini" and config.gemini_api_key:
        provs.append(GeminiProvider(config.gemini_api_key, config.gemini_model))
    elif p == "openai" and config.openai_api_key:
        provs.append(OpenAIProvider(config.openai_api_key, config.openai_model))
    elif p == "ollama":
        provs.append(OllamaProvider())
    # gpt-4o-mini as a fallback if a key is present and it isn't already primary
    if config.openai_api_key and not any(isinstance(x, OpenAIProvider) for x in provs):
        provs.append(OpenAIProvider(config.openai_api_key, config.openai_model))
    return provs


class LLMRouter:
    def __init__(
        self,
        config: Config,
        *,
        cache: LLMCache | None = None,
        providers: list[Provider] | None = None,
    ) -> None:
        self.config = config
        self.cache = cache
        self.providers = providers if providers is not None else build_providers(config)
        self.tokens_used = 0  # in-memory tally for this process

    def available(self) -> bool:
        return len(self.providers) > 0

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = True,
        max_tokens: int = 1024,
    ) -> LLMResult:
        if not self.providers:
            raise LLMUnavailable("no LLM provider configured")
        budget = self.config.monthly_token_budget
        month = _month()
        budget_blocked = False
        last_err: Exception | None = None

        for provider in self.providers:
            key = cache_key(provider.model, prompt, system)
            if self.cache:
                hit = self.cache.get(key)
                if hit is not None:
                    return LLMResult(hit, provider.model, cached=True)
            if provider.paid and budget > 0:
                used = self.cache.tokens_this_month(month) if self.cache else self.tokens_used
                if used >= budget:
                    budget_blocked = True
                    continue
            try:
                resp = provider.complete(
                    prompt, system=system, json_mode=json_mode, max_tokens=max_tokens
                )
            except ProviderError as exc:
                last_err = exc
                continue
            total = resp.prompt_tokens + resp.completion_tokens
            self.tokens_used += total
            if self.cache:
                self.cache.put(key, resp.text)
                if provider.paid:
                    self.cache.add_tokens(month, total)
            return LLMResult(
                resp.text,
                resp.model,
                cached=False,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
            )

        if budget_blocked and last_err is None:
            raise BudgetExceeded(f"monthly token budget {budget} reached")
        raise LLMUnavailable(f"all providers failed: {last_err}")
