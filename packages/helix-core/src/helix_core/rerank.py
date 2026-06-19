"""Optional reranking stage (v2 plan §2.1).

After the hybrid recall produces candidates, an optional reranker re-scores the top few by
deeper query↔document relevance. Two implementations:

  * **LexicalReranker** — dependency-free, deterministic, $0. Scores by query-term coverage +
    proximity. Always available; the default so reranking never costs a download or a model load.
  * **CrossEncoderReranker** — a real cross-encoder (sentence-transformers) when installed and
    configured. Higher quality, still local; opt-in via `HELIX_RERANK_MODEL`.

Reranking is OFF by default (small strands don't benefit and it adds latency); enable with
`HELIX_RERANK=1` or `recall(..., rerank=True)`.
"""

from __future__ import annotations

import re

from .models import Hit

_TOKEN = re.compile(r"[A-Za-z0-9]+")
RERANK_N = 25  # how many top candidates to rerank
BLEND = 0.5  # weight of the reranker score vs the original ranking score


def _toks(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class LexicalReranker:
    """Deterministic relevance: query-term coverage + density, normalized to [0, 1]."""

    name = "lexical"

    def score(self, query: str, docs: list[str]) -> list[float]:
        q = set(_toks(query))
        if not q:
            return [0.0] * len(docs)
        out: list[float] = []
        for doc in docs:
            dt = _toks(doc)
            if not dt:
                out.append(0.0)
                continue
            present = q & set(dt)
            coverage = len(present) / len(q)  # how much of the query is answered
            density = sum(1 for t in dt if t in q) / len(dt)  # how on-topic the doc is
            out.append(0.7 * coverage + 0.3 * density)
        return out


class CrossEncoderReranker:
    """Wraps a sentence-transformers CrossEncoder. Constructed only when the lib + model exist."""

    def __init__(self, model: str) -> None:
        from sentence_transformers import CrossEncoder  # imported lazily; optional dependency

        self.name = f"cross-encoder:{model}"
        self._model = CrossEncoder(model)

    def score(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        raw = self._model.predict([(query, d) for d in docs])
        lo, hi = min(raw), max(raw)
        rng = (hi - lo) or 1.0
        return [float((r - lo) / rng) for r in raw]  # normalize to [0, 1]


def get_reranker(config) -> LexicalReranker | CrossEncoderReranker:
    """Return the configured reranker, falling back to the dependency-free lexical one."""
    model = getattr(config, "rerank_model", "") or ""
    if model:
        try:
            return CrossEncoderReranker(model)
        except Exception:
            pass  # never let an optional reranker break the $0 path
    return LexicalReranker()


def apply_rerank(reranker, query: str, hits: list[Hit], k: int, *, n: int = RERANK_N) -> list[Hit]:
    """Rerank the top `n` hits, blend with their original score, and return the top `k`."""
    if not hits:
        return hits
    head, tail = hits[:n], hits[n:]
    rscores = reranker.score(query, [h.memory.content for h in head])
    for h, rs in zip(head, rscores):
        h.score = BLEND * rs + (1 - BLEND) * h.score
    head.sort(key=lambda h: h.score, reverse=True)
    return (head + tail)[:k]
