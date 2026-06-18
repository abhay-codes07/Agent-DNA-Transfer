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
from .ids import edge_id, slug
from .models import (
    GLOBAL,
    Cognitive,
    Edge,
    Hit,
    Memory,
    MemoryType,
    Origin,
    Provenance,
    Scope,
    Status,
    utcnow,
)
from .redaction import redact
from .retrieve import pack_context, recall
from .stores.sqlite_store import SqliteStore


class Engine:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or load()
        self.embedder = get_embedder(self.config)
        self.store = SqliteStore(self.config.strand_path)
        self.store.ensure_embedding_space(self.embedder.model, self.embedder.dim)
        self.router = None
        self.extractor = self._build_extractor()

    def _build_extractor(self):
        """Deterministic by default ($0); LLM-backed when a provider is configured (Phase 3)."""
        cutoff = self.config.heuristic_confidence_cutoff
        deterministic = DeterministicExtractor(cutoff)
        if not self.config.llm_enabled():
            return deterministic
        try:
            from .extract.llm import LLMExtractor
            from .llm.cache import LLMCache
            from .llm.router import LLMRouter

            cache = LLMCache(self.config.home / "llm-cache.db")
            router = LLMRouter(self.config, cache=cache)
            if not router.available():
                return deterministic
            self.router = router
            return LLMExtractor(router, deterministic, cutoff)
        except Exception:
            return deterministic  # never let LLM setup break the $0 path

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
                res = consolidate(self.store, cand, emb, prov)
                self._link_to_scope(res.memory_id, scope)
                results.append(res)
        return results

    def _link_to_scope(self, memory_id: str, scope: Scope) -> None:
        """Attach a memory to its project hub node so graph expansion can bridge facts."""
        if not scope.startswith("project:"):
            return
        hub_id = self._ensure_hub(scope)
        self.store.add_edge(
            Edge(id=edge_id(hub_id, "has_member", memory_id),
                 from_id=hub_id, to_id=memory_id, relation="has_member")
        )

    def _ensure_hub(self, scope: Scope) -> str:
        name = scope.split(":", 1)[1]
        hub_id = f"hub_{slug(scope)}"
        if self.store.get_memory(hub_id) is None:
            now = utcnow()
            hub = Memory(
                id=hub_id, type=MemoryType.ENTITY, content=f"Project: {name}", scope=scope,
                cognitive=Cognitive.ENTITY, attributes={"_hub": True}, importance=0.2,
                confidence=0.9, valid_from=now, recorded_at=now, created_at=now,
                updated_at=now, last_seen_at=now,
            )
            self.store.upsert_memory(hub)  # no embedding -> invisible to vector search
        return hub_id

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
            mems = [m for m in self.store.all_memories(scope=scope, limit=200)
                    if not m.attributes.get("_hub")]
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
        return [m for m in self.store.all_memories(scope=scope, limit=limit)
                if not m.attributes.get("_hub")]

    def relate(self, from_id: str, to_id: str, relation: str, weight: float = 1.0) -> str:
        """Create a typed edge between two memories (memory.relate)."""
        eid = edge_id(from_id, relation, to_id)
        with self.store.tx():
            self.store.add_edge(
                Edge(id=eid, from_id=from_id, to_id=to_id, relation=relation, weight=weight)
            )
            self.store.add_history("relate", from_id, {"to": to_id, "relation": relation})
        return eid

    def maintain(
        self, *, now: datetime | None = None, archive_below: float = 0.05, min_age_days: float = 30.0
    ) -> dict:
        """Decay-driven housekeeping: archive stale, low-salience memories (never delete).

        Reflection/insight synthesis (LLM-assisted) is Phase 3; this is the deterministic,
        $0 part of consolidation (docs/CONSOLIDATION.md).
        """
        now = now or utcnow()
        scanned = archived = 0
        with self.store.tx():
            for mem in self.store.all_memories(limit=100000):
                if mem.attributes.get("_hub"):
                    continue
                scanned += 1
                age_days = (now - mem.last_seen_at).total_seconds() / 86400.0
                if salience(mem, now) < archive_below and age_days >= min_age_days:
                    mem.status = Status.ARCHIVED
                    mem.updated_at = now
                    self.store.upsert_memory(mem)
                    self.store.add_history("archive", mem.id, {"age_days": round(age_days, 1)})
                    archived += 1
        return {"scanned": scanned, "archived": archived}

    # --- diagnostics ----------------------------------------------------------
    def stats(self) -> dict:
        return {
            "strand_path": str(self.config.strand_path),
            "embedding_model": self.embedder.model,
            "embedding_dim": self.embedder.dim,
            "fts5": self.store.fts,
            "active_memories": self.store.count(),
            "archived_memories": self.store.count((Status.ARCHIVED.value,)),
            "extractor": getattr(self.extractor, "name", "deterministic"),
            "llm_provider": self.config.llm_provider,
            "llm_enabled": self.router is not None and self.router.available(),
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
