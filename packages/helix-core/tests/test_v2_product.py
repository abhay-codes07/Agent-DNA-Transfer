"""Wave A — copilot (about) + observability (analytics, $0 meter). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine


def _eng(tmp_path) -> Engine:
    eng = Engine(Config(home=tmp_path))
    eng.remember("We chose Postgres over Mongo for the billing service.", scope="project:billing")
    eng.remember("All API errors use RFC-7807.", scope="project:billing")
    eng.remember("I prefer pytest over unittest.")
    return eng


def test_about_returns_sourced_facts(tmp_path):
    eng = _eng(tmp_path)
    ans = eng.about("which database for billing")
    assert ans["count"] >= 1
    f = ans["facts"][0]
    assert {"content", "source", "stale", "conflict", "confidence"} <= set(f)
    eng.close()


def test_analytics_snapshot_has_expected_shape(tmp_path):
    eng = _eng(tmp_path)
    a = eng.analytics()
    assert a["total"] >= 3
    assert isinstance(a["by_type"], dict) and sum(a["by_type"].values()) == a["total"]
    assert a["facts_per_day"]  # at least one day bucket
    assert "to_review" in a and "tombstones" in a
    eng.close()


def test_savings_meter_counts_local_work(tmp_path):
    eng = _eng(tmp_path)
    s = eng.savings()
    assert s["local_embeddings"] >= 3
    assert s["est_usd_saved"] > 0
    assert s["llm_enabled"] is False  # $0 default
    eng.close()
