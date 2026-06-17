"""Helix engine façade.

The single API that the CLI, MCP server, and SDK call. It wires together the write path
(redact -> gate -> extract -> embed -> consolidate -> store) and the read path
(retrieve -> rank -> pack), plus strand transfer (export/import/merge).

Pre-alpha: method signatures are the contract (see docs/TSD.md). Bodies land per ROADMAP.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config, load
from .models import Hit, Memory, Scope


class Engine:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load()
        # Stores/embedder/extractor/router are constructed lazily in Phase 1+.

    # --- write path (async to the agent; never blocks) ----------------------
    def remember(self, content: str, *, scope: Scope = "global", source: str = "cli") -> list[str]:
        """Redact -> gate -> extract -> embed -> consolidate -> store.

        Returns the ids of memories created/updated. Most slices are dropped by the gate
        with zero model calls (docs/COST_OPTIMIZATION.md §3).
        """
        raise NotImplementedError("Phase 1: full write pipeline")

    # --- read path (the hot path; p95 < 150ms) ------------------------------
    def recall(
        self,
        query: str,
        *,
        scope: Scope | None = None,
        k: int = 8,
        budget_tokens: int | None = None,
    ) -> list[Hit]:
        """Hybrid vector + graph retrieval, ranked and packed under a token budget."""
        raise NotImplementedError("Phase 1: retrieve + rank + pack")

    def forget(self, id_or_query: str) -> list[str]:
        """Soft-delete a fact (recoverable via history)."""
        raise NotImplementedError("Phase 1: soft-delete + history")

    def list_memories(
        self, *, scope: Scope | None = None, limit: int = 100
    ) -> list[Memory]:
        raise NotImplementedError("Phase 1")

    # --- transfer (the headline) --------------------------------------------
    def export_strand(self, path: Path) -> None:
        """Package -> sign (Ed25519) -> encrypt (XChaCha20-Poly1305) -> .dna (DNA_FORMAT.md)."""
        raise NotImplementedError("Phase 4: strand codec export")

    def import_strand(self, path: Path) -> None:
        """Verify signature -> decrypt -> check compat (re-embed if needed) -> open."""
        raise NotImplementedError("Phase 4: strand codec import")

    def merge_strand(self, path: Path) -> None:
        """Union + consolidate + resolve conflicts -> new version (reversible)."""
        raise NotImplementedError("Phase 4: three-way merge")
