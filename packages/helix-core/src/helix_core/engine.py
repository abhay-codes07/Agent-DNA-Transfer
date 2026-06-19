"""Helix engine façade.

The single API the CLI, MCP server, and SDK call. Phase 1 implements the full local $0/offline
loop: remember (redact → extract → embed → consolidate → store) and recall (hybrid retrieve →
rank). Transfer (export/import/merge) lands in Phase 4.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .config import Config, load
from .consolidate import ConsolidationResult, consolidate
from .decay import reinforce, salience
from .embed import get_embedder
from .extract.deterministic import DeterministicExtractor
from .ids import edge_id, new_id, slug
from .models import (
    GLOBAL,
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
        self._reranker_obj = None
        self.extractor = self._build_extractor()

    def _reranker(self):
        if self._reranker_obj is None:
            from .rerank import get_reranker

            self._reranker_obj = get_reranker(self.config)
        return self._reranker_obj

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
        clean = redact(content, pii=self.config.redact_pii)
        candidates = self.extractor.extract(clean, scope=scope, force=force)
        results: list[ConsolidationResult] = []
        with self.store.tx():
            for cand in candidates:
                # Defensive re-scrub: an LLM extractor may rephrase; a secret must never persist.
                cand.content = redact(cand.content, pii=self.config.redact_pii)
                emb = self.embedder.embed([cand.content])[0]
                prov = Provenance(agent=source, extractor=self.extractor.name, origin=origin)
                res = consolidate(self.store, cand, emb, prov, router=self.router)
                self._link_to_scope(res.memory_id, scope)
                results.append(res)
        return results

    def _link_to_scope(self, memory_id: str, scope: Scope) -> None:
        """Attach a memory to its project hub node so graph expansion can bridge facts."""
        if not scope.startswith("project:"):
            return
        hub_id = self._ensure_hub(scope)
        self.store.add_edge(
            Edge(
                id=edge_id(hub_id, "has_member", memory_id),
                from_id=hub_id,
                to_id=memory_id,
                relation="has_member",
            )
        )

    def _ensure_hub(self, scope: Scope) -> str:
        name = scope.split(":", 1)[1]
        hub_id = f"hub_{slug(scope)}"
        if self.store.get_memory(hub_id) is None:
            now = utcnow()
            hub = Memory(
                id=hub_id,
                type=MemoryType.ENTITY,
                content=f"Project: {name}",
                scope=scope,
                cognitive=Cognitive.ENTITY,
                attributes={"_hub": True},
                importance=0.2,
                confidence=0.9,
                valid_from=now,
                recorded_at=now,
                created_at=now,
                updated_at=now,
                last_seen_at=now,
            )
            self.store.upsert_memory(hub)  # no embedding -> invisible to vector search
        return hub_id

    def remember_batch(
        self,
        contents: list[str],
        *,
        scope: Scope = GLOBAL,
        source: str = "cli",
        origin: Origin = Origin.USER_ASSERTED,
        force: bool = False,
    ) -> list[ConsolidationResult]:
        """Remember many slices efficiently — one LLM extraction call for the whole batch.

        The cost lever (heuristic gate) still drops slices with no durable fact; only the
        survivors are sent to the model, together, in a single call.
        """
        cleaned = [redact(c, pii=self.config.redact_pii) for c in contents]
        per_slice = self.extractor.extract_batch(cleaned, scope=scope, force=force)
        results: list[ConsolidationResult] = []
        with self.store.tx():
            for cands in per_slice:
                for cand in cands:
                    cand.content = redact(cand.content, pii=self.config.redact_pii)
                    emb = self.embedder.embed([cand.content])[0]
                    prov = Provenance(agent=source, extractor=self.extractor.name, origin=origin)
                    res = consolidate(self.store, cand, emb, prov, router=self.router)
                    self._link_to_scope(res.memory_id, cand.scope)
                    results.append(res)
        return results

    def ingest(self, text: str, *, scope: Scope = GLOBAL, source: str = "ingest") -> dict:
        """Seed memory from a block of notes/markdown: slice into facts and remember them."""
        slices = _slice_notes(text)
        results = self.remember_batch(
            slices, scope=scope, source=source, origin=Origin.AGENT_INGESTED, force=True
        )
        ops: dict[str, int] = {"ADD": 0, "UPDATE": 0, "NOOP": 0, "SUPERSEDE": 0}
        for r in results:
            ops[r.op] = ops.get(r.op, 0) + 1
        return {"slices": len(slices), "stored": ops}

    def ingest_file(self, path, *, scope: Scope = GLOBAL) -> dict:
        # utf-8-sig strips a BOM if present (e.g. files written by some editors/shells).
        text = Path(path).read_text(encoding="utf-8-sig")
        return self.ingest(text, scope=scope, source="ingest:file")

    def ingest_dir(self, path, *, scope: Scope = GLOBAL, pattern: str = "*.md") -> dict:
        files = 0
        slices = 0
        stored: dict[str, int] = {"ADD": 0, "UPDATE": 0, "NOOP": 0, "SUPERSEDE": 0}
        for fp in sorted(Path(path).rglob(pattern)):
            res = self.ingest_file(fp, scope=scope)
            files += 1
            slices += res["slices"]
            for key, val in res["stored"].items():
                stored[key] = stored.get(key, 0) + val
        return {"files": files, "slices": slices, "stored": stored}

    def export_markdown(self, path) -> int:
        """Dump active memories to human-readable Markdown (portable, editable). Returns count."""
        from .serialize import memories_to_markdown

        mems = self.list_memories(limit=1_000_000)
        Path(path).write_text(memories_to_markdown(mems), encoding="utf-8")
        return len(mems)

    # --- read path ------------------------------------------------------------
    def recall(
        self,
        query: str,
        *,
        scope: Scope | None = None,
        k: int = 8,
        touch: bool = False,
        rerank: bool | None = None,
        now: datetime | None = None,
    ) -> list[Hit]:
        """Hybrid retrieval + ranking. With touch=True, reinforce the surfaced memories.

        If `rerank` (or `config.rerank`) is set, an optional reranker re-scores the top
        candidates (v2 plan §2.1) — a wider candidate set is fetched, then trimmed to `k`.
        """
        use_rerank = self.config.rerank if rerank is None else rerank
        fetch_k = max(k, 30) if use_rerank else k
        hits = recall(self.store, self.embedder, query, scope=scope, k=fetch_k, now=now)
        if use_rerank and hits:
            from .rerank import apply_rerank

            hits = apply_rerank(self._reranker(), query, hits, k)
        else:
            hits = hits[:k]
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
            mems = [
                m
                for m in self.store.all_memories(scope=scope, limit=200)
                if not m.attributes.get("_hub")
            ]
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

    def conflicts(self) -> list[dict]:
        """Unresolved conflicting fact pairs (both still active), surfaced for the user to judge.

        v2 plan §1.5: Helix keeps contradictory facts side-by-side with provenance rather than
        silently picking a winner. Returns each pair with content + source.
        """
        out: list[dict] = []
        for e in self.store.edges_by_relation("conflicts_with"):
            a = self.store.get_memory(e.from_id)
            b = self.store.get_memory(e.to_id)
            if a and b and a.status == Status.ACTIVE and b.status == Status.ACTIVE:
                out.append(
                    {
                        "a": {"id": a.id, "content": a.content, "type": a.type.value},
                        "b": {"id": b.id, "content": b.content, "type": b.type.value},
                    }
                )
        return out

    def review_queue(self, *, limit: int = 100) -> list[dict]:
        """Facts that want human attention: possibly-stale or in conflict (v2 plan §6.3).

        Prioritized stale-first (they degrade silently); never auto-changes anything.
        """
        items: list[dict] = []
        for m in self.store.all_memories(limit=100000):
            if m.attributes.get("_hub"):
                continue
            if m.attributes.get("_stale_suspected"):
                items.append(
                    {
                        "id": m.id,
                        "kind": "stale",
                        "content": m.content,
                        "reason": m.attributes.get("_stale_reason", ""),
                    }
                )
            elif m.attributes.get("_conflict"):
                items.append(
                    {
                        "id": m.id,
                        "kind": "conflict",
                        "content": m.content,
                        "reason": "contradicts another fact",
                    }
                )
        items.sort(key=lambda d: 0 if d["kind"] == "stale" else 1)
        return items[:limit]

    def resolve_stale(self, memory_id: str, *, keep: bool) -> Memory | None:
        """Clear a stale/conflict flag: keep the fact (clear the flag) or forget it."""
        mem = self.store.get_memory(memory_id)
        if mem is None:
            return None
        if not keep:
            self.forget(memory_id)
            return self.store.get_memory(memory_id)
        with self.store.tx():
            for key in ("_stale_suspected", "_stale_reason", "_conflict"):
                mem.attributes.pop(key, None)
            mem.updated_at = utcnow()
            self.store.upsert_memory(mem)
            self.store.add_history("review-keep", mem.id, {})
        return mem

    def erase(self, id_or_query: str) -> dict:
        """Irreversibly erase a fact and cascade (GDPR Art. 17 / v2 plan §4.1).

        Unlike `forget` (soft, recoverable), this hard-deletes the memory, its embedding, its
        FTS row, and its edges; records a tombstone so a later merge can't resurrect it; and
        flags facts *derived from* it as possibly-stale (their basis is gone). We delete discrete
        vectors, not model weights — no "machine unlearning" required.
        """
        mem = self.store.get_memory(id_or_query)
        if mem is None:
            hits = self.recall(id_or_query, k=1)
            if not hits:
                return {"erased": 0}
            mem = hits[0].memory
        dependents = [
            e.from_id for e in self.store.edges_by_relation("derived_from") if e.to_id == mem.id
        ]
        with self.store.tx():
            for did in dependents:
                dm = self.store.get_memory(did)
                if dm is not None:
                    dm.attributes["_stale_suspected"] = True
                    dm.attributes["_stale_reason"] = "a source fact was erased"
                    dm.updated_at = utcnow()
                    self.store.upsert_memory(dm)
            self.store.delete_memory(mem.id, tombstone=True)
            self.store.add_history("erase", mem.id, {"dependents": len(dependents)})
        return {"erased": 1, "id": mem.id, "dependents_flagged": len(dependents)}

    def export_subject(self, subject: str, *, k: int = 200) -> dict:
        """Data-subject access export (DSAR): everything Helix knows about a subject + lineage.

        Returns each matching fact with its provenance and confidence — human-readable and
        portable (GDPR Art. 15). `subject` is matched by recall.
        """
        hits = self.recall(subject, k=k)
        facts = []
        for h in hits:
            m = h.memory
            facts.append(
                {
                    "id": m.id,
                    "type": m.type.value,
                    "content": m.content,
                    "scope": m.scope,
                    "confidence": m.confidence,
                    "created_at": m.created_at.isoformat(),
                    "provenance": [
                        {"agent": p.agent, "extractor": p.extractor, "origin": p.origin.value}
                        for p in m.provenance
                    ],
                }
            )
        return {"subject": subject, "count": len(facts), "facts": facts}

    def list_memories(self, *, scope: Scope | None = None, limit: int = 100) -> list[Memory]:
        return [
            m
            for m in self.store.all_memories(scope=scope, limit=limit)
            if not m.attributes.get("_hub")
        ]

    # --- scoped sharing + quarantine (v2 plan §3.1 / §3.2) -------------------
    def _trusted_contributors(self) -> set[str]:
        raw = self.store.get_meta("trusted_contributors")
        return set(json.loads(raw)) if raw else set()

    def trust_contributor(self, name: str) -> None:
        """Pin a contributor as trusted (TOFU): their future shared facts import directly."""
        names = self._trusted_contributors()
        names.add(name)
        self.store.set_meta("trusted_contributors", json.dumps(sorted(names)))

    def export_share(
        self,
        out_path,
        *,
        scope: Scope | None = None,
        contributor: str | None = None,
        pii: bool = True,
    ) -> dict:
        """Write a scoped, redacted, attributable share bundle (JSON) for a teammate/agent."""
        from .sharing import build_bundle

        who = contributor or self.config.strand
        bundle = build_bundle(
            self.list_memories(limit=1_000_000), contributor=who, scope=scope, pii=pii
        )
        Path(out_path).write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        return {"facts": len(bundle["facts"]), "scope": scope, "path": str(out_path)}

    def import_share(self, path_or_bundle, *, trust: bool = False) -> dict:
        """Import a share bundle. Untrusted contributors are quarantined until reviewed.

        Tampered facts (failed fingerprint) and tombstoned (previously erased) facts are dropped.
        """
        from .sharing import verify_bundle

        if isinstance(path_or_bundle, dict):
            bundle = path_or_bundle
        else:
            bundle = json.loads(Path(path_or_bundle).read_text(encoding="utf-8"))
        valid, tampered = verify_bundle(bundle)
        contributor = bundle.get("contributor", "unknown")
        trusted = trust or contributor in self._trusted_contributors()
        added = quarantined = skipped = 0
        with self.store.tx():
            for f in valid:
                if self.store.is_tombstoned(f.get("fingerprint", "")):
                    skipped += 1
                    continue
                mtype = MemoryType(f["type"])
                content = f["content"]
                if trusted:
                    cand = CandidateFact(
                        type=mtype,
                        content=content,
                        scope=f.get("scope", GLOBAL),
                        importance=f.get("importance", 0.5),
                        confidence=f.get("confidence", 0.5),
                    )
                    emb = self.embedder.embed([content])[0]
                    prov = Provenance(
                        agent=contributor, extractor="share", origin=Origin.AGENT_INGESTED
                    )
                    consolidate(self.store, cand, emb, prov, router=self.router)
                    added += 1
                else:
                    now = utcnow()
                    mem = Memory(
                        id=new_id(mtype.value, content),
                        type=mtype,
                        content=content,
                        scope=f.get("scope", GLOBAL),
                        importance=f.get("importance", 0.5),
                        confidence=f.get("confidence", 0.5),
                        status=Status.QUARANTINED,
                        attributes={"_contributor": contributor},
                        provenance=[
                            Provenance(
                                agent=contributor,
                                extractor="share",
                                origin=Origin.AGENT_INGESTED,
                            )
                        ],
                        valid_from=now,
                        recorded_at=now,
                        created_at=now,
                        updated_at=now,
                        last_seen_at=now,
                    )
                    self.store.upsert_memory(mem, self.embedder.embed([content])[0])
                    self.store.add_history("quarantine", mem.id, {"from": contributor})
                    quarantined += 1
            if trust and contributor != "unknown":
                self.trust_contributor(contributor)
        return {
            "added": added,
            "quarantined": quarantined,
            "tampered": len(tampered),
            "skipped_tombstoned": skipped,
            "contributor": contributor,
        }

    def review_incoming(self, *, limit: int = 100) -> list[dict]:
        """List quarantined (untrusted) facts awaiting approval."""
        rows = self.store.all_memories(statuses=(Status.QUARANTINED.value,), limit=limit)
        return [
            {"id": m.id, "content": m.content, "from": m.attributes.get("_contributor", "?")}
            for m in rows
        ]

    def approve_incoming(self, memory_id: str) -> Memory | None:
        """Accept a quarantined fact into active memory."""
        mem = self.store.get_memory(memory_id)
        if mem is None or mem.status != Status.QUARANTINED:
            return None
        with self.store.tx():
            mem.status = Status.ACTIVE
            mem.attributes.pop("_contributor", None)
            mem.updated_at = utcnow()
            self.store.upsert_memory(mem)
            self.store.add_history("approve-incoming", mem.id, {})
        return mem

    def reject_incoming(self, memory_id: str) -> bool:
        """Discard a quarantined fact (tombstoned so a re-share won't re-stage it)."""
        with self.store.tx():
            ok = self.store.delete_memory(memory_id, tombstone=True)
            if ok:
                self.store.add_history("reject-incoming", memory_id, {})
        return ok

    def edit_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        scope: str | None = None,
        type: str | None = None,
        importance: float | None = None,
    ) -> Memory | None:
        """Edit a memory in place (re-embeds if the content changed). Returns the updated memory."""
        mem = self.store.get_memory(memory_id)
        if mem is None:
            return None
        content_changed = content is not None and content != mem.content
        if content is not None:
            mem.content = content
        if scope is not None:
            mem.scope = scope
        if type is not None:
            from .models import COGNITIVE_OF

            mem.type = MemoryType(type)
            mem.cognitive = COGNITIVE_OF[mem.type]
        if importance is not None:
            mem.importance = min(max(float(importance), 0.0), 1.0)
        mem.updated_at = utcnow()
        emb = self.embedder.embed([mem.content])[0] if content_changed else None
        with self.store.tx():
            self.store.upsert_memory(mem, emb)
            self.store.add_history("edit", mem.id, {"content_changed": content_changed})
        return mem

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.store.get_memory(memory_id)

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
        self,
        *,
        now: datetime | None = None,
        archive_below: float = 0.05,
        min_age_days: float = 30.0,
    ) -> dict:
        """Decay-driven housekeeping: archive stale, low-salience memories (never delete).

        Reflection (insight synthesis) is separate — see `reflect()`; this is the deterministic,
        $0 archival part of consolidation (docs/CONSOLIDATION.md).
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

    def consolidate_sleep(self, *, min_reinforced: int = 2, reflect: bool = True) -> dict:
        """Offline 'sleep-time' consolidation (v2 plan §1.2), run off the hot path.

        Two stages, both keeping the $0 default:
          1. **Episodic → semantic** (deterministic): an episode recalled/reinforced enough times
             is promoted to a durable semantic fact — repetition-driven semanticization (CLS).
          2. **Insight synthesis** (LLM, optional): clusters of facts are distilled into
             higher-level insights that cite their sources (reuses `reflect`, ≥2 sources).
        """
        promoted = 0
        now = utcnow()
        with self.store.tx():
            for mem in self.store.all_memories(limit=100000):
                if mem.attributes.get("_hub") or mem.attributes.get("_consolidated"):
                    continue
                if mem.cognitive == Cognitive.EPISODIC and (
                    float(mem.attributes.get("_reinforced", 0)) >= min_reinforced
                ):
                    mem.cognitive = Cognitive.SEMANTIC
                    if mem.type == MemoryType.EPISODE:
                        mem.type = MemoryType.FACT
                    mem.confidence = min(mem.confidence + 0.1, 1.0)
                    mem.attributes["_consolidated"] = True
                    mem.updated_at = now
                    self.store.upsert_memory(mem)
                    self.store.add_history("consolidate-promote", mem.id, {})
                    promoted += 1
        insights = self.reflect()["insights"] if reflect else 0
        return {"promoted": promoted, "insights": insights}

    def reflect(self, *, scope: Scope | None = None, min_cluster: int = 3) -> dict:
        """Synthesize higher-level insights from clusters of related memories (ADR-015).

        Groups active memories by scope and asks the LLM to distill each sizeable cluster into a
        couple of concise insights, stored as new memories that **cite their sources** (linked
        with `derived_from` edges, ADR-029). Needs an LLM; the deterministic path makes none.
        """
        mems = [
            m
            for m in self.store.all_memories(scope=scope, limit=100000)
            if not m.attributes.get("_hub") and not m.attributes.get("_reflection")
        ]
        clusters: dict[str, list[Memory]] = {}
        for m in mems:
            clusters.setdefault(m.scope, []).append(m)

        created = examined = 0
        with self.store.tx():
            for cscope, group in clusters.items():
                if len(group) < min_cluster:
                    continue
                examined += 1
                for text in self._synthesize(group):
                    cand = CandidateFact(
                        type=MemoryType.FACT,
                        content=text,
                        scope=cscope,
                        cognitive=Cognitive.SEMANTIC,
                        importance=0.7,
                        confidence=0.7,
                        attributes={"_reflection": True, "sources": [m.id for m in group[:10]]},
                    )
                    emb = self.embedder.embed([text])[0]
                    prov = Provenance(
                        agent="reflect", extractor="reflect", origin=Origin.AGENT_INGESTED
                    )
                    res = consolidate(self.store, cand, emb, prov, router=self.router)
                    if res.op in ("ADD", "UPDATE", "SUPERSEDE"):
                        for src in group[:10]:
                            self.store.add_edge(
                                Edge(
                                    id=edge_id(res.memory_id, "derived_from", src.id),
                                    from_id=res.memory_id,
                                    to_id=src.id,
                                    relation="derived_from",
                                )
                            )
                        created += 1
        return {"clusters_examined": examined, "insights": created}

    def _synthesize(self, group: list[Memory]) -> list[str]:
        if not (self.router and self.router.available()):
            return []  # natural-language insight synthesis needs an LLM
        facts = "\n".join(f"- {m.content}" for m in group[:30])
        prompt = (
            "From these facts about a project or topic, write 1-2 concise higher-level insights "
            '(each a single sentence). Return JSON {"insights": ["..."]}.\nFACTS:\n' + facts
        )
        try:
            result = self.router.complete(
                prompt,
                system="You synthesize higher-level insights from a developer's memory.",
                json_mode=True,
            )
            data = json.loads(result.text)
            items = data.get("insights", []) if isinstance(data, dict) else []
            return [str(x).strip() for x in items if str(x).strip()][:3]
        except Exception:
            return []

    # --- copilot + observability (v2 plan §6.1 / §6.2) -----------------------
    def about(self, subject: str, *, k: int = 8) -> dict:
        """Answer "what do you know about X?" — sourced facts + related facts + flags.

        Backs the memory copilot: every returned fact carries its provenance and any
        stale/conflict flag so the answer is inspectable, not a black box.
        """
        hits = self.recall(subject, k=k)
        facts = []
        for h in hits:
            m = h.memory
            facts.append(
                {
                    "id": m.id,
                    "type": m.type.value,
                    "content": m.content,
                    "confidence": round(m.confidence, 2),
                    "source": (m.provenance[0].agent if m.provenance else None),
                    "stale": bool(m.attributes.get("_stale_suspected")),
                    "conflict": bool(m.attributes.get("_conflict")),
                }
            )
        related: list[dict] = []
        if hits:
            for nb in self.store.neighbors(hits[0].memory.id, depth=1)[:5]:
                if not nb.attributes.get("_hub"):
                    related.append({"id": nb.id, "content": nb.content})
        return {"subject": subject, "facts": facts, "related": related, "count": len(facts)}

    def analytics(self) -> dict:
        """A snapshot of the memory's health for the observability dashboard."""
        from collections import Counter

        mems = self.list_memories(limit=1_000_000)
        by_type = Counter(m.type.value for m in mems)
        by_day: Counter = Counter(m.created_at.date().isoformat() for m in mems)
        most = sorted(mems, key=lambda m: float(m.attributes.get("_reinforced", 0)), reverse=True)
        stale = sum(1 for m in mems if m.attributes.get("_stale_suspected"))
        return {
            "total": len(mems),
            "by_type": dict(by_type),
            "facts_per_day": dict(sorted(by_day.items())),
            "most_recalled": [
                {"content": m.content, "recalled": int(m.attributes.get("_reinforced", 0))}
                for m in most[:5]
                if m.attributes.get("_reinforced")
            ],
            "to_review": stale + len(self.conflicts()),
            "conflicts": len(self.conflicts()),
            "stale_suspected": stale,
            "quarantined": len(self.review_incoming()),
            "tombstones": self.store.tombstone_count(),
        }

    # Estimated cloud-equivalent prices for the "$0 saved" meter (transparent, conservative).
    _EMBED_USD = 0.0000004  # ~20 tokens @ text-embedding-3-small ($0.02/1M)
    _OP_USD = 0.00008  # an avoided cloud memory extract/recall call (conservative)

    def savings(self) -> dict:
        """The "$0 meter": estimate what running locally has saved vs a cloud memory service."""
        mems = self.store.count()
        ops = self.store.history_count()
        est = mems * self._EMBED_USD + ops * self._OP_USD
        return {
            "local_embeddings": mems,
            "local_operations": ops,
            "llm_enabled": self.router is not None and self.router.available(),
            "est_usd_saved": round(est, 4),
            "note": "estimate vs a hosted memory API; Helix runs these locally at $0",
        }

    # --- procedural / skill memory (v2 plan §1.1) ----------------------------
    def learn_procedure(
        self,
        trigger: str,
        steps: list[str],
        *,
        scope: Scope = GLOBAL,
        success_signal: str | None = None,
        source: str = "cli",
    ) -> str:
        """Store a reusable how-to recipe keyed by a trigger condition.

        Unlike a declarative fact (what is true), a procedure captures *how to act* — the gap
        that makes a coding-agent memory more than a knowledge base. `steps` are ordered;
        `success_signal` is how the agent knows it worked (e.g. "tests pass"). Reliability grows
        as the procedure is confirmed via `record_procedure_outcome`.
        """
        clean_steps = [redact(s, pii=self.config.redact_pii) for s in steps]
        content = redact(f"When {trigger}: " + "; ".join(clean_steps), pii=self.config.redact_pii)
        now = utcnow()
        mem = Memory(
            id=new_id("procedure", content),
            type=MemoryType.PROCEDURE,
            content=content,
            scope=scope,
            cognitive=Cognitive.PROCEDURAL,
            attributes={
                "trigger": trigger,
                "steps": clean_steps,
                "success_signal": success_signal,
                "success_count": 0,
                "reliability": 0.5,
                "verified_at": None,
            },
            importance=0.6,
            confidence=0.6,
            provenance=[
                Provenance(agent=source, extractor="procedure", origin=Origin.USER_ASSERTED)
            ],
            valid_from=now,
            recorded_at=now,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )
        with self.store.tx():
            self.store.upsert_memory(mem, self.embedder.embed([mem.content])[0])
            self._link_to_scope(mem.id, scope)
            self.store.add_history("learn-procedure", mem.id, {"steps": len(clean_steps)})
        return mem.id

    def recall_procedures(
        self, situation: str, *, scope: Scope | None = None, k: int = 5
    ) -> list[dict]:
        """Find procedures whose trigger matches the situation, ranked by match × reliability.

        Retrieval is gated on the trigger (how-to memory is situation→action), then blended with
        each procedure's earned reliability so confirmed recipes float to the top.
        """
        from .embed.base import cosine

        procs = [
            m
            for m in self.store.all_memories(scope=scope, limit=100000)
            if m.type == MemoryType.PROCEDURE
        ]
        if not procs:
            return []
        qv = self.embedder.embed([situation])[0]
        scored: list[tuple[float, Memory]] = []
        for p in procs:
            trig = str(p.attributes.get("trigger") or p.content)
            sim = cosine(qv, self.embedder.embed([trig])[0])
            reliability = float(p.attributes.get("reliability", 0.5))
            scored.append((0.7 * sim + 0.3 * reliability, p))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            {
                "id": p.id,
                "trigger": p.attributes.get("trigger"),
                "steps": p.attributes.get("steps", []),
                "reliability": round(float(p.attributes.get("reliability", 0.5)), 2),
                "success_count": int(p.attributes.get("success_count", 0)),
                "score": round(s, 3),
            }
            for s, p in scored[:k]
        ]

    def record_procedure_outcome(self, proc_id: str, success: bool) -> dict | None:
        """Record whether a procedure worked. Success raises reliability (SM-2-style); failure lowers it."""
        p = self.store.get_memory(proc_id)
        if p is None or p.type != MemoryType.PROCEDURE:
            return None
        now = utcnow()
        with self.store.tx():
            if success:
                sc = int(p.attributes.get("success_count", 0)) + 1
                p.attributes["success_count"] = sc
                p.attributes["reliability"] = min(0.5 + 0.1 * sc, 1.0)
                p.attributes["verified_at"] = now.isoformat()
                reinforce(p, now)
            else:
                p.attributes["reliability"] = max(
                    float(p.attributes.get("reliability", 0.5)) - 0.15, 0.0
                )
            p.updated_at = now
            self.store.upsert_memory(p)
            self.store.add_history("procedure-outcome", p.id, {"success": success})
        return {
            "id": p.id,
            "reliability": round(float(p.attributes["reliability"]), 2),
            "success_count": int(p.attributes.get("success_count", 0)),
        }

    # --- diagnostics ----------------------------------------------------------
    def stats(self) -> dict:
        return {
            "strand_path": str(self.config.strand_path),
            "embedding_model": self.embedder.model,
            "embedding_dim": self.embedder.dim,
            "fts5": self.store.fts,
            "active_memories": self.store.count(),
            "archived_memories": self.store.count((Status.ARCHIVED.value,)),
            "tombstones": self.store.tombstone_count(),
            "extractor": getattr(self.extractor, "name", "deterministic"),
            "rerank": self.config.rerank,
            "reranker": self._reranker().name if self.config.rerank else "off",
            "llm_provider": self.config.llm_provider,
            "llm_enabled": self.router is not None and self.router.available(),
            "fastembed": _has("fastembed"),
            "sqlite_vec": _has("sqlite_vec"),
        }

    def close(self) -> None:
        self.store.close()

    # transfer (Phase 4 — the portable .dna strand) ---------------------------
    def _passphrase(self, override: str | None) -> str:
        pw = override or self.config.passphrase
        if not pw:
            raise ValueError(
                "a passphrase is required for .dna — pass --passphrase or set HELIX_PASSPHRASE"
            )
        return pw

    @property
    def _identity_path(self) -> Path:
        return self.config.home / "identity.key"

    def export_strand(self, out_path, *, passphrase: str | None = None, label: str = ""):
        """Package the strand into a signed, encrypted, portable .dna file."""
        from .strand.codec import export_dna

        return export_dna(
            self.store,
            Path(out_path),
            passphrase=self._passphrase(passphrase),
            identity_path=self._identity_path,
            label=label,
        )

    def verify_strand(self, path) -> dict:
        from .strand.codec import verify_dna

        return verify_dna(Path(path))

    def import_strand(
        self,
        path,
        *,
        passphrase: str | None = None,
        as_strand: str | None = None,
        replace: bool = False,
        reembed: bool = True,
    ) -> dict:
        """Import a .dna into a new strand, or replace the active one (rollback).

        If the imported strand's embedding space differs from the local embedder, its vectors
        are re-embedded so recall works on this machine (ADR-006 / Phase 4 hardening).
        """
        from .strand.codec import import_dna

        pw = self._passphrase(passphrase)
        if replace:
            self.store.close()
            try:
                manifest = import_dna(Path(path), self.config.strand_path, passphrase=pw)
            finally:
                self.store = SqliteStore(self.config.strand_path)
            reembedded = self._reembed_if_needed(self.store) if reembed else 0
            return {
                "strand": self.config.strand,
                "dest": str(self.config.strand_path),
                "manifest": manifest,
                "reembedded": reembedded,
            }
        name = as_strand or "imported"
        dest = self.config.home / f"{name}.helix.db"
        manifest = import_dna(Path(path), dest, passphrase=pw)
        reembedded = 0
        if reembed:
            dest_store = SqliteStore(dest)
            try:
                reembedded = self._reembed_if_needed(dest_store)
            finally:
                dest_store.close()
        return {"strand": name, "dest": str(dest), "manifest": manifest, "reembedded": reembedded}

    def _reembed_if_needed(self, store: SqliteStore) -> int:
        if store.get_meta("embedding_model") == self.embedder.model:
            return 0
        return store.reembed(self.embedder)

    def merge_strand(self, path, *, passphrase: str | None = None) -> dict:
        """Merge another .dna into the current strand, reusing consolidation (dedup)."""
        from .strand.codec import import_dna

        pw = self._passphrase(passphrase)
        ops = {"ADD": 0, "UPDATE": 0, "NOOP": 0, "SUPERSEDE": 0}
        with tempfile.TemporaryDirectory() as d:
            other_path = Path(d) / "other.helix.db"
            manifest = import_dna(Path(path), other_path, passphrase=pw)
            other = SqliteStore(other_path)
            try:
                from .stores.sqlite_store import content_fingerprint

                with self.store.tx():
                    for mem in other.all_memories(limit=1_000_000):
                        if mem.attributes.get("_hub"):
                            continue
                        # Tombstoned (erased) facts must never be resurrected by a merge.
                        if self.store.is_tombstoned(content_fingerprint(mem)):
                            ops["NOOP"] += 1
                            continue
                        cand = CandidateFact(
                            type=mem.type,
                            content=mem.content,
                            scope=mem.scope,
                            cognitive=mem.cognitive,
                            attributes=dict(mem.attributes),
                            importance=mem.importance,
                            confidence=mem.confidence,
                        )
                        emb = self.embedder.embed([mem.content])[0]
                        origin = (
                            mem.provenance[0].origin if mem.provenance else Origin.USER_ASSERTED
                        )
                        prov = Provenance(agent="merge", extractor="merge", origin=origin)
                        res = consolidate(self.store, cand, emb, prov, router=self.router)
                        self._link_to_scope(res.memory_id, mem.scope)
                        ops[res.op] += 1
            finally:
                other.close()
        return {"merged": ops, "from_strand": manifest.strand_id}

    def diff_strand(self, path, *, passphrase: str | None = None) -> dict:
        """Compare the current strand with a .dna: what's added/removed/common."""
        pw = self._passphrase(passphrase)
        from .strand.codec import import_dna

        mine = {(m.type.value, m.content) for m in self.list_memories(limit=1_000_000)}
        with tempfile.TemporaryDirectory() as d:
            other_path = Path(d) / "other.helix.db"
            import_dna(Path(path), other_path, passphrase=pw)
            other = SqliteStore(other_path)
            try:
                theirs = {
                    (m.type.value, m.content)
                    for m in other.all_memories(limit=1_000_000)
                    if not m.attributes.get("_hub")
                }
            finally:
                other.close()
        added = theirs - mine  # present in the .dna, missing here
        removed = mine - theirs  # present here, missing in the .dna
        return {
            "added": len(added),
            "removed": len(removed),
            "common": len(mine & theirs),
            "added_samples": [c for _, c in list(added)[:5]],
            "removed_samples": [c for _, c in list(removed)[:5]],
        }

    def history(self, limit: int = 50) -> list[dict]:
        return self.store.history(limit)

    # --- optional encrypted sync (Phase 7) -----------------------------------
    def push(
        self, location: str, *, passphrase: str | None = None, name: str | None = None
    ) -> dict:
        """Export the strand and upload the encrypted .dna to a shared location (E2E)."""
        from .sync import backend_from_uri

        pw = self._passphrase(passphrase)
        name = name or f"{self.config.strand}.dna"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / name
            self.export_strand(str(out), passphrase=pw, label=f"sync:{self.config.strand}")
            data = out.read_bytes()
        backend_from_uri(location).put(name, data)
        return {"pushed": name, "bytes": len(data), "location": location}

    def pull(
        self,
        location: str,
        *,
        passphrase: str | None = None,
        name: str | None = None,
        merge: bool = True,
    ) -> dict:
        """Download an encrypted .dna from a shared location and merge (or replace) locally."""
        from .sync import backend_from_uri

        pw = self._passphrase(passphrase)
        name = name or f"{self.config.strand}.dna"
        data = backend_from_uri(location).get(name)
        if data is None:
            raise ValueError(f"no '{name}' found at {location}")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / name
            f.write_bytes(data)
            if merge:
                res = self.merge_strand(str(f), passphrase=pw)
                res["mode"] = "merge"
                return res
            res = self.import_strand(str(f), passphrase=pw, replace=True)
            res["mode"] = "replace"
            return res

    def rollback(self, path, *, passphrase: str | None = None) -> dict:
        """Restore the active strand from a prior .dna export (verify, then replace)."""
        return self.import_strand(path, passphrase=passphrase, replace=True)


def _has(module: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(module) is not None


_BULLET = re.compile(r"^([-*+]|\d+[.)])\s+")


def _slice_notes(text: str) -> list[str]:
    """Split markdown/text notes into candidate fact slices (skips headers, fences, fluff)."""
    slices: list[str] = []
    in_code = False
    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")  # tolerate a UTF-8 BOM on the first line
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith("#"):
            continue
        if set(line) <= set("-=*_"):  # horizontal rule
            continue
        line = _BULLET.sub("", line).strip()
        if len(line.split()) >= 3:
            slices.append(line)
    return slices
