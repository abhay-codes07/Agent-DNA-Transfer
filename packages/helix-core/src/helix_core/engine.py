"""Helix engine façade.

The single API the CLI, MCP server, and SDK call. Phase 1 implements the full local $0/offline
loop: remember (redact → extract → embed → consolidate → store) and recall (hybrid retrieve →
rank). Transfer (export/import/merge) lands in Phase 4.
"""

from __future__ import annotations

from datetime import datetime

from .config import Config, load
from .consolidate import ConsolidationResult, consolidate
from .decay import reinforce, salience
from .embed import get_embedder
from .extract.deterministic import DeterministicExtractor
from .models import GLOBAL, Hit, Memory, Origin, Provenance, Scope, Status, utcnow
from .redaction import redact
from .retrieve import pack_context, recall
from .stores.sqlite_store import SqliteStore


class Engine:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load()
        self.embedder = get_embedder(self.config)
        self.store = SqliteStore(self.config.strand_path)
        self.store.ensure_embedding_space(self.embedder.model, self.embedder.dim)
        self.extractor = DeterministicExtractor(self.config.heuristic_confidence_cutoff)

    # --- write path -----------------------------------------------------------
    def remember(
        self,
        content: str,
        *,
        scope: Scope = GLOBAL,
        source: str = "cli",
        origin: Origin = Origin.USER_ASSERTED,
        force: bool = True,
    ) -> list[ConsolidationResult]:
        """Redact → extract → embed → consolidate → store. Returns per-fact results.

        `force=True` (the default for explicit `add`/SDK calls) stores at least one fact even
        if the heuristic gate is unsure. Passive agent slices should pass force=False so the
        gate can drop most turns at $0.
        """
        clean = redact(content)
        candidates = self.extractor.extract(clean, scope=scope, force=force)
        results: list[ConsolidationResult] = []
        with self.store.tx():
            for cand in candidates:
                emb = self.embedder.embed([cand.content])[0]
                prov = Provenance(agent=source, extractor=self.extractor.name, origin=origin)
                results.append(consolidate(self.store, cand, emb, prov))
        return results

    # --- read path ------------------------------------------------------------
    def recall(
        self,
        query: str,
        *,
        scope: Scope | None = None,
        k: int = 8,
        touch: bool = False,
        now: datetime | None = None,
    ) -> list[Hit]:
        """Hybrid retrieval + ranking. With touch=True, reinforce the surfaced memories."""
        hits = recall(self.store, self.embedder, query, scope=scope, k=k, now=now)
        if touch and hits:
            with self.store.tx():
                for h in hits:
                    reinforce(h.memory, now)
                    self.store.upsert_memory(h.memory)
        return hits

    def context(
        self, *, scope: Scope | None = None, query: str | None = None, budget_tokens: int = 1500
    ) -> str:
        """One-call 'give me what matters here', packed under a token budget."""
        if query:
            hits = self.recall(query, scope=scope, k=20)
        else:
            now = utcnow()
            mems = self.store.all_memories(scope=scope, limit=200)
            hits = sorted(
                (Hit(memory=m, score=salience(m, now), salience=salience(m, now)) for m in mems),
                key=lambda h: h.score,
                reverse=True,
            )[:20]
        return pack_context(hits, budget_tokens)

    def forget(self, id_or_query: str) -> list[str]:
        """Soft-delete by id, or the top match for a query (recoverable via history)."""
        mem = self.store.get_memory(id_or_query)
        if mem is None:
            hits = self.recall(id_or_query, k=1)
            if not hits:
                return []
            mem = hits[0].memory
        with self.store.tx():
            mem.status = Status.FORGOTTEN
            mem.updated_at = utcnow()
            self.store.upsert_memory(mem)
            self.store.add_history("forget", mem.id, {})
        return [mem.id]

    def list_memories(self, *, scope: Scope | None = None, limit: int = 100) -> list[Memory]:
        return self.store.all_memories(scope=scope, limit=limit)

    # --- diagnostics ----------------------------------------------------------
    def stats(self) -> dict:
        return {
            "strand_path": str(self.config.strand_path),
            "embedding_model": self.embedder.model,
            "embedding_dim": self.embedder.dim,
            "fts5": self.store.fts,
            "active_memories": self.store.count(),
            "fastembed": _has("fastembed"),
            "sqlite_vec": _has("sqlite_vec"),
        }

    def close(self) -> None:
        self.store.close()

    # transfer (Phase 4) ------------------------------------------------------
    def export_strand(self, path) -> None:  # noqa: ANN001
        raise NotImplementedError("Phase 4: strand codec export (docs/DNA_FORMAT.md)")

    def import_strand(self, path) -> None:  # noqa: ANN001
        raise NotImplementedError("Phase 4: strand codec import")

    def merge_strand(self, path) -> None:  # noqa: ANN001
        raise NotImplementedError("Phase 4: three-way merge (docs/SYNC.md)")


def _has(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None
