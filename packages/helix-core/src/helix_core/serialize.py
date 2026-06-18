"""Serialization helpers — turn memories/hits into plain JSON-safe dicts.

Used by the CLI `--json` output and the MCP toolset (Phase 2). Keeps the public, human-
readable surface in one place: ids, types, content, scope, confidence, and provenance origin
(no internal counters like `_reinforced`).
"""

from __future__ import annotations

from .models import Hit, Memory


def memory_to_dict(mem: Memory) -> dict:
    return {
        "id": mem.id,
        "type": mem.type.value,
        "cognitive": mem.cognitive.value,
        "content": mem.content,
        "scope": mem.scope,
        "confidence": round(mem.confidence, 3),
        "importance": round(mem.importance, 3),
        "status": mem.status.value,
        "valid_from": mem.valid_from.isoformat() if mem.valid_from else None,
        "valid_to": mem.valid_to.isoformat() if mem.valid_to else None,
        "origin": mem.provenance[0].origin.value if mem.provenance else None,
    }


def hit_to_dict(hit: Hit) -> dict:
    d = memory_to_dict(hit.memory)
    d["score"] = round(hit.score, 4)
    d["similarity"] = round(hit.similarity, 4)
    d["salience"] = round(hit.salience, 4)
    return d
