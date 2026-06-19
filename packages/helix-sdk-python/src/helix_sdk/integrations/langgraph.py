"""LangGraph adapter — a long-term memory store backed by Helix (v2 plan §5.3).

`HelixStore` implements LangGraph's `BaseStore` convenience surface (`put` / `get` / `search` /
`delete`, plus async mirrors) over a local, portable `.dna` strand. Pass it straight to a graph:

    from helix_sdk.integrations.langgraph import HelixStore
    graph = builder.compile(store=HelixStore())

LangGraph namespaces (tuples) map to Helix scopes, so per-user / per-project memory is isolated.
The adapter does not require LangGraph to import — it's duck-typed against the store interface —
so it stays $0 and testable on its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from helix_core.config import Config
from helix_core.engine import Engine


def _scope(namespace: Sequence[Any] | None) -> str:
    """Map a LangGraph namespace tuple to a Helix scope."""
    if not namespace:
        return "global"
    return "project:" + "-".join(str(p) for p in namespace)


@dataclass
class Item:
    """A stored item, shaped like a LangGraph store Item/SearchItem."""

    namespace: tuple
    key: str
    value: dict
    score: float = 0.0


class HelixStore:
    """LangGraph-compatible memory store backed by a local Helix strand."""

    def __init__(self, engine: Engine | None = None, config: Config | None = None) -> None:
        self._engine = engine or Engine(config)

    @staticmethod
    def _content(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return (
                value.get("content") or value.get("text") or value.get("data") or json.dumps(value)
            )
        return str(value)

    def put(self, namespace: Sequence[Any], key: str, value: Any, **_: Any) -> None:
        self._engine.remember(self._content(value), scope=_scope(namespace), source="langgraph")

    def get(self, namespace: Sequence[Any], key: str, **_: Any) -> Item | None:
        m = self._engine.get_memory(key)
        return Item(tuple(namespace), key, {"content": m.content}) if m else None

    def search(
        self,
        namespace: Sequence[Any],
        *,
        query: str | None = None,
        limit: int = 10,
        **_: Any,
    ) -> list[Item]:
        scope = _scope(namespace)
        if not query:
            mems = self._engine.list_memories(scope=scope, limit=limit)
            return [Item(tuple(namespace), m.id, {"content": m.content}) for m in mems]
        hits = self._engine.recall(query, scope=scope, k=limit)
        return [
            Item(tuple(namespace), h.memory.id, {"content": h.memory.content}, h.score)
            for h in hits
        ]

    def delete(self, namespace: Sequence[Any], key: str, **_: Any) -> None:
        self._engine.forget(key)

    # async mirrors (LangGraph calls the async API in async graphs)
    async def aput(self, *a: Any, **k: Any) -> None:
        self.put(*a, **k)

    async def aget(self, *a: Any, **k: Any) -> Item | None:
        return self.get(*a, **k)

    async def asearch(self, *a: Any, **k: Any) -> list[Item]:
        return self.search(*a, **k)

    async def adelete(self, *a: Any, **k: Any) -> None:
        self.delete(*a, **k)

    def close(self) -> None:
        self._engine.close()
