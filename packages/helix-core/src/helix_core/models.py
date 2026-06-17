"""Core data model for Helix memory.

Mirrors docs/MEMORY_MODEL.md. Every stored fact carries source, created_at, confidence, and
type — downstream features (audit, decay, merge) depend on it (see CLAUDE.md conventions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryType(str, Enum):
    """Typed nodes in the memory graph. Coding-native types are first-class."""

    IDENTITY = "identity"
    PREFERENCE = "preference"
    PROJECT = "project"
    DECISION = "decision"
    ENTITY = "entity"
    CONVENTION = "convention"
    SNIPPET = "snippet"
    FACT = "fact"


class Status(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"
    SUPERSEDED = "superseded"


# Scope is "global" or "project:<id>".
Scope = str
GLOBAL: Scope = "global"


@dataclass(slots=True)
class Provenance:
    """Why Helix believes a fact: the slice, extractor, and model that produced it."""

    agent: str | None = None  # e.g. "claude-code", "cursor"
    ref: str | None = None  # opaque pointer to the source slice
    extractor: str | None = None  # "deterministic" | "llm:gemini-2.0-flash" | ...
    ingested_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class Memory:
    """One typed fact in the graph. See docs/MEMORY_MODEL.md §3."""

    id: str  # UUIDv7 (time-sortable)
    type: MemoryType
    content: str  # distilled, human-readable fact (never a raw transcript)
    scope: Scope = GLOBAL
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5  # [0..1] — how sure we are it's true/durable
    salience: float = 0.5  # [0..1] — importance; decays unless reinforced
    status: Status = Status.ACTIVE
    provenance: list[Provenance] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_seen_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class Edge:
    """A typed, weighted relation between two memories. See docs/MEMORY_MODEL.md §4."""

    id: str
    from_id: str
    to_id: str
    relation: str  # e.g. "has_decision", "depends_on", "supersedes", "contradicts"
    weight: float = 1.0
    provenance: Provenance | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass(slots=True)
class CandidateFact:
    """Output of extraction, before consolidation decides ADD/UPDATE/DELETE/NOOP."""

    type: MemoryType
    content: str
    scope: Scope = GLOBAL
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5


@dataclass(slots=True)
class Hit:
    """A retrieval result with the score used to rank it."""

    memory: Memory
    score: float
    similarity: float = 0.0
