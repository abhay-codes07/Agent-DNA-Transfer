"""Wave A — reranking (§2.1) and sleep-time consolidation (§1.2). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.models import Cognitive, Hit, Memory, MemoryType, utcnow
from helix_core.rerank import LexicalReranker, apply_rerank


def _mem(mid: str, content: str) -> Memory:
    now = utcnow()
    return Memory(
        id=mid,
        type=MemoryType.FACT,
        content=content,
        cognitive=Cognitive.SEMANTIC,
        valid_from=now,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )


def test_lexical_reranker_rewards_query_coverage():
    r = LexicalReranker()
    scores = r.score(
        "billing database postgres",
        ["we chose postgres for the billing database", "the weather is nice today"],
    )
    assert scores[0] > scores[1]


def test_apply_rerank_reorders_by_relevance():
    hits = [
        Hit(memory=_mem("h1", "alpha beta gamma unrelated"), score=0.9),
        Hit(memory=_mem("h2", "billing database postgres acid"), score=0.3),
    ]
    out = apply_rerank(LexicalReranker(), "billing database postgres", hits, k=2)
    assert out[0].memory.id == "h2"  # strong lexical match wins despite a lower base score


def test_engine_recall_with_rerank_runs(tmp_path):
    eng = Engine(Config(home=tmp_path, rerank=True))
    eng.remember("We chose Postgres over Mongo for the billing service.", scope="project:billing")
    eng.remember("All API errors use RFC-7807.", scope="project:billing")
    hits = eng.recall("which database for billing", scope="project:billing", k=5, rerank=True)
    assert hits
    assert any("Postgres" in h.memory.content for h in hits)
    eng.close()


def test_consolidate_sleep_promotes_reinforced_episode(tmp_path):
    eng = Engine(Config(home=tmp_path))
    ep = _mem("ep1", "Debugged the flaky billing test by pinning the clock")
    ep.type = MemoryType.EPISODE
    ep.cognitive = Cognitive.EPISODIC
    ep.attributes["_reinforced"] = 3  # recalled several times -> ready to semanticize
    with eng.store.tx():
        eng.store.upsert_memory(ep, [0.0])
    res = eng.consolidate_sleep(reflect=False)
    assert res["promoted"] == 1
    got = eng.store.get_memory("ep1")
    assert got.cognitive == Cognitive.SEMANTIC
    assert got.type == MemoryType.FACT
    assert got.attributes.get("_consolidated") is True
    # Running again is idempotent (already consolidated).
    assert eng.consolidate_sleep(reflect=False)["promoted"] == 0
    eng.close()
