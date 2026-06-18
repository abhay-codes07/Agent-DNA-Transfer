"""LLMExtractor — structured fact extraction via the router (TSD §6.2, Phase 3).

Used only when an LLM is configured AND the heuristic gate thinks a slice is worth it (the cost
lever). Emits compact JSON. ALWAYS degrades to the deterministic extractor on any failure,
budget exhaustion, or unparsable output — so $0/offline stays first-class (CLAUDE.md rule 3).
"""

from __future__ import annotations

import json

from ..gate import evaluate
from ..models import COGNITIVE_OF, CandidateFact, MemoryType
from .deterministic import DeterministicExtractor

_SYSTEM = (
    "You extract durable, reusable facts about a software developer and their projects from a "
    "snippet of conversation or notes. Return only facts worth remembering long-term "
    "(preferences, decisions, conventions, project/architecture facts, identities, reusable "
    "snippets) — ignore small talk and transient chatter."
)

_PROMPT = """Extract durable memory facts from the text below.

Return JSON of the form: {{"facts": [{{"type": "<type>", "content": "<one concise fact>", "importance": <0..1>}}]}}
Allowed types: identity, preference, project, decision, convention, snippet, entity, fact.
If there is nothing durable to remember, return {{"facts": []}}.

TEXT:
{text}
"""


class LLMExtractor:
    name = "llm"

    def __init__(
        self, router, fallback: DeterministicExtractor | None = None, cutoff: float = 0.75
    ) -> None:
        self.router = router
        self.fallback = fallback or DeterministicExtractor(cutoff)
        self._cutoff = cutoff

    def extract(
        self, text: str, *, scope: str = "global", force: bool = False
    ) -> list[CandidateFact]:
        text = text.strip()
        if not text:
            return []
        # Cost lever: don't even call the model unless the gate (or force) says it's worth it.
        if not force and not evaluate(text).should_extract(self._cutoff):
            return []
        try:
            result = self.router.complete(_PROMPT.format(text=text), system=_SYSTEM, json_mode=True)
        except Exception:
            return self.fallback.extract(text, scope=scope, force=force)

        facts = _parse(result.text, scope)
        if not facts and force:
            return self.fallback.extract(text, scope=scope, force=True)
        return facts


def _parse(raw: str, scope: str) -> list[CandidateFact]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data.get("facts", []) if isinstance(data, dict) else data
    out: list[CandidateFact] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        try:
            mtype = MemoryType(str(item.get("type", "fact")).lower())
        except ValueError:
            mtype = MemoryType.FACT
        try:
            importance = float(item.get("importance", 0.6))
        except (TypeError, ValueError):
            importance = 0.6
        out.append(
            CandidateFact(
                type=mtype,
                content=content,
                scope=scope,
                cognitive=COGNITIVE_OF[mtype],
                importance=min(max(importance, 0.0), 1.0),
                confidence=0.7,
            )
        )
    return out
