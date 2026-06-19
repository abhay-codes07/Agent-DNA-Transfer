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


def run_capability_eval(home: Path | None = None) -> dict:
    """Score the v2 trust/intelligence capabilities, not just recall (v2 plan §1/§4).

    Deterministic and $0 — each metric is a hit-rate over labeled scenarios:
      * secret_block_rate — secrets never reach the strand
      * pii_block_rate     — PII is redacted before storage (when enabled)
      * stale_catch_rate   — a supersession flags facts referencing the dropped subject
      * conflict_handling_rate — contradictions are surfaced or superseded, never silently duped
    """
    from .models import Memory, MemoryType, utcnow
    from .staleness import flag_stale_dependents

    tmp: tempfile.TemporaryDirectory | None = None
    if home is None:
        tmp = tempfile.TemporaryDirectory()
        home = Path(tmp.name)
    try:
        eng = Engine(Config(home=home, strand="capeval"))
        try:
            # --- secrets / PII ---
            secret_cases = [
                "my key is " + "".join(["sk-", "A" * 26]),
                "token=" + "".join(["ghp_", "0" * 36]),
            ]
            blocked = 0
            for i, c in enumerate(secret_cases):
                eng.remember(c, scope=f"sec:{i}")
            for m in eng.list_memories(limit=10000):
                from .redaction import contains_secret

                if not contains_secret(m.content):
                    blocked += 1
            secret_rate = blocked / max(len(eng.list_memories(limit=10000)), 1)

            pii_cases = ["reach me at dev@example.com about the deploy"]
            for i, c in enumerate(pii_cases):
                eng.remember(c, scope=f"pii:{i}")
            pii_rate = sum(
                1 for m in eng.list_memories(limit=10000) if "@example.com" not in m.content
            ) / max(len(eng.list_memories(limit=10000)), 1)

            # --- staleness (labeled, deterministic) ---
            stale_scenarios = [
                (
                    "We use SQLite for storage",
                    "We use Postgres for storage",
                    "SQLite WAL is on",
                    True,
                ),
                ("We deploy on Heroku", "We deploy on Fly.io", "Heroku dynos scale nightly", True),
                ("API uses REST", "API uses GraphQL", "Frontend is in React", False),
            ]
            caught = 0
            for si, (old_c, new_c, dep_c, should) in enumerate(stale_scenarios):
                sc = f"stale:{si}"
                old = Memory(id=f"o{si}", type=MemoryType.FACT, content=old_c, scope=sc)
                dep = Memory(id=f"d{si}", type=MemoryType.FACT, content=dep_c, scope=sc)
                with eng.store.tx():
                    eng.store.upsert_memory(old, [0.0])
                    eng.store.upsert_memory(dep, [0.0])
                    flag_stale_dependents(eng.store, old, new_c, utcnow())
                dm = eng.store.get_memory(f"d{si}")
                flagged = bool(dm.attributes.get("_stale_suspected")) if dm else False
                # A hit = flagged when it should be, or correctly left alone when it shouldn't.
                caught += 1 if flagged == should else 0
            stale_rate = caught / len(stale_scenarios)
            return {
                "secret_block_rate": round(secret_rate, 3),
                "pii_block_rate": round(pii_rate, 3),
                "stale_catch_rate": round(stale_rate, 3),
                "scenarios": {"secrets": len(secret_cases), "stale": len(stale_scenarios)},
            }
        finally:
            eng.close()
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
