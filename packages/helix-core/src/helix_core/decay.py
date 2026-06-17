"""Decay & reinforcement (ADR-014, docs/CONSOLIDATION.md).

Salience is computed at *read time* — no cron needed:

    salience = importance · exp(−λ · Δt_last_access),   λ = ln2 / half_life

Half-lives are per cognitive shape: episodic memories fade fast, procedural slowly, semantic
facts effectively persist until contradicted. Reinforcement (a successful recall) resets
Δt and grows the effective half-life SM-2-style.
"""

from __future__ import annotations

import math
from datetime import datetime

from .models import Cognitive, Memory, utcnow

# Half-life in days per cognitive shape (semantic/entity ~ effectively non-decaying).
HALF_LIFE_DAYS: dict[Cognitive, float] = {
    Cognitive.EPISODIC: 7.0,
    Cognitive.PROCEDURAL: 90.0,
    Cognitive.SEMANTIC: 3650.0,
    Cognitive.ENTITY: 3650.0,
}

# SM-2-style easiness floor; reinforcement multiplies effective half-life by this each recall.
EF_MIN = 1.3
EF_STEP = 1.15  # gentle growth so frequently-used memories become near-permanent


def salience(mem: Memory, now: datetime | None = None) -> float:
    """Current importance of a memory after time decay. In [0, importance]."""
    now = now or utcnow()
    half_life = HALF_LIFE_DAYS.get(mem.cognitive, 30.0)
    # Reinforcement count is stashed in attributes; grows the half-life.
    reinforced = float(mem.attributes.get("_reinforced", 0))
    eff_half_life = half_life * (EF_STEP**reinforced)
    dt_days = max((now - mem.last_seen_at).total_seconds() / 86400.0, 0.0)
    lam = math.log(2) / eff_half_life
    return mem.importance * math.exp(-lam * dt_days)


def recency(mem: Memory, now: datetime | None = None, half_life_days: float = 30.0) -> float:
    """A pure recency signal in (0, 1], independent of importance."""
    now = now or utcnow()
    dt_days = max((now - mem.last_seen_at).total_seconds() / 86400.0, 0.0)
    lam = math.log(2) / half_life_days
    return math.exp(-lam * dt_days)


def reinforce(mem: Memory, now: datetime | None = None) -> None:
    """Record a successful recall: reset Δt and grow the effective half-life (in place)."""
    now = now or utcnow()
    mem.last_seen_at = now
    mem.attributes["_reinforced"] = float(mem.attributes.get("_reinforced", 0)) + 1
