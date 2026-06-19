"""Hybrid retrieval + ranking (TSD §6.4, docs/RETRIEVAL.md, ADR-016).

Dense (cosine) + keyword (FTS/LIKE) candidates → Reciprocal Rank Fusion (k=60) → graph
expansion (PPR-lite: pull neighbors of strong hits) → multi-signal ranking (RRF + similarity +
salience + recency + confidence + graph proximity) → MMR-lite dedup → optional token-budgeted
packing. No LLM on this hot path. Hub/connector nodes bridge the graph but never surface.
"""

from __future__ import annotations

import re
from datetime import datetime

from .decay import recency, salience
from .models import Hit, Status, utcnow

RRF_K = 60

# Ranking weights (sum ~1.0); tunable per ADR-016.
W_RRF = 0.35
W_SIM = 0.22
W_SAL = 0.12
W_REC = 0.08
W_CONF = 0.08
W_GRAPH = 0.15

# Advisory down-weight for facts a supersession marked possibly-stale (v2 plan §1.3). They stay
# retrievable (never hidden) but rank below fresh facts unless nothing else matches.
STALE_PENALTY = 0.6

_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _in_scope(mem, scope: str | None) -> bool:
    return scope is None or mem.scope == scope or mem.scope == "global"


def recall(
    store,  # SqliteStore
    embedder,  # Embedder
    query: str,
    *,
    scope: str | None = None,
    k: int = 8,
    candidate_n: int = 50,
    expand: bool = True,
    expand_depth: int = 1,
    now: datetime | None = None,
) -> list[Hit]:
    now = now or utcnow()
    qvec = embedder.embed([query])[0]
    dense = store.vector_search(qvec, candidate_n, scope=scope)  # [(id, sim)]
    sparse = store.keyword_search(query, candidate_n, scope=scope)  # [(id, score)]

    rrf: dict[str, float] = {}
    for rank, (mid, _) in enumerate(dense):
        rrf[mid] = rrf.get(mid, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, (mid, _) in enumerate(sparse):
        rrf[mid] = rrf.get(mid, 0.0) + 1.0 / (RRF_K + rank + 1)
    if not rrf:
        return []

    sim_map = dict(dense)
    max_rrf = max(rrf.values())

    # base candidates: id -> (memory, sim, rrf_norm)
    base: dict[str, tuple] = {}
    for mid, score in rrf.items():
        mem = store.get_memory(mid)
        if mem and mem.status == Status.ACTIVE:
            base[mid] = (mem, sim_map.get(mid, 0.0), score / max_rrf)

    # graph expansion (PPR-lite): neighbors of the strongest seeds gain proximity, and
    # neighbor memories that didn't match textually are pulled in as new candidates.
    graph_score: dict[str, float] = {}
    if expand and base:
        seeds = sorted(base.items(), key=lambda kv: kv[1][2], reverse=True)[:5]
        for sid, (_smem, _sim, srrf) in seeds:
            for nb in store.neighbors(sid, depth=expand_depth):
                graph_score[nb.id] = graph_score.get(nb.id, 0.0) + srrf
                if nb.id not in base and _in_scope(nb, scope):
                    base[nb.id] = (nb, 0.0, 0.0)
    max_graph = max(graph_score.values()) if graph_score else 1.0

    scored: list[Hit] = []
    for mid, (mem, sim, rrf_norm) in base.items():
        if mem.attributes.get("_hub"):
            continue  # connectors bridge the graph but never surface as results
        sal = salience(mem, now)
        rec = recency(mem, now)
        g = graph_score.get(mid, 0.0) / max_graph
        final = (
            W_RRF * rrf_norm
            + W_SIM * max(sim, 0.0)
            + W_SAL * sal
            + W_REC * rec
            + W_CONF * mem.confidence
            + W_GRAPH * g
        )
        if mem.attributes.get("_stale_suspected"):
            final *= STALE_PENALTY
        scored.append(Hit(memory=mem, score=final, similarity=sim, salience=sal))

    scored.sort(key=lambda h: h.score, reverse=True)
    return _mmr_dedup(scored, k)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _mmr_dedup(hits: list[Hit], k: int, sim_cutoff: float = 0.9) -> list[Hit]:
    """Greedy selection dropping near-duplicate content (MMR-lite, ADR-016)."""
    selected: list[Hit] = []
    sel_tokens: list[set[str]] = []
    for h in hits:
        toks = _tokens(h.memory.content)
        if any(_jaccard(toks, s) >= sim_cutoff for s in sel_tokens):
            continue
        selected.append(h)
        sel_tokens.append(toks)
        if len(selected) >= k:
            break
    return selected


def pack_context(hits: list[Hit], budget_tokens: int = 1500, *, min_ratio: float = 0.22) -> str:
    """Pack hits into a context block under a token budget, most-salient at head and tail.

    Tighter packing (v2 plan §2.3): drop near-duplicate facts and marginal tail hits (those
    scoring below `min_ratio` of the top hit) before packing — fewer, stronger facts beat a
    stuffed window ("context rot"). Strongest memories go at the edges to beat "lost in the
    middle" (docs/RETRIEVAL.md). Token estimate ~ 4 chars/token.
    """
    ranked = sorted(hits, key=lambda h: h.score, reverse=True)
    ranked = _dedup_near(ranked)
    if ranked:
        floor = ranked[0].score * min_ratio
        ranked = [ranked[0]] + [h for h in ranked[1:] if h.score >= floor]
    chosen: list[Hit] = []
    used = 0
    for h in ranked:
        cost = max(len(h.memory.content) // 4, 1)
        if used + cost > budget_tokens:
            break
        chosen.append(h)
        used += cost
    if not chosen:
        return ""
    lines = [f"- ({h.memory.type.value}) {h.memory.content}" for h in chosen_order(chosen)]
    return "\n".join(lines)


def _dedup_near(hits: list[Hit], sim_cutoff: float = 0.85) -> list[Hit]:
    """Drop near-duplicate content by token overlap (semantically-related distractors hurt most)."""
    kept: list[Hit] = []
    kept_tokens: list[set[str]] = []
    for h in hits:
        toks = _tokens(h.memory.content)
        if any(_jaccard(toks, s) >= sim_cutoff for s in kept_tokens):
            continue
        kept.append(h)
        kept_tokens.append(toks)
    return kept


def chosen_order(chosen: list[Hit]) -> list[Hit]:
    """Place strongest memories at the edges of the list (head and tail)."""
    out: list[Hit] = [None] * len(chosen)  # type: ignore[list-item]
    lo, hi = 0, len(chosen) - 1
    for i, h in enumerate(chosen):  # chosen is strongest-first
        if i % 2 == 0:
            out[lo] = h
            lo += 1
        else:
            out[hi] = h
            hi -= 1
    return out
