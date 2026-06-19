"""Consolidation — ADD / UPDATE / NOOP / SUPERSEDE (TSD §6.3, docs/CONSOLIDATION.md).

For each candidate fact (already embedded), find the nearest existing memory and decide how to
fold it in. Bi-temporal supersession never hard-deletes: the old fact's `valid_to` is closed
and it is marked superseded, linked by a `supersedes` edge (ADR-013/021). Idempotent: a
re-stated fact is a NOOP that simply reinforces.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .decay import reinforce
from .ids import edge_id, new_id
from .models import CandidateFact, Edge, Memory, Provenance, Status, utcnow

# Cosine thresholds (vectors are normalized; cosine in [-1, 1]).
DUP_THRESHOLD = 0.97  # essentially the same statement -> NOOP
UPDATE_THRESHOLD = 0.82  # same subject, refine/supersede
GRAY_LOW = 0.65  # below DUP and around UPDATE: ambiguous -> ask the LLM if available (ADR-034)

_NEGATION = re.compile(r"\b(no longer|not|instead|now use|switched to|deprecated|don'?t)\b", re.I)
# Types that hold at most one current value per scope -> a near-match is a supersession.
_SINGLETON = {"identity"}
_VERDICTS = {"duplicate", "update", "contradict", "distinct"}


@dataclass(slots=True)
class ConsolidationResult:
    op: str  # "ADD" | "UPDATE" | "NOOP" | "SUPERSEDE"
    memory_id: str


def consolidate(
    store,  # SqliteStore
    candidate: CandidateFact,
    embedding: list[float],
    provenance: Provenance,
    *,
    router=None,  # optional LLMRouter for gray-band adjudication
) -> ConsolidationResult:
    now = utcnow()
    hits = store.vector_search(embedding, k=5, scope=candidate.scope)
    best_id, best_sim = hits[0] if hits else (None, 0.0)
    best = store.get_memory(best_id) if best_id else None
    same_type = best is not None and best.type == candidate.type

    # NOOP — clearly the same; reinforce (deterministic, never spends an LLM call).
    if best and same_type and best_sim >= DUP_THRESHOLD:
        return _noop(store, best, provenance, now, best_sim)

    # Gray band — ambiguous. If an LLM is configured, let it adjudicate (ADR-034).
    if (
        best
        and same_type
        and GRAY_LOW <= best_sim < DUP_THRESHOLD
        and router
        and router.available()
    ):
        verdict = _llm_adjudicate(router, best, candidate)
        if verdict == "duplicate":
            return _noop(store, best, provenance, now, best_sim, op="noop-llm")
        if verdict == "contradict":
            return _supersede(store, best, candidate, embedding, provenance, now, best_sim)
        if verdict == "update":
            return _update(store, best, candidate, embedding, provenance, now, best_sim)
        if verdict == "distinct":
            return _add(store, candidate, embedding, provenance, now)
        # None / unavailable -> fall through to the deterministic decision below.

    # Deterministic UPDATE / SUPERSEDE — same subject area.
    if best and same_type and best_sim >= UPDATE_THRESHOLD:
        contradicts = (
            bool(_NEGATION.search(candidate.content)) or candidate.type.value in _SINGLETON
        )
        if contradicts:
            return _supersede(store, best, candidate, embedding, provenance, now, best_sim)
        return _update(store, best, candidate, embedding, provenance, now, best_sim)

    # Weakly-similar but contradictory (gray band, no confident resolution): keep BOTH and
    # surface the conflict rather than silently picking a winner (v2 plan §1.5).
    res = _add(store, candidate, embedding, provenance, now)
    if best and same_type and best_sim >= GRAY_LOW and _contradiction_signal(candidate, best):
        _flag_conflict(store, res.memory_id, best.id, best_sim)
    return res


def _contradiction_signal(candidate: CandidateFact, best: Memory) -> bool:
    return bool(_NEGATION.search(candidate.content)) or candidate.type.value in _SINGLETON


def _flag_conflict(store, new_id: str, old_id: str, sim: float) -> None:
    """Record a bidirectional-by-convention `conflicts_with` edge and flag both memories.

    Both stay ACTIVE; the edge makes the conflict visible (recall's graph expansion pulls the
    counterpart in, and the review queue lists it). Never auto-resolved.
    """
    store.add_edge(
        Edge(
            id=edge_id(new_id, "conflicts_with", old_id),
            from_id=new_id,
            to_id=old_id,
            relation="conflicts_with",
        )
    )
    for mid in (new_id, old_id):
        mem = store.get_memory(mid)
        if mem is not None and not mem.attributes.get("_conflict"):
            mem.attributes["_conflict"] = True
            store.upsert_memory(mem)
    store.add_history("conflict", new_id, {"with": old_id, "sim": round(sim, 3)})


def _noop(store, best, provenance, now, sim, op: str = "noop") -> ConsolidationResult:
    reinforce(best, now)
    best.confidence = min(best.confidence + 0.05, 1.0)
    best.provenance.append(provenance)
    best.updated_at = now
    store.upsert_memory(best)
    store.add_history(op, best.id, {"sim": round(sim, 3)})
    return ConsolidationResult("NOOP", best.id)


def _update(store, best, candidate, embedding, provenance, now, sim) -> ConsolidationResult:
    if len(candidate.content) > len(best.content):
        best.content = candidate.content
    best.importance = max(best.importance, candidate.importance)
    best.confidence = min(best.confidence + 0.05, 1.0)
    best.attributes.update(candidate.attributes)
    best.provenance.append(provenance)
    reinforce(best, now)
    best.updated_at = now
    store.upsert_memory(best, embedding)
    store.add_history("update", best.id, {"sim": round(sim, 3)})
    return ConsolidationResult("UPDATE", best.id)


def _add(store, candidate, embedding, provenance, now) -> ConsolidationResult:
    mem = _new_memory(candidate, provenance, now)
    store.upsert_memory(mem, embedding)
    store.add_history("add", mem.id, {"type": mem.type.value})
    return ConsolidationResult("ADD", mem.id)


def _llm_adjudicate(router, existing: Memory, candidate: CandidateFact) -> str | None:
    """Ask the LLM how the new statement relates to an existing memory. None on any failure."""
    prompt = (
        f"Existing memory: {existing.content}\n"
        f"New statement: {candidate.content}\n"
        'Respond JSON {"relation": "<r>"} where <r> is one of: '
        "duplicate (same fact), update (refines/extends the same subject), "
        "contradict (new replaces or negates the old), distinct (a different fact)."
    )
    try:
        result = router.complete(
            prompt,
            system="You classify how a new statement relates to an existing memory.",
            json_mode=True,
        )
        relation = str(json.loads(result.text).get("relation", "")).lower().strip()
        return relation if relation in _VERDICTS else None
    except Exception:
        return None


def _supersede(
    store, old: Memory, candidate, embedding, provenance, now, sim
) -> ConsolidationResult:
    old.valid_to = now
    old.status = Status.SUPERSEDED
    old.updated_at = now
    store.upsert_memory(old)  # drops it from FTS/active retrieval
    new = _new_memory(candidate, provenance, now)
    store.upsert_memory(new, embedding)
    store.add_edge(
        Edge(
            id=edge_id(new.id, "supersedes", old.id),
            from_id=new.id,
            to_id=old.id,
            relation="supersedes",
        )
    )
    store.add_history("supersede", new.id, {"superseded": old.id, "sim": round(sim, 3)})
    # Implicit invalidation: facts referencing a subject this change dropped are now suspect.
    from .staleness import flag_stale_dependents

    flag_stale_dependents(store, old, new.content, now)
    return ConsolidationResult("SUPERSEDE", new.id)


def _new_memory(candidate: CandidateFact, provenance: Provenance, now) -> Memory:
    return Memory(
        id=new_id(candidate.type.value, candidate.content),
        type=candidate.type,
        content=candidate.content,
        scope=candidate.scope,
        cognitive=candidate.cognitive,
        attributes=dict(candidate.attributes),
        importance=candidate.importance,
        confidence=candidate.confidence,
        provenance=[provenance],
        valid_from=now,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )
