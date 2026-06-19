"""CRDT-style mergeable memory (v2 plan §3.3).

Gives concurrent replicas of a strand a deterministic, conflict-free way to converge on edits to
the *same* fact, complementing the semantic 3-way merge (which dedups *different* facts):

  * **Existence is add-wins** — a fact present in either replica survives the merge (deletion is
    handled separately by tombstones, which intentionally win for GDPR erasure).
  * **Scalar fields are last-writer-wins** by a **Lamport clock**, tie-broken by replica id — so
    two replicas that both edited a fact converge on the same winner regardless of merge order.

Edits are stamped with `_clock` (logical time) and `_replica` (origin) in `attributes`. A missing
clock counts as 0, so facts written before this feature merge safely.
"""

from __future__ import annotations

from .models import Memory, Provenance


def stamp(mem: Memory, clock: int, replica: str) -> None:
    """Tag a memory with the logical time and replica that produced this version."""
    mem.attributes["_clock"] = clock
    mem.attributes["_replica"] = replica


def _ticket(mem: Memory) -> tuple[int, str]:
    return (int(mem.attributes.get("_clock", 0)), str(mem.attributes.get("_replica", "")))


def _union_provenance(a: list[Provenance], b: list[Provenance]) -> list[Provenance]:
    seen: set = set()
    out: list[Provenance] = []
    for p in [*a, *b]:
        key = (p.agent, p.extractor, p.ref)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def merge_memories(local: Memory, incoming: Memory) -> tuple[Memory, bool]:
    """Resolve two versions of the same fact id. Returns (winner, content_changed).

    The higher (clock, replica) wins content/scope/type; importance/confidence take the max and
    provenance is unioned, so no contributor's attribution is lost.
    """
    winner = incoming if _ticket(incoming) > _ticket(local) else local
    loser = local if winner is incoming else incoming
    content_changed = winner.content != local.content or winner.scope != local.scope
    winner.importance = max(local.importance, incoming.importance)
    winner.confidence = max(local.confidence, incoming.confidence)
    winner.provenance = _union_provenance(winner.provenance, loser.provenance)
    return winner, content_changed
