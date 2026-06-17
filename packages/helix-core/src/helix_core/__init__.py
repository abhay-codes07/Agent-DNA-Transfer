"""Helix core engine.

Local-first, portable memory for AI coding agents. This package is the only place with
business logic; the CLI, MCP server, and SDK are thin front-ends over it
(see docs/SYSTEM_ARCHITECTURE.md).

Pre-alpha: most subsystems are interface stubs. The structure is authoritative — build
into it, not around it (see CLAUDE.md).
"""

from __future__ import annotations

__version__ = "0.0.1"

from .models import CandidateFact, Edge, Hit, Memory, MemoryType, Provenance, Scope

__all__ = [
    "__version__",
    "Memory",
    "MemoryType",
    "Edge",
    "Provenance",
    "CandidateFact",
    "Hit",
    "Scope",
]
