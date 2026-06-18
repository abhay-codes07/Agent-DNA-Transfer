"""Helix Python SDK.

A small, ergonomic wrapper over helix_core.Engine for embedding portable memory in custom
agents and scripts — full parity with the CLI/MCP surface. $0/offline by default.

    from helix_sdk import Helix

    mem = Helix()
    mem.remember("We use RFC-7807 for API errors", scope="project:billing-svc")
    for hit in mem.recall("how do we format API errors?", scope="project:billing-svc"):
        print(hit.score, hit.memory.content)
"""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine

__version__ = "0.0.1"


class Helix:
    """Thin, friendly facade over the engine. Same operations as `helix` and the MCP server."""

    def __init__(self, config: Config | None = None) -> None:
        self._engine = Engine(config)

    @property
    def engine(self) -> Engine:
        return self._engine

    # --- memory ---
    def remember(self, content: str, *, scope: str = "global", source: str = "sdk"):
        return self._engine.remember(content, scope=scope, source=source)

    def recall(self, query: str, *, scope: str | None = None, k: int = 8):
        return self._engine.recall(query, scope=scope, k=k)

    def context(
        self, *, scope: str | None = None, query: str | None = None, budget_tokens: int = 1500
    ) -> str:
        return self._engine.context(scope=scope, query=query, budget_tokens=budget_tokens)

    def list(self, *, scope: str | None = None, limit: int = 100):
        return self._engine.list_memories(scope=scope, limit=limit)

    def get(self, memory_id: str):
        return self._engine.get_memory(memory_id)

    def edit(self, memory_id: str, **fields):
        return self._engine.edit_memory(memory_id, **fields)

    def forget(self, id_or_query: str):
        return self._engine.forget(id_or_query)

    def relate(self, from_id: str, to_id: str, relation: str = "related_to") -> str:
        return self._engine.relate(from_id, to_id, relation)

    def maintain(self, **kw) -> dict:
        return self._engine.maintain(**kw)

    def history(self, limit: int = 50):
        return self._engine.history(limit)

    def stats(self) -> dict:
        return self._engine.stats()

    # --- transfer (.dna) ---
    def export(self, path: str, *, passphrase: str | None = None, label: str = ""):
        return self._engine.export_strand(path, passphrase=passphrase, label=label)

    def verify(self, path: str) -> dict:
        return self._engine.verify_strand(path)

    def import_(
        self,
        path: str,
        *,
        passphrase: str | None = None,
        as_strand: str | None = None,
        replace: bool = False,
    ) -> dict:
        return self._engine.import_strand(
            path, passphrase=passphrase, as_strand=as_strand, replace=replace
        )

    def merge(self, path: str, *, passphrase: str | None = None) -> dict:
        return self._engine.merge_strand(path, passphrase=passphrase)

    def diff(self, path: str, *, passphrase: str | None = None) -> dict:
        return self._engine.diff_strand(path, passphrase=passphrase)

    # --- sync ---
    def push(
        self, location: str, *, passphrase: str | None = None, name: str | None = None
    ) -> dict:
        return self._engine.push(location, passphrase=passphrase, name=name)

    def pull(
        self,
        location: str,
        *,
        passphrase: str | None = None,
        name: str | None = None,
        merge: bool = True,
    ) -> dict:
        return self._engine.pull(location, passphrase=passphrase, name=name, merge=merge)

    def close(self) -> None:
        self._engine.close()

    def __enter__(self) -> "Helix":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


__all__ = ["Helix", "__version__"]
