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


def provenance_to_dict(p) -> dict:
    return {
        "agent": p.agent,
        "ref": p.ref,
        "extractor": p.extractor,
        "origin": p.origin.value,
        "ingested_at": p.ingested_at.isoformat() if p.ingested_at else None,
    }


def memory_detail_dict(mem: Memory) -> dict:
    """Full detail incl. provenance ('why it believes this') — for the dashboard drill-down."""
    d = memory_to_dict(mem)
    d["created_at"] = mem.created_at.isoformat() if mem.created_at else None
    d["updated_at"] = mem.updated_at.isoformat() if mem.updated_at else None
    d["last_seen_at"] = mem.last_seen_at.isoformat() if mem.last_seen_at else None
    d["provenance"] = [provenance_to_dict(p) for p in mem.provenance]
    d["attributes"] = {k: v for k, v in mem.attributes.items() if not k.startswith("_")}
    return d


def hit_to_dict(hit: Hit) -> dict:
    d = memory_to_dict(hit.memory)
    d["score"] = round(hit.score, 4)
    d["similarity"] = round(hit.similarity, 4)
    d["salience"] = round(hit.salience, 4)
    return d
