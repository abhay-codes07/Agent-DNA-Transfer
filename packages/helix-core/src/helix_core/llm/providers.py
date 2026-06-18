"""LLM providers (ADR-007, ADR-031).

Thin, dependency-free HTTP clients (stdlib urllib) for the providers the router can use:
Gemini (free-tier-first), OpenAI (gpt-4o-mini fallback), and Ollama (local, $0). LiteLLM can
be swapped in later behind the same Provider interface. A FakeProvider makes the whole LLM
path testable offline with no keys or network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Any provider-side failure (network, auth, rate-limit, bad response)."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@runtime_checkable
class Provider(Protocol):
    name: str
    model: str
    paid: bool

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = True,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


def _post_json(url: str, payload: dict, headers: dict, timeout: float = 30.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise ProviderError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise ProviderError(f"invalid JSON from {url}: {exc}") from exc


class GeminiProvider:
    """Google Gemini (free tier is the default cheap path)."""

    name = "gemini"
    paid = False  # free tier

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._key = api_key
        self.model = model

    def complete(self, prompt, *, system=None, json_mode=True, max_tokens=1024) -> LLMResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self._key}"
        )
        gen: dict = {"maxOutputTokens": max_tokens, "temperature": 0.1}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        payload: dict = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        body = _post_json(url, payload, headers={})
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"unexpected Gemini response: {body}") from exc
        usage = body.get("usageMetadata", {})
        return LLMResponse(
            text, self.model, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0)
        )


class OpenAIProvider:
    """OpenAI chat completions (gpt-4o-mini fallback)."""

    name = "openai"
    paid = True

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._key = api_key
        self.model = model

    def complete(self, prompt, *, system=None, json_mode=True, max_tokens=1024) -> LLMResponse:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}
        ]
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = _post_json(
            "https://api.openai.com/v1/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {self._key}"},
        )
        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ProviderError(f"unexpected OpenAI response: {body}") from exc
        usage = body.get("usage", {})
        return LLMResponse(
            text, self.model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        )


class OllamaProvider:
    """Local LLM via Ollama — better-than-heuristic extraction at $0, fully offline."""

    name = "ollama"
    paid = False

    def __init__(self, model: str = "llama3.2", host: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self._host = host.rstrip("/")

    def complete(self, prompt, *, system=None, json_mode=True, max_tokens=1024) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"
        body = _post_json(f"{self._host}/api/generate", payload, headers={}, timeout=120.0)
        text = body.get("response")
        if text is None:
            raise ProviderError(f"unexpected Ollama response: {body}")
        return LLMResponse(
            text, self.model, body.get("prompt_eval_count", 0), body.get("eval_count", 0)
        )


class FakeProvider:
    """Deterministic, in-memory provider for tests. Records calls; can simulate failure."""

    name = "fake"

    def __init__(
        self, response: str = '{"facts": []}', *, paid: bool = False, fail: bool = False
    ) -> None:
        self.response = response
        self.model = "fake-model"
        self.paid = paid
        self.fail = fail
        self.calls = 0

    def complete(self, prompt, *, system=None, json_mode=True, max_tokens=1024) -> LLMResponse:
        self.calls += 1
        if self.fail:
            raise ProviderError("simulated provider failure")
        return LLMResponse(self.response, "fake-model", prompt_tokens=10, completion_tokens=20)
