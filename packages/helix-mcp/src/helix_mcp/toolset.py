"""HelixToolset — transport-agnostic memory tools over the engine (ADR-023/024).

This is the business surface the MCP server (and tests) call. It is plain and synchronous so
it can be unit-tested without a transport. Results are JSON-safe dicts, token-budgeted, with
human-readable ids and `concise`/`detailed` formats (docs/API_REFERENCE.md). Errors are
returned as `{"ok": False, "error": ...}` so the server can map them to MCP `isError` results.
"""

from __future__ import annotations

from typing import Any

from helix_core.engine import Engine
from helix_core.models import Origin
from helix_core.serialize import hit_to_dict, memory_to_dict

CHARS_PER_TOKEN = 4


def _concise(d: dict) -> dict:
    return {k: d[k] for k in ("id", "type", "content", "scope", "score") if k in d}


class HelixToolset:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or Engine()

    # memory.search -------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        scope: str | None = None,
        k: int = 8,
        budget_tokens: int | None = None,
        response_format: str = "concise",
    ) -> dict:
        hits = self.engine.recall(query, scope=scope, k=k)
        rows = [hit_to_dict(h) for h in hits]
        if response_format == "concise":
            rows = [_concise(r) for r in rows]
        rows = _apply_budget(rows, budget_tokens)
        return {"ok": True, "count": len(rows), "results": rows}

    # memory.context ------------------------------------------------------
    def context(
        self, *, scope: str | None = None, query: str | None = None, budget_tokens: int = 1500
    ) -> dict:
        return {
            "ok": True,
            "context": self.engine.context(scope=scope, query=query, budget_tokens=budget_tokens),
        }

    # memory.write / add --------------------------------------------------
    def write(
        self,
        content: str,
        *,
        scope: str = "global",
        source: str = "agent",
        origin: str = "agent-ingested",
    ) -> dict:
        try:
            origin_enum = Origin(origin)
        except ValueError:
            origin_enum = Origin.AGENT_INGESTED
        results = self.engine.remember(content, scope=scope, source=source, origin=origin_enum)
        return {"ok": True, "results": [{"op": r.op, "id": r.memory_id} for r in results]}

    # memory.get ----------------------------------------------------------
    def get(self, memory_id: str) -> dict:
        mem = self.engine.store.get_memory(memory_id)
        if not mem:
            return {"ok": False, "error": f"no memory with id '{memory_id}'"}
        return {"ok": True, "memory": memory_to_dict(mem)}

    # memory.forget -------------------------------------------------------
    def forget(self, id_or_query: str) -> dict:
        removed = self.engine.forget(id_or_query)
        return {"ok": bool(removed), "forgot": removed}

    # memory.relate -------------------------------------------------------
    def relate(self, from_id: str, to_id: str, relation: str = "related_to") -> dict:
        if not self.engine.store.get_memory(from_id) or not self.engine.store.get_memory(to_id):
            return {"ok": False, "error": "both from_id and to_id must exist"}
        eid = self.engine.relate(from_id, to_id, relation)
        return {"ok": True, "edge": eid}

    # memory.list ---------------------------------------------------------
    def list(self, *, scope: str | None = None, limit: int = 50) -> dict:
        mems = self.engine.list_memories(scope=scope, limit=limit)
        return {"ok": True, "count": len(mems), "memories": [memory_to_dict(m) for m in mems]}

    # memory.about (copilot) ---------------------------------------------
    def about(self, subject: str, *, k: int = 8) -> dict:
        """What the memory knows about a subject — sourced facts (the copilot surface)."""
        return {"ok": True, **self.engine.about(subject, k=k)}

    # memory.how (recall procedures) -------------------------------------
    def how(self, situation: str, *, scope: str | None = None, k: int = 5) -> dict:
        """Recall reusable how-to recipes (procedures/skills) matching a situation."""
        return {
            "ok": True,
            "procedures": self.engine.recall_procedures(situation, scope=scope, k=k),
        }

    # memory.learn (teach a procedure) -----------------------------------
    def learn(
        self,
        trigger: str,
        steps: Any,
        *,
        scope: str = "global",
        success_signal: str | None = None,
    ) -> dict:
        """Teach a reusable how-to recipe (a skill) keyed by a trigger condition."""
        if not steps:
            return {"ok": False, "error": "a procedure needs at least one step"}
        pid = self.engine.learn_procedure(
            trigger, list(steps), scope=scope, success_signal=success_signal
        )
        return {"ok": True, "id": pid}


def _apply_budget(rows: list[dict], budget_tokens: int | None) -> list[dict]:
    if not budget_tokens:
        return rows
    out: list[dict] = []
    used = 0
    for r in rows:
        cost = max(len(r.get("content", "")) // CHARS_PER_TOKEN, 1)
        if used + cost > budget_tokens:
            break
        out.append(r)
        used += cost
    return out
