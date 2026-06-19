"""Staleness / implicit-invalidation detection (Helix v2, plan §1.3).

When a fact supersedes another ("we use SQLite" → "we use Postgres"), facts that referenced the
*dropped* subject ("SQLite WAL mode is on") are likely no longer true — even though nothing
explicitly contradicted them. This module flags such dependents as `_stale_suspected` so they can
be down-weighted in recall and surfaced in a review queue.

It is **advisory only** — never auto-deletes (CLAUDE.md: the user owns the memory). Pure stdlib,
$0, deterministic.
"""

from __future__ import annotations

import re
from datetime import datetime

from .models import Memory, Status

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9.+#_-]*")
# Common words that look like entities at a sentence start but carry no subject identity.
_STOP = {
    "the",
    "a",
    "an",
    "we",
    "i",
    "it",
    "this",
    "that",
    "they",
    "our",
    "all",
    "use",
    "uses",
    "used",
    "using",
    "for",
    "to",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "now",
    "no",
    "not",
    "longer",
    "instead",
    "switched",
    "moved",
    "migrated",
    "replaced",
    "deprecated",
    "from",
    "of",
    "in",
    "on",
    "with",
    "prefer",
    "chose",
    "choose",
    "every",
    "always",
    "never",
}


def key_entities(text: str) -> set[str]:
    """Distinctive subject tokens: capitalized words, dotted/techy names, and ALLCAPS terms.

    Lower-cased for comparison. Sentence-initial common words are filtered via a small stop-list.
    """
    out: set[str] = set()
    for tok in _WORD.findall(text):
        low = tok.lower()
        if low in _STOP or len(tok) < 3:
            continue
        is_capitalized = tok[0].isupper()
        is_techy = any(c in tok for c in ".+#_-") or any(c.isdigit() for c in tok)
        is_allcaps = tok.isupper() and len(tok) >= 3
        if is_capitalized or is_techy or is_allcaps:
            out.add(low)
    return out


def flag_stale_dependents(
    store, old: Memory, new_content: str, now: datetime, *, limit: int = 200
) -> list[str]:
    """Mark same-scope active facts that reference an entity dropped by a supersession.

    `dropped` = entities present in the OLD fact but absent from the NEW one. Returns the ids
    flagged. The flagging fact (the new one) and the old fact itself are never flagged.
    """
    dropped = key_entities(old.content) - key_entities(new_content)
    if not dropped:
        return []
    flagged: list[str] = []
    for mem in store.all_memories(scope=old.scope, limit=limit):
        if mem.id == old.id or mem.attributes.get("_hub") or mem.status != Status.ACTIVE:
            continue
        if mem.attributes.get("_stale_suspected"):
            continue
        ents = key_entities(mem.content)
        hit = dropped & ents
        if hit:
            mem.attributes["_stale_suspected"] = True
            mem.attributes["_stale_reason"] = (
                f"references '{sorted(hit)[0]}', superseded by: {new_content[:80]}"
            )
            mem.updated_at = now
            store.upsert_memory(mem)
            store.add_history("stale-suspect", mem.id, {"because": old.id})
            flagged.append(mem.id)
    return flagged
