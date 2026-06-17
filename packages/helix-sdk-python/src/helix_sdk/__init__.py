"""Helix Python SDK.

A small, ergonomic wrapper over helix_core.Engine for embedding portable memory in custom
agents and scripts. Mirrors the MCP surface (docs/MCP_INTEGRATION.md).

    from helix_sdk import Helix

    mem = Helix()                      # opens the local strand; $0, offline by default
    mem.remember("We use RFC-7807 for API errors", scope="project:billing-svc")
    hits = mem.recall("how do we format API errors?", scope="project:billing-svc")
"""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine

__version__ = "0.0.1"


class Helix:
    """Thin, friendly facade over the engine."""

    def __init__(self, config: Config | None = None) -> None:
        self._engine = Engine(config)

    def remember(self, content: str, *, scope: str = "global", source: str = "sdk") -> list[str]:
        return self._engine.remember(content, scope=scope, source=source)

    def recall(self, query: str, *, scope: str | None = None, k: int = 8):  # noqa: ANN201
        return self._engine.recall(query, scope=scope, k=k)

    def forget(self, id_or_query: str) -> list[str]:
        return self._engine.forget(id_or_query)


__all__ = ["Helix", "__version__"]
