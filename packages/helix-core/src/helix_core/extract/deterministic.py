"""DeterministicExtractor — the no-LLM, $0 floor (TSD §6.2, docs/CONSOLIDATION.md).

Splits a redacted slice into candidate statements, runs the heuristic gate on each, and infers
a typed CandidateFact from lexical cues. Lower recall than an LLM, fully local and free, and
always available so $0 mode is first-class.
"""

from __future__ import annotations

import re

from ..gate import evaluate
from ..models import COGNITIVE_OF, CandidateFact, MemoryType

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

# Ordered cue rules: first match wins. (compiled, case-insensitive)
_RULES: list[tuple[MemoryType, re.Pattern[str]]] = [
    (
        MemoryType.DECISION,
        re.compile(
            r"\b(decided|chose|chosen|opted for|going with|will use|we use .+ because|"
            r"decision|picked)\b",
            re.I,
        ),
    ),
    (
        MemoryType.CONVENTION,
        re.compile(
            r"\b(convention|standard|rule|guideline|must|should always|always use|never use|"
            r"style guide|policy)\b",
            re.I,
        ),
    ),
    (
        MemoryType.PREFERENCE,
        re.compile(
            r"\b(prefer|favou?r|i like|i dislike|avoid|rather than|over \w+|don'?t use)\b", re.I
        ),
    ),
    (MemoryType.SNIPPET, re.compile(r"```|\b(snippet|helper|boilerplate|pattern for)\b", re.I)),
    (
        MemoryType.PROJECT,
        re.compile(
            r"\b(project|service|repo|repository|architecture|microservice|the stack|built with|"
            r"runs on)\b",
            re.I,
        ),
    ),
    (
        MemoryType.IDENTITY,
        re.compile(r"\b(i am|i'?m a|my name is|i work as|i'?m the|my role)\b", re.I),
    ),
    (
        MemoryType.ENTITY,
        re.compile(r"\b(owns|owner of|maintains|on the .+ team|reports to)\b", re.I),
    ),
]


def _infer_type(text: str) -> MemoryType:
    for mtype, pat in _RULES:
        if pat.search(text):
            return mtype
    return MemoryType.FACT


class DeterministicExtractor:
    name = "deterministic"

    def __init__(self, cutoff: float = 0.75) -> None:
        self._cutoff = cutoff

    def extract(
        self, text: str, *, scope: str = "global", force: bool = False
    ) -> list[CandidateFact]:
        text = text.strip()
        if not text:
            return []
        statements = [s.strip() for s in _SENT_SPLIT.split(text) if len(s.split()) >= 3]
        if not statements:
            statements = [text] if force else []

        facts: list[CandidateFact] = []
        for stmt in statements:
            gate = evaluate(stmt)
            if not force and not gate.should_extract(self._cutoff):
                continue
            mtype = _infer_type(stmt)
            importance = _importance(mtype, gate.has_fact_score)
            facts.append(
                CandidateFact(
                    type=mtype,
                    content=stmt,
                    scope=scope,
                    cognitive=COGNITIVE_OF[mtype],
                    importance=importance,
                    confidence=0.6 if force else 0.5 + 0.3 * gate.has_fact_score,
                )
            )
        # When forced (e.g. `helix add`) but everything was filtered, keep the whole slice.
        if force and not facts:
            mtype = _infer_type(text)
            facts.append(
                CandidateFact(
                    type=mtype,
                    content=text,
                    scope=scope,
                    cognitive=COGNITIVE_OF[mtype],
                    importance=_importance(mtype, 0.5),
                    confidence=0.6,
                )
            )
        return facts


def _importance(mtype: MemoryType, gate_score: float) -> float:
    base = 0.4 + 0.4 * gate_score
    boost = {
        MemoryType.DECISION: 0.2,
        MemoryType.CONVENTION: 0.15,
        MemoryType.IDENTITY: 0.15,
        MemoryType.PROJECT: 0.1,
    }.get(mtype, 0.0)
    return round(min(base + boost, 1.0), 3)
