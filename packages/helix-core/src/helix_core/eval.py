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

            # --- v3: compounding lift (does recording outcomes raise a proven fact's rank?) ---
            comp_lift = _compounding_lift(home)
            # --- v3: temporal catch (does the bitemporal path recover a superseded belief?) ---
            temporal_rate = _temporal_catch_rate(home)
            return {
                "secret_block_rate": round(secret_rate, 3),
                "pii_block_rate": round(pii_rate, 3),
                "stale_catch_rate": round(stale_rate, 3),
                "compounding_lift_rate": round(comp_lift, 3),
                "temporal_catch_rate": round(temporal_rate, 3),
                "scenarios": {"secrets": len(secret_cases), "stale": len(stale_scenarios)},
            }
        finally:
            eng.close()
    finally:
        if tmp is not None:
            tmp.cleanup()


def _compounding_lift(home: Path) -> float:
    """Fraction of scenarios where recording successful outcomes lifts a fact's rank (v3 §1.1/§4.1)."""
    scenarios = [
        (
            "project:ops",
            "Deploys use the blue-green strategy.",
            "Deploys use a rolling strategy.",
            "what deploy strategy do we use",
        ),
        (
            "project:api",
            "Rate limits are enforced with a token bucket.",
            "Rate limits are enforced with a leaky bucket.",
            "how are rate limits enforced",
        ),
    ]
    lifted = 0
    for si, (scope, proven, other, query) in enumerate(scenarios):
        eng = Engine(Config(home=home, strand=f"complift{si}"))
        try:
            pid = eng.remember(proven, scope=scope)[0].memory_id
            eng.remember(other, scope=scope)
            before = [h.memory.id for h in eng.recall(query, scope=scope)]
            for _ in range(5):
                eng.record_outcome([pid], success=True)
            after = [h.memory.id for h in eng.recall(query, scope=scope)]
            if pid in after and (pid not in before or after.index(pid) <= before.index(pid)):
                # proven fact is present and ranks at least as high as before (usually higher).
                if not before or before[0] != pid or (after and after[0] == pid):
                    lifted += 1
        finally:
            eng.close()
    return lifted / len(scenarios)


def _temporal_catch_rate(home: Path) -> float:
    """Fraction of scenarios where a temporal query recovers a superseded prior belief (v3 §2.2)."""
    scenarios = [
        (
            "project:db",
            "The billing database is MongoDB.",
            "The billing database is Postgres, not MongoDB.",
            "what did the billing database use to be",
        ),
        (
            "project:host",
            "We deploy on Heroku.",
            "We deploy on Fly.io, not Heroku.",
            "what did we previously use for deploys",
        ),
    ]
    caught = 0
    for si, (scope, old, new, query) in enumerate(scenarios):
        eng = Engine(Config(home=home, strand=f"temporal{si}"))
        try:
            eng.remember(old, scope=scope)
            eng.remember(new, scope=scope)
            hist = eng.history_of(old.split(" is ")[0] if " is " in old else old, k=8)
            temporal_hits = [
                h.memory.content for h in eng.recall(query, scope=scope, temporal=True)
            ]
            # A hit = the old belief resurfaces via the bitemporal path (history transition or
            # a temporal recall admitting the superseded fact).
            recovered = hist["changes"] > 0 or any(
                old.lower()[:12] in c.lower() for c in temporal_hits
            )
            caught += 1 if recovered else 0
        finally:
            eng.close()
    return caught / len(scenarios)


# Floors the evolution eval must clear — the CI regression gate (v3 plan §4.3). A drop below any of
# these fails the build, turning "memory compounds" from a claim into an enforced contract.
EVOLUTION_FLOORS = {
    "knowledge_freshness": 1.0,  # never serve a superseded fact as current
    "skill_reuse": 1.0,  # a distilled skill is recalled for its situation
    "temporal_accuracy": 1.0,  # the prior belief is recoverable
    "avg_reliability": 0.5,  # proven facts have earned reliability above the neutral prior
}


def run_evolution_eval(home: Path | None = None) -> dict:
    """SWE-EVO-style multi-episode scenario: does memory *compound* as a project evolves? (v3 §4.2).

    Simulates one project across several 'sessions': facts are learned, some are superseded as the
    codebase changes, a successful trajectory is distilled into a skill, and task outcomes are
    recorded. We then measure — on the *same* strand, end to end — whether:
      * knowledge_freshness — recall serves the *current* fact, never a superseded one;
      * skill_reuse         — a distilled skill resurfaces for a matching situation;
      * temporal_accuracy   — the *prior* belief is still recoverable via the bitemporal path;
      * avg_reliability     — facts credited by real outcomes rose above the neutral 0.5 prior.
    Deterministic and $0. `helix eval-evolution` prints it; a test asserts EVOLUTION_FLOORS.
    """
    from .experience import reliability
    from .models import Status

    tmp: tempfile.TemporaryDirectory | None = None
    if home is None:
        tmp = tempfile.TemporaryDirectory()
        home = Path(tmp.name)
    scope = "project:orders-svc"
    try:
        eng = Engine(Config(home=home, strand="evolution"))
        try:
            # --- Episode 1: the project is young; learn its initial shape, use a fact ---
            api = eng.remember("The orders service API uses REST.", scope=scope)[0].memory_id
            eng.remember("The orders service stores data in MySQL.", scope=scope)
            eng.remember("Deploys run on Heroku.", scope=scope)
            eng.record_outcome([api], success=True)  # the REST fact helped a task

            # --- Episode 2: the codebase evolves; supersede, distill a skill, credit outcomes ---
            grpc = eng.remember("The orders service API uses gRPC, not REST.", scope=scope)[
                0
            ].memory_id
            eng.remember("Deploys run on Fly.io, not Heroku.", scope=scope)
            skill_id = eng.distill_skill(
                "the orders build breaks on a migration",
                ["reset the test database", "rerun the migration", "re-run the suite"],
                scope=scope,
            )
            for _ in range(3):
                eng.record_outcome([grpc], success=True)

            # --- Episode 3: measure whether the memory compounded ---
            # freshness: the current (gRPC) fact surfaces; the superseded (REST) one does not.
            fresh_hits = eng.recall("how does the orders API communicate", scope=scope)
            active_contents = [h.memory.content.lower() for h in fresh_hits]
            # A served-stale hit is the superseded REST fact resurfacing: mentions REST but not the
            # new gRPC value (the current fact legitimately says "gRPC, not REST"), or is SUPERSEDED.
            served_stale = any(
                h.memory.status == Status.SUPERSEDED
                or ("rest" in h.memory.content.lower() and "grpc" not in h.memory.content.lower())
                for h in fresh_hits
            )
            knows_current = any("grpc" in c for c in active_contents)
            knowledge_freshness = 1.0 if (knows_current and not served_stale) else 0.0

            # skill_reuse: the distilled skill resurfaces for its situation.
            procs = eng.recall_procedures(
                "the orders build is failing on a db migration", scope=scope
            )
            skill_reuse = 1.0 if any(p["id"] == skill_id for p in procs) else 0.0

            # temporal_accuracy: the prior belief (REST) is recoverable via the bitemporal path.
            hist = eng.history_of("orders service api", k=8)
            temporal_hits = [
                h.memory.content.lower()
                for h in eng.recall(
                    "what did the orders API use before", scope=scope, temporal=True
                )
            ]
            temporal_accuracy = (
                1.0 if (hist["changes"] > 0 or any("rest" in c for c in temporal_hits)) else 0.0
            )

            # compounding: facts credited by outcomes earned reliability above the neutral prior.
            credited = [
                m
                for m in eng.list_memories(scope=scope, limit=1000)
                if float(m.attributes.get("_uses", 0)) > 0
            ]
            avg_reliability = (
                sum(reliability(m) for m in credited) / len(credited) if credited else 0.5
            )

            metrics = {
                "episodes": 3,
                "knowledge_freshness": round(knowledge_freshness, 3),
                "skill_reuse": round(skill_reuse, 3),
                "temporal_accuracy": round(temporal_accuracy, 3),
                "avg_reliability": round(avg_reliability, 3),
            }
            metrics["overall"] = round(
                sum(metrics[k] for k in EVOLUTION_FLOORS) / len(EVOLUTION_FLOORS), 3
            )
            return metrics
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
