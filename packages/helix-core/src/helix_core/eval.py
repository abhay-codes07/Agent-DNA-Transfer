"""Recall-quality evaluation harness (docs/EVALUATION.md, ADR-027).

Measures how well Helix surfaces the *right* memories: precision@k, recall@k, MRR, and recall
latency over labeled (query -> gold memories) cases. Metrics depend on the active embedder
(lexical hashing by default; semantic with fastembed). Ships a small built-in coding-agent
benchmark so `helix eval` runs out of the box — the category gap the docs call out.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .engine import Engine


@dataclass
class EvalQuery:
    query: str
    gold: list[str]  # memory contents that *should* be surfaced
    scope: str | None = None


@dataclass
class EvalCase:
    name: str
    memories: list[tuple[str, str]]  # (content, scope)
    queries: list[EvalQuery] = field(default_factory=list)


@dataclass
class EvalResult:
    k: int
    n_queries: int
    precision_at_k: float
    recall_at_k: float
    mrr: float
    p50_ms: float
    p95_ms: float

    def as_dict(self) -> dict:
        return {
            "k": self.k,
            "n_queries": self.n_queries,
            "precision_at_k": round(self.precision_at_k, 3),
            "recall_at_k": round(self.recall_at_k, 3),
            "mrr": round(self.mrr, 3),
            "p50_ms": round(self.p50_ms, 1),
            "p95_ms": round(self.p95_ms, 1),
        }


def _matches(hit_content: str, gold: str) -> bool:
    a, b = hit_content.lower().strip(), gold.lower().strip()
    return a == b or b in a or a in b


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(round((pct / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[idx]


def run_eval(cases: list[EvalCase], *, k: int = 5, home: Path | None = None) -> EvalResult:
    """Load each case's memories, run its queries, and aggregate recall metrics + latency."""
    tmp: tempfile.TemporaryDirectory | None = None
    if home is None:
        tmp = tempfile.TemporaryDirectory()
        home = Path(tmp.name)
    try:
        precisions: list[float] = []
        recalls: list[float] = []
        rr: list[float] = []
        latencies: list[float] = []
        n = 0
        for ci, case in enumerate(cases):
            eng = Engine(Config(home=home, strand=f"eval{ci}"))
            try:
                for content, scope in case.memories:
                    eng.remember(content, scope=scope)
                for q in case.queries:
                    n += 1
                    t0 = time.perf_counter()
                    hits = eng.recall(q.query, scope=q.scope, k=k)
                    latencies.append((time.perf_counter() - t0) * 1000.0)
                    top = [h.memory.content for h in hits[:k]]
                    matched = sum(1 for c in top if any(_matches(c, g) for g in q.gold))
                    precisions.append(matched / max(len(top), 1))
                    found = sum(1 for g in q.gold if any(_matches(c, g) for c in top))
                    recalls.append(found / max(len(q.gold), 1))
                    rank = next(
                        (i + 1 for i, c in enumerate(top) if any(_matches(c, g) for g in q.gold)),
                        0,
                    )
                    rr.append(1.0 / rank if rank else 0.0)
            finally:
                eng.close()

        def avg(xs: list[float]) -> float:
            return sum(xs) / len(xs) if xs else 0.0

        return EvalResult(
            k=k,
            n_queries=n,
            precision_at_k=avg(precisions),
            recall_at_k=avg(recalls),
            mrr=avg(rr),
            p50_ms=_percentile(latencies, 50),
            p95_ms=_percentile(latencies, 95),
        )
    finally:
        if tmp is not None:
            tmp.cleanup()


# A small built-in coding-agent memory benchmark (the category gap from docs/EVALUATION.md).
CODING_BENCHMARK: list[EvalCase] = [
    EvalCase(
        name="project-facts",
        memories=[
            (
                "We chose Postgres over MongoDB for billing because it needs ACID.",
                "project:billing",
            ),
            ("All API errors use the RFC-7807 problem+json format.", "project:billing"),
            (
                "The billing service is built with FastAPI and deployed on Fly.io.",
                "project:billing",
            ),
            ("Events flow through NATS, not Kafka.", "project:billing"),
        ],
        queries=[
            EvalQuery(
                "which database did we choose for billing",
                ["We chose Postgres over MongoDB for billing because it needs ACID."],
                "project:billing",
            ),
            EvalQuery(
                "how should API errors be formatted",
                ["All API errors use the RFC-7807 problem+json format."],
                "project:billing",
            ),
            EvalQuery(
                "what message bus do we use",
                ["Events flow through NATS, not Kafka."],
                "project:billing",
            ),
        ],
    ),
    EvalCase(
        name="preferences",
        memories=[
            ("I prefer pytest over unittest.", "global"),
            ("Use ruff and black for Python formatting and linting.", "global"),
            ("Always write type hints in core modules.", "global"),
        ],
        queries=[
            EvalQuery(
                "what testing framework do I prefer", ["I prefer pytest over unittest."], "global"
            ),
            EvalQuery(
                "which linter and formatter should be used",
                ["Use ruff and black for Python formatting and linting."],
                "global",
            ),
        ],
    ),
    EvalCase(
        name="scope-isolation",
        memories=[
            ("This service uses Redis for caching.", "project:alpha"),
            ("This service uses Memcached for caching.", "project:beta"),
        ],
        queries=[
            EvalQuery(
                "what cache does this service use",
                ["This service uses Redis for caching."],
                "project:alpha",
            ),
        ],
    ),
]
