"""v3 §4.2/§4.3 — the SWE-EVO-style evolution eval + CI regression gate. Offline / $0.

This test IS the regression gate: it fails the build if the compounding/temporal/skill metrics
drop below EVOLUTION_FLOORS, so "memory compounds" stays a contract, not a claim.
"""

from __future__ import annotations

from helix_core.eval import EVOLUTION_FLOORS, run_evolution_eval


def test_evolution_eval_meets_floors(tmp_path):
    res = run_evolution_eval(home=tmp_path)
    assert res["episodes"] == 3
    for metric, floor in EVOLUTION_FLOORS.items():
        assert res[metric] >= floor, f"{metric}={res[metric]} fell below floor {floor}"
    # overall is the mean of the gated metrics.
    assert 0.0 <= res["overall"] <= 1.0


def test_evolution_serves_current_not_stale(tmp_path):
    # Freshness is the load-bearing property — a memory that serves superseded facts is worse
    # than no memory. It must be a hard 1.0.
    res = run_evolution_eval(home=tmp_path)
    assert res["knowledge_freshness"] == 1.0
    assert res["temporal_accuracy"] == 1.0
