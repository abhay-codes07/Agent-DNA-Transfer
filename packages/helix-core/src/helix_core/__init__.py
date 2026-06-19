"""Helix core engine.

Local-first, portable memory for AI coding agents. This package is the only place with
business logic; the CLI, MCP server, and SDK are thin front-ends over it
(see docs/SYSTEM_ARCHITECTURE.md).

Phase 1 implements a working $0/offline vertical slice: ingest -> redact -> gate -> extract
-> embed -> consolidate -> store, and hybrid retrieve -> rank -> recall.
"""

from __future__ import annotations

__version__ = "0.1.1"

from .models import (
    COGNITIVE_OF,
    CandidateFact,
    Cognitive,
    Edge,
    Hit,
    Memory,
    MemoryType,
    Origin,
    Provenance,
    Scope,
    Status,
)

__all__ = [
    "__version__",
    "Memory",
    "MemoryType",
    "Cognitive",
    "COGNITIVE_OF",
    "Status",
    "Origin",
    "Edge",
    "Provenance",
    "CandidateFact",
    "Hit",
    "Scope",
]


def open_engine(config=None):  # noqa: ANN001 - lazy to avoid importing heavy deps at import time
    """Convenience: open the local engine on the default (or given) config."""
    from .engine import Engine

    return Engine(config)
