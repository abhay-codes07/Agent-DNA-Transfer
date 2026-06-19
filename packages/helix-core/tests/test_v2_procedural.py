"""Wave B — procedural / skill memory (v2 plan §1.1). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.models import MemoryType


def _eng(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


def test_learn_and_recall_procedure(tmp_path):
    eng = _eng(tmp_path)
    pid = eng.learn_procedure(
        "the billing tests flake",
        ["pin the system clock", "seed the RNG", "rerun pytest -k billing"],
        scope="project:billing",
        success_signal="tests pass",
    )
    m = eng.store.get_memory(pid)
    assert m.type == MemoryType.PROCEDURE
    assert m.attributes["steps"][0] == "pin the system clock"

    procs = eng.recall_procedures("billing tests are flaky again", scope="project:billing")
    assert procs and procs[0]["id"] == pid
    assert procs[0]["steps"]


def test_procedure_outcome_adjusts_reliability(tmp_path):
    eng = _eng(tmp_path)
    pid = eng.learn_procedure("a flaky test", ["pin the clock"])
    start = eng.store.get_memory(pid).attributes["reliability"]
    up = eng.record_procedure_outcome(pid, success=True)
    assert up["reliability"] > start
    assert up["success_count"] == 1
    down = eng.record_procedure_outcome(pid, success=False)
    assert down["reliability"] < up["reliability"]
    eng.close()


def test_procedures_rank_by_reliability(tmp_path):
    eng = _eng(tmp_path)
    a = eng.learn_procedure("deploy fails on Friday", ["check the freeze window"])
    b = eng.learn_procedure("deploy fails on Friday", ["retry the pipeline"])
    # Confirm `b` several times so it earns higher reliability.
    for _ in range(3):
        eng.record_procedure_outcome(b, success=True)
    procs = eng.recall_procedures("my deploy failed on a Friday")
    assert procs[0]["id"] == b  # the proven recipe ranks first
    assert any(p["id"] == a for p in procs)
    eng.close()


def test_secrets_redacted_in_procedure_steps(tmp_path):
    eng = _eng(tmp_path)
    pid = eng.learn_procedure(
        "rotate the deploy token",
        ["set the new value " + "".join(["ghp_", "0" * 36])],
    )
    steps = eng.store.get_memory(pid).attributes["steps"]
    assert all("ghp_0000" not in s for s in steps)
