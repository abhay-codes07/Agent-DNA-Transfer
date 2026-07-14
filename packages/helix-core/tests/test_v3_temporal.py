"""v3 Wave B — temporal reasoning, skill distillation, and the v3 eval metrics. Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine, _is_temporal
from helix_core.models import MemoryType, Status


def _eng(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


# --- temporal query detection + superseded recall -------------------------
def test_is_temporal_detection():
    assert _is_temporal("what did we use before for the database")
    assert _is_temporal("when did we migrate off Heroku")
    assert _is_temporal("history of the deploy target")
    assert not _is_temporal("what database do we use")


def test_temporal_recall_admits_superseded(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("The billing database is MongoDB.", scope="project:billing")
    eng.remember("The billing database is Postgres, not MongoDB.", scope="project:billing")
    # A superseded fact should exist now.
    supers = eng.store.all_memories(statuses=(Status.SUPERSEDED.value,), limit=100)
    assert supers, "expected the old belief to be superseded"

    # Plain recall returns only active facts; a temporal query admits the superseded one.
    plain = [h.memory.status for h in eng.recall("billing database", scope="project:billing")]
    assert all(s == Status.ACTIVE for s in plain)
    temporal = eng.recall(
        "what did the billing database use to be", scope="project:billing", temporal=True
    )
    assert any(h.memory.status == Status.SUPERSEDED for h in temporal)
    eng.close()


# --- change_summary (§2.3) -------------------------------------------------
def test_change_summary_builds_arc(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("We deploy on Heroku.", scope="project:ops")
    eng.remember("We deploy on Fly.io, not Heroku.", scope="project:ops")
    summ = eng.change_summary("deploy")
    assert summ["subject"] == "deploy"
    assert summ["llm"] is False  # deterministic path with no LLM configured
    # Either an arc (if a supersedes edge formed) or the current belief.
    assert isinstance(summ["summary"], str)
    eng.close()


# --- skill distillation (§1.4) --------------------------------------------
def test_distill_skill_only_on_success(tmp_path):
    eng = _eng(tmp_path)
    assert eng.distill_skill("x", [], succeeded=True) is None  # no steps
    assert eng.distill_skill("a failed attempt", ["step"], succeeded=False) is None  # failure
    pid = eng.distill_skill(
        "the billing tests flake",
        ["pin the clock", "rerun pytest -k billing"],
        scope="project:billing",
    )
    assert pid
    p = eng.store.get_memory(pid)
    assert p.type == MemoryType.PROCEDURE and p.attributes.get("_distilled")
    # Pre-credited with one confirmed outcome, so reliability beats an untried recipe.
    assert p.attributes["success_count"] >= 1
    assert p.attributes["reliability"] > 0.5
    eng.close()


def test_distilled_skill_recallable_via_how(tmp_path):
    eng = _eng(tmp_path)
    eng.distill_skill("deploy fails on Friday", ["check the freeze window"], scope="project:ops")
    procs = eng.recall_procedures("my deploy failed on a Friday", scope="project:ops")
    assert procs and procs[0]["steps"]
    eng.close()


# --- the v3 eval metrics (§4.1) -------------------------------------------
def test_capability_eval_reports_v3_metrics(tmp_path):
    from helix_core.eval import run_capability_eval

    res = run_capability_eval(home=tmp_path)
    assert "compounding_lift_rate" in res
    assert "temporal_catch_rate" in res
    # Both are rates in [0, 1]; temporal catch should be perfect on the labeled scenarios.
    assert 0.0 <= res["compounding_lift_rate"] <= 1.0
    assert res["temporal_catch_rate"] == 1.0
