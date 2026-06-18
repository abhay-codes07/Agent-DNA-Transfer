"""LLM response cache (docs/COST_OPTIMIZATION.md §4).

Keyed by a hash of (model, system, prompt) so identical extraction/consolidation work is never
paid for twice — across runs. Also tracks monthly token usage for the budget guardrail. A tiny
SQLite file next to the strand; safe to delete.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def cache_key(model: str, prompt: str, system: str | None) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update((system or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


class LLMCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(
            "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, value TEXT);"
            "CREATE TABLE IF NOT EXISTS llm_usage (month TEXT PRIMARY KEY, tokens INTEGER);"
        )
        self.conn.commit()

    def get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM llm_cache WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO llm_cache(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def tokens_this_month(self, month: str) -> int:
        row = self.conn.execute("SELECT tokens FROM llm_usage WHERE month=?", (month,)).fetchone()
        return int(row[0]) if row else 0

    def add_tokens(self, month: str, tokens: int) -> None:
        self.conn.execute(
            "INSERT INTO llm_usage(month,tokens) VALUES(?,?) "
            "ON CONFLICT(month) DO UPDATE SET tokens=tokens+excluded.tokens",
            (month, tokens),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
