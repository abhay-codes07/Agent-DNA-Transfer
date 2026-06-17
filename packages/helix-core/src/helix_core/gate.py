"""Heuristic gate — the primary cost lever (docs/COST_OPTIMIZATION.md §3).

Before any model runs, decide cheaply whether a slice likely contains a durable, novel
fact. Most slices are dropped here with ZERO model calls, which is what keeps default cost
at ~$0 even with an LLM enabled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Cues that durable facts are being stated.
_CUES = re.compile(
    r"(?i)\b(remember|always|never|i prefer|we (?:use|decided|chose)|the convention|"
    r"from now on|by default|note that|don'?t use)\b"
)


@dataclass(slots=True)
class GateResult:
    has_fact_score: float  # [0..1] likelihood a durable fact is present
    reasons: list[str]

    def should_extract(self, cutoff: float) -> bool:
        return self.has_fact_score >= cutoff


def evaluate(
    text: str,
    *,
    nearest_distance: float | None = None,
) -> GateResult:
    """Estimate whether `text` is worth extracting from.

    Signals (cheap, local):
      - explicit memory cues,
      - structural hints (length, imperatives),
      - novelty: distance to nearest existing memory (closer == less novel).

    `nearest_distance` is the cosine distance to the closest existing memory, if known.
    """
    score = 0.0
    reasons: list[str] = []

    if _CUES.search(text):
        score += 0.5
        reasons.append("memory-cue")

    words = len(text.split())
    if 4 <= words <= 400:
        score += 0.2
        reasons.append("informative-length")

    if nearest_distance is not None:
        # Far from everything we know -> likely novel -> worth extracting.
        novelty = min(max(nearest_distance, 0.0), 1.0)
        score += 0.3 * novelty
        reasons.append(f"novelty={novelty:.2f}")

    return GateResult(has_fact_score=min(score, 1.0), reasons=reasons)
