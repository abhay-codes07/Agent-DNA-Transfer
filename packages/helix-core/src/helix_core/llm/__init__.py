"""LLM router (optional). Free-tier-first; the engine works fully without it."""

from .cache import LLMCache, cache_key
from .providers import (
    FakeProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    ProviderError,
    LLMResponse,
)
from .router import BudgetExceeded, LLMResult, LLMRouter, LLMUnavailable, build_providers

__all__ = [
    "LLMRouter",
    "LLMResult",
    "BudgetExceeded",
    "LLMUnavailable",
    "build_providers",
    "LLMCache",
    "cache_key",
    "Provider",
    "ProviderError",
    "LLMResponse",
    "GeminiProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "FakeProvider",
]
