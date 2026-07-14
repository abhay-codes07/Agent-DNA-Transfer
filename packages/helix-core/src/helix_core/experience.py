"""Experience & credit assignment (v3 plan §1.1/§1.2).

The v3 headline: memory *compounds*. When recalled facts contribute to a task that succeeds or
fails, each earns a reliability signal, and reliability gently biases future ranking so proven
facts float up and repeatedly-unhelpful ones sink.

Design constraints (CLAUDE.md): fully local, deterministic, $0 — this is Laplace-smoothed
arithmetic (Memory-R2-lite), **not** reinforcement learning. RL/auto-tuning stays opt-in cloud
(v2 plan §1.7). Nothing here ever deletes a fact; the negative signal only routes to the review
queue.
"""

from __future__ import annotations

from .models import Memory

# Reliability is a Laplace-smoothed win rate over recorded outcomes; a fact with no outcomes
# sits at the neutral 0.5 so a fresh strand's ranking is exactly unchanged.
_PRIOR_WINS = 1.0
_PRIOR_USES = 2.0

# Experience multiplier bounds — deliberately gentle so a single outcome can't swing ranking.
# reliability 0.5 -> 1.0 (neutral); 1.0 -> 1.0 + SPAN/2; 0.0 -> 1.0 - SPAN/2.
_SPAN = 0.5


def reliability(mem: Memory) -> float:
    """A fact's earned reliability in [0, 1] — Laplace-smoothed win rate. Neutral 0.5 with no data."""
    wins = float(mem.attributes.get("_wins", 0.0))
    uses = float(mem.attributes.get("_uses", 0.0))
    return (wins + _PRIOR_WINS) / (uses + _PRIOR_USES)


def experience_factor(mem: Memory) -> float:
    """Bounded, neutral-at-baseline ranking multiplier from reliability.

    Centered on 1.0 at reliability 0.5, so a strand with no recorded outcomes ranks identically
    to before experience-weighting existed.
    """
    return 1.0 + _SPAN * (reliability(mem) - 0.5)


def record_use(mem: Memory, success: bool, *, weight: float = 1.0) -> None:
    """Credit or debit a fact for a task outcome (in place). Grows `_uses`, and `_wins` on success."""
    mem.attributes["_uses"] = float(mem.attributes.get("_uses", 0.0)) + weight
    if success:
        mem.attributes["_wins"] = float(mem.attributes.get("_wins", 0.0)) + weight
