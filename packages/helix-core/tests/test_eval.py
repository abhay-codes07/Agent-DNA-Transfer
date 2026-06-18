"""Tests for the recall-quality eval harness (docs/EVALUATION.md). Offline."""

from __future__ import annotations

from helix_core.eval import CODING_BENCHMARK, EvalCase, EvalQuery, run_eval


def test_builtin_benchmark_runs_and_reports(tmp_path):
    res = run_eval(CODING_BENCHMARK, k=5, home=tmp_path)
    assert res.n_queries == sum(len(c.queries) for c in CODING_BENCHMARK)
    assert 0.0 <= res.precision_at_k <= 1.0
    assert res.recall_at_k > 0.5  # gold is recoverable within top-k
    assert res.mrr > 0.0
    assert res.p95_ms >= res.p50_ms >= 0.0
    assert "precision_at_k" in res.as_dict()


def test_perfect_recall_case(tmp_path):
    case = EvalCase(
        name="t",
        memories=[("We use Postgres for the billing service.", "project:b")],
        queries=[EvalQuery("postgres billing database", ["We use Postgres for the billing service."], "project:b")],
    )
    res = run_eval([case], k=5, home=tmp_path)
    assert res.recall_at_k == 1.0
    assert res.mrr == 1.0  # the only memory is the top hit
