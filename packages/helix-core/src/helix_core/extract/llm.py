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

_BATCH_PROMPT = """Extract durable memory facts from each numbered note below.

Return JSON: {{"notes": [{{"i": <note number>, "facts": [{{"type": "<type>", "content": "<one concise fact>", "importance": <0..1>}}]}}]}}
Allowed types: identity, preference, project, decision, convention, snippet, entity, fact.
Include a note only if it has durable facts; omit notes that have none.

NOTES:
{notes}
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

    def extract_batch(
        self, texts: list[str], *, scope: str = "global", force: bool = False
    ) -> list[list[CandidateFact]]:
        """Extract from many slices in ONE LLM call (cost lever). Gated + fallback-safe."""
        results: list[list[CandidateFact]] = [[] for _ in texts]
        passing = [
            (i, t.strip())
            for i, t in enumerate(texts)
            if t.strip() and (force or evaluate(t).should_extract(self._cutoff))
        ]
        if not passing:
            return results
        prompt = _BATCH_PROMPT.format(notes="\n".join(f"[{i}] {t}" for i, t in passing))
        try:
            result = self.router.complete(prompt, system=_SYSTEM, json_mode=True)
            per_index = _parse_batch(result.text, scope)
        except Exception:
            for i, t in passing:
                results[i] = self.fallback.extract(t, scope=scope, force=force)
            return results
        for i, t in passing:
            facts = per_index.get(i, [])
            if not facts and force:
                facts = self.fallback.extract(t, scope=scope, force=True)
            results[i] = facts
        return results


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


def _parse_batch(raw: str, scope: str) -> dict[int, list[CandidateFact]]:
    out: dict[int, list[CandidateFact]] = {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return out
    notes = data.get("notes", []) if isinstance(data, dict) else []
    for note in notes if isinstance(notes, list) else []:
        if not isinstance(note, dict):
            continue
        try:
            idx = int(note.get("i"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        out[idx] = _parse(json.dumps({"facts": note.get("facts", [])}), scope)
    return out
