"""Phase 3 tests: the optional LLM router + extractor.

Fully offline via FakeProvider — no keys, no network. Proves the $0 default is unchanged and
that every LLM path degrades safely (cache, budget, provider failure).
"""

from __future__ import annotations

import pytest

from helix_core.config import Config
from helix_core.extract.llm import LLMExtractor
from helix_core.llm.cache import LLMCache
from helix_core.llm.providers import FakeProvider
from helix_core.llm.router import (
    BudgetExceeded,
    LLMRouter,
    LLMUnavailable,
    build_providers,
)


# --- router ---

def test_router_unavailable_without_providers():
    r = LLMRouter(Config(), providers=[])
    assert r.available() is False
    with pytest.raises(LLMUnavailable):
        r.complete("anything")


def test_router_complete_counts_tokens():
    fake = FakeProvider('{"facts": []}')
    r = LLMRouter(Config(), providers=[fake])
    res = r.complete("extract this")
    assert res.text == '{"facts": []}' and res.cached is False
    assert r.tokens_used == 30  # 10 prompt + 20 completion
    assert fake.calls == 1


def test_router_cache_pays_once(tmp_path):
    fake = FakeProvider('{"ok": 1}')
    r = LLMRouter(Config(), cache=LLMCache(tmp_path / "c.db"), providers=[fake])
    a = r.complete("same prompt")
    b = r.complete("same prompt")
    assert a.cached is False and b.cached is True
    assert fake.calls == 1  # second answer came from cache


def test_router_budget_blocks_paid(tmp_path):
    paid = FakeProvider('{"ok": 1}', paid=True)
    cfg = Config(monthly_token_budget=25)
    r = LLMRouter(cfg, cache=LLMCache(tmp_path / "c.db"), providers=[paid])
    r.complete("first")  # consumes 30 tokens (> budget of 25)
    with pytest.raises(BudgetExceeded):
        r.complete("second")
    assert paid.calls == 1  # the over-budget call was never made


def test_build_providers_free_tier_first(monkeypatch):
    monkeypatch.setenv("HELIX_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    assert [p.name for p in build_providers(Config())] == ["gemini", "openai"]

    monkeypatch.setenv("HELIX_LLM_PROVIDER", "none")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert build_providers(Config()) == []


def test_config_llm_enabled_for_ollama(monkeypatch):
    monkeypatch.setenv("HELIX_LLM_PROVIDER", "ollama")
    assert Config().llm_enabled() is True


# --- extractor ---

def test_llm_extractor_parses_structured_facts():
    resp = (
        '{"facts": ['
        '{"type": "decision", "content": "Chose Postgres for billing", "importance": 0.9},'
        '{"type": "preference", "content": "Prefers pytest"}]}'
    )
    ex = LLMExtractor(LLMRouter(Config(), providers=[FakeProvider(resp)]))
    facts = ex.extract("we decided postgres; I prefer pytest", scope="project:b", force=True)
    assert len(facts) == 2
    assert facts[0].type.value == "decision"
    assert facts[0].importance == 0.9
    assert facts[0].scope == "project:b"


def test_llm_extractor_falls_back_on_provider_failure():
    ex = LLMExtractor(LLMRouter(Config(), providers=[FakeProvider(fail=True)]))
    facts = ex.extract("We decided to adopt trunk-based development.", scope="g", force=True)
    assert len(facts) >= 1  # deterministic fallback still produced a fact


def test_llm_extractor_gate_skips_chatter_without_calling_model():
    fake = FakeProvider('{"facts": []}')
    ex = LLMExtractor(LLMRouter(Config(), providers=[fake]), cutoff=0.75)
    assert ex.extract("ok thanks!", scope="g", force=False) == []
    assert fake.calls == 0  # the heuristic gate prevented a paid call (cost lever)
