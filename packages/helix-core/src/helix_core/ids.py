"""Identifier helpers.

Memory ids are **human-readable and time-sortable** (ADR-023): `<type>_<slug>_<ts><rand>`.
Human-readable ids improve agent retrieval precision and make the graph inspectable; the
time component keeps them roughly sortable by creation.
"""

from __future__ import annotations

import os
import re
import time

_WORD = re.compile(r"[a-z0-9]+")
# Crockford-ish base32 (no i/l/o/u) for compact, unambiguous suffixes.
_B32 = "0123456789abcdefghjkmnpqrstvwxyz"


def _b32(n: int, width: int) -> str:
    out = []
    for _ in range(width):
        n, r = divmod(n, 32)
        out.append(_B32[r])
    return "".join(reversed(out))


def slug(text: str, max_words: int = 6) -> str:
    words = _WORD.findall(text.lower())
    return "-".join(words[:max_words]) or "mem"


def new_id(kind: str, text: str = "") -> str:
    """A human-readable, time-sortable id: `<kind>_<slug>_<ts8><rand4>`."""
    ts = _b32(int(time.time() * 1000), 8)  # ms timestamp, 40 bits -> 8 chars
    rnd = _b32(int.from_bytes(os.urandom(3), "big"), 4)  # 24 bits -> ~5 chars; keep 4
    body = slug(text) if text else "x"
    return f"{kind[:4]}_{body}_{ts}{rnd}"


def edge_id(from_id: str, relation: str, to_id: str) -> str:
    rnd = _b32(int.from_bytes(os.urandom(3), "big"), 4)
    return f"edge_{relation}_{rnd}"
