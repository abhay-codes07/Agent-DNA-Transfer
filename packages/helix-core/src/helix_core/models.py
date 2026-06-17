"""Core data model for Helix memory.

Mirrors docs/MEMORY_MODEL.md (v2): typed, bi-temporal, provenance-tagged. Every stored fact
carries source, time, confidence, importance, and type — downstream features (audit, decay,
merge) depend on it (see CLAUDE.md conventions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryType(str, Enum):
    """Coding-native node types. Each maps onto a cognitive shape (see Cognitive)."""

    IDENTITY = "identity"
    PREFERENCE = "preference"
    PROJECT = "project"
    DECISION = "decision"
    ENTITY = "entity"
    CONVENTION = "convention"
    SNIPPET = "snippet"
    EPISODE = "episode"
    FACT = "fact"


class Cognitive(str, Enum):
    """The cognitive memory shape (docs/MEMORY_MODEL.md §2)."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    ENTITY = "entity"


# Default cognitive shape per node type.
COGNITIVE_OF: dict[MemoryType, Cognitive] = {
    MemoryType.IDENTITY: Cognitive.SEMANTIC,
    MemoryType.PREFERENCE: Cognitive.SEMANTIC,
    MemoryType.PROJECT: Cognitive.SEMANTIC,
    MemoryType.DECISION: Cognitive.SEMANTIC,
    MemoryType.FACT: Cognitive.SEMANTIC,
    MemoryType.CONVENTION: Cognitive.PROCEDURAL,
    MemoryType.SNIPPET: Cognitive.PROCEDURAL,
    MemoryType.EPISODE: Cognitive.EPISODIC,
    MemoryType.ENTITY: Cognitive.ENTITY,
}


class Status(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"
    SUPERSEDED = "superseded"


class Origin(str, Enum):
    """Trust origin of a memory — drives anti-poisoning guards (ADR-029)."""

    USER_ASSERTED = "user-asserted"
    AGENT_INGESTED = "agent-ingested"


# Scope is "global" or "project:<id>".
Scope = str
GLOBAL: Scope = "global"


@dataclass(slots=True)
class Provenance:
    """Why Helix believes a fact: the slice, extractor, model, and trust origin."""

    agent: str | None = None  # e.g. "claude-code", "cursor", "cli"
    ref: str | None = None  # opaque pointer to the source slice
    extractor: str | None = None  # "deterministic" | "llm:gemini-2.0-flash" | ...
    origin: Origin = Origin.USER_ASSERTED
    ingested_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class Memory:
    """One typed fact in the graph. See docs/MEMORY_MODEL.md §4."""

    id: str  # human-readable, time-sortable (see ids.py)
    type: MemoryType
    content: str  # distilled, human-readable fact (never a raw transcript)
    scope: Scope = GLOBAL
    cognitive: Cognitive = Cognitive.SEMANTIC
    attributes: dict[str, Any] = field(default_factory=dict)

    # retrieval signals
    importance: float = 0.5  # [0..1] rated at write time; input to salience (decays)
    confidence: float = 0.5  # [0..1] how sure we are it's true/durable

    # lifecycle
    status: Status = Status.ACTIVE
    provenance: list[Provenance] = field(default_factory=list)

    # bi-temporal (ADR-013)
    valid_from: datetime = field(default_factory=utcnow)  # when true in the world
    valid_to: datetime | None = None  # None = currently true; set when superseded
    recorded_at: datetime = field(default_factory=utcnow)  # transaction-time

    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    last_seen_at: datetime = field(default_factory=utcnow)  # reinforcement signal


@dataclass(slots=True)
class Edge:
    """A typed, weighted relation between two memories. See docs/MEMORY_MODEL.md §5."""

    id: str
    from_id: str
    to_id: str
    relation: str  # e.g. "has_decision", "depends_on", "supersedes", "contradicts"
    weight: float = 1.0
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class CandidateFact:
    """Output of extraction, before consolidation decides ADD/UPDATE/DELETE/NOOP."""

    type: MemoryType
    content: str
    scope: Scope = GLOBAL
    cognitive: Cognitive = Cognitive.SEMANTIC
    attributes: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    confidence: float = 0.5


@dataclass(slots=True)
class Hit:
    """A retrieval result with the score used to rank it."""

    memory: Memory
    score: float
    similarity: float = 0.0
    salience: float = 0.0
