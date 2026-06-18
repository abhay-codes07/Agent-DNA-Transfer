"""Phase 3 tests: the optional LLM router + extractor.

Fully offline via FakeProvider — no keys, no network. Proves the $0 default is unchanged and
that every LLM path degrades safely (cache, budget, provider failure).
"""

from __future__ import annotations

import pytest

from helix_core.config import Config
from helix_core.engine import Engine
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


# --- gray-band consolidation adjudication (ADR-034) ---


def _engine_with_verdict(tmp_path, relation: str) -> Engine:
    eng = Engine(Config(home=tmp_path))
    eng.remember("We use MongoDB for the billing service.", scope="project:b")
    eng.router = LLMRouter(Config(), providers=[FakeProvider('{"relation": "%s"}' % relation)])
    return eng


def test_consolidation_llm_adjudicates_contradiction_as_supersede(tmp_path):
    eng = _engine_with_verdict(tmp_path, "contradict")
    r = eng.remember("We use Postgres for the billing service.", scope="project:b")
    assert r[0].op == "SUPERSEDE"  # LLM said the new fact replaces the old one
    actives = [m for m in eng.list_memories() if "billing service" in m.content.lower()]
    assert len(actives) == 1 and "postgres" in actives[0].content.lower()
    eng.close()


def test_consolidation_llm_distinct_keeps_both(tmp_path):
    eng = _engine_with_verdict(tmp_path, "distinct")
    r = eng.remember("We use Postgres for the billing service.", scope="project:b")
    assert r[0].op == "ADD"  # LLM said it's a different fact -> keep both
    actives = [m for m in eng.list_memories() if "billing service" in m.content.lower()]
    assert len(actives) == 2
    eng.close()


# --- batched extraction (one LLM call for many slices) ---


def test_llm_extract_batch_uses_a_single_call():
    resp = (
        '{"notes": ['
        '{"i": 0, "facts": [{"type": "decision", "content": "Chose Postgres"}]},'
        '{"i": 1, "facts": [{"type": "preference", "content": "Prefers pytest"}]}]}'
    )
    fake = FakeProvider(resp)
    ex = LLMExtractor(LLMRouter(Config(), providers=[fake]))
    out = ex.extract_batch(
        ["we decided on postgres for billing", "i really prefer pytest"], scope="g", force=True
    )
    assert len(out) == 2
    assert out[0][0].content == "Chose Postgres" and out[0][0].type.value == "decision"
    assert out[1][0].content == "Prefers pytest"
    assert fake.calls == 1  # ONE model call for both notes (cost lever)


def test_deterministic_extract_batch_maps_over_inputs():
    from helix_core.extract.deterministic import DeterministicExtractor

    out = DeterministicExtractor().extract_batch(
        ["We use Postgres for billing.", "We deploy on Fridays."], scope="g", force=True
    )
    assert len(out) == 2 and out[0] and out[1]


# --- reflection (insight synthesis, ADR-015) ---


def test_reflect_synthesizes_a_cited_insight_with_llm(tmp_path):
    eng = Engine(Config(home=tmp_path))
    eng.remember("We use Postgres for the billing service.", scope="project:b")
    eng.remember("We use FastAPI for the billing service.", scope="project:b")
    eng.remember("We deploy the billing service on Fly.io.", scope="project:b")
    eng.router = LLMRouter(
        Config(),
        providers=[
            FakeProvider(
                '{"insights": ["The billing service is a FastAPI app on Postgres, deployed to Fly.io."]}'
            )
        ],
    )
    res = eng.reflect(scope="project:b", min_cluster=3)
    assert res["insights"] >= 1

    reflections = [
        m for m in eng.list_memories(scope="project:b") if m.attributes.get("_reflection")
    ]
    assert reflections
    assert "fastapi" in reflections[0].content.lower()
    assert reflections[0].attributes.get("sources")  # cites its grounding memories
    eng.close()


def test_reflect_makes_no_insights_without_an_llm(tmp_path):
    eng = Engine(Config(home=tmp_path))
    for fact in ("alpha fact about caching", "beta fact about caching", "gamma fact about caching"):
        eng.remember(fact, scope="project:b")
    res = eng.reflect(scope="project:b", min_cluster=3)
    assert res["insights"] == 0  # deterministic mode: NL synthesis needs a model
    eng.close()
