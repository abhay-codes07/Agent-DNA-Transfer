"""SqliteStore — the default strand: one SQLite file holding vectors + graph + metadata.

Implements both VectorStore and GraphStore over a single transactional database (ADR-005,
ADR-018). Vectors are stored as float32 blobs and searched brute-force with cosine (fast
enough at Phase-1 scale; sqlite-vec is an optional accelerator later). Keyword search uses
FTS5 when available, else a LIKE fallback. Writes are transactional; a crash never yields a
partial strand.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from ..embed.base import cosine, from_bytes, to_bytes
from ..models import (
    Cognitive,
    Edge,
    Memory,
    MemoryType,
    Origin,
    Provenance,
    Status,
    utcnow,
)

ACTIVE = (Status.ACTIVE.value,)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    cognitive   TEXT NOT NULL,
    content     TEXT NOT NULL,
    scope       TEXT NOT NULL,
    attributes  TEXT NOT NULL DEFAULT '{}',
    importance  REAL NOT NULL DEFAULT 0.5,
    confidence  REAL NOT NULL DEFAULT 0.5,
    status      TEXT NOT NULL DEFAULT 'active',
    provenance  TEXT NOT NULL DEFAULT '[]',
    valid_from  TEXT,
    valid_to    TEXT,
    recorded_at TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    last_seen_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_scope_status ON memories(scope, status);

CREATE TABLE IF NOT EXISTS vectors (
    id   TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    dim  INTEGER NOT NULL,
    data BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id        TEXT PRIMARY KEY,
    from_id   TEXT NOT NULL,
    to_id     TEXT NOT NULL,
    relation  TEXT NOT NULL,
    weight    REAL NOT NULL DEFAULT 1.0,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_edge_from ON edges(from_id);
CREATE INDEX IF NOT EXISTS idx_edge_to ON edges(to_id);

CREATE TABLE IF NOT EXISTS history (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT,
    op         TEXT,
    memory_id  TEXT,
    detail     TEXT
);

CREATE TABLE IF NOT EXISTS tombstones (
    fp        TEXT PRIMARY KEY,   -- content fingerprint of an erased fact
    erased_at TEXT
);
"""


def content_fingerprint(mem: Memory) -> str:
    """Stable hash of a fact's identity (type + normalized content) for tombstone matching."""
    import hashlib

    key = f"{mem.type.value}|{mem.content.strip().lower()}"
    return hashlib.blake2b(key.encode("utf-8"), digest_size=16).hexdigest()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class SqliteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so the local dashboard daemon can serve from its own thread;
        # access is serialized (single-threaded HTTPServer / the engine's tx()).
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        self.fts = self._init_fts()
        self.conn.commit()

    # --- FTS (optional; graceful fallback) ---
    def _init_fts(self) -> bool:
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts "
                "USING fts5(content, id UNINDEXED, scope UNINDEXED)"
            )
            return True
        except sqlite3.OperationalError:
            return False  # FTS5 not compiled in -> LIKE fallback

    # --- transactions ---
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- meta / embedding space ---
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def ensure_embedding_space(self, model: str, dim: int) -> None:
        """Pin the embedding space on first write; refuse a silent mismatch (ADR-006)."""
        cur_model = self.get_meta("embedding_model")
        if cur_model is None:
            self.set_meta("embedding_model", model)
            self.set_meta("embedding_dim", str(dim))
            self.set_meta("schema_version", "1")
            return
        if cur_model != model or int(self.get_meta("embedding_dim") or 0) != dim:
            raise ValueError(
                f"strand uses embedding space {cur_model}/{self.get_meta('embedding_dim')}, "
                f"not {model}/{dim}; re-embed required (not yet automated in Phase 1)."
            )

    # --- writes ---
    def upsert_memory(self, mem: Memory, embedding: list[float] | None = None) -> None:
        self.conn.execute(
            """INSERT INTO memories
               (id,type,cognitive,content,scope,attributes,importance,confidence,status,
                provenance,valid_from,valid_to,recorded_at,created_at,updated_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 type=excluded.type, cognitive=excluded.cognitive, content=excluded.content,
                 scope=excluded.scope, attributes=excluded.attributes,
                 importance=excluded.importance, confidence=excluded.confidence,
                 status=excluded.status, provenance=excluded.provenance,
                 valid_from=excluded.valid_from, valid_to=excluded.valid_to,
                 recorded_at=excluded.recorded_at, updated_at=excluded.updated_at,
                 last_seen_at=excluded.last_seen_at""",
            (
                mem.id,
                mem.type.value,
                mem.cognitive.value,
                mem.content,
                mem.scope,
                json.dumps(_clean_attrs(mem.attributes)),
                mem.importance,
                mem.confidence,
                mem.status.value,
                json.dumps([_prov_to_dict(p) for p in mem.provenance]),
                _iso(mem.valid_from),
                _iso(mem.valid_to),
                _iso(mem.recorded_at),
                _iso(mem.created_at),
                _iso(mem.updated_at),
                _iso(mem.last_seen_at),
            ),
        )
        if embedding is not None:
            self.conn.execute(
                "INSERT INTO vectors(id,dim,data) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET dim=excluded.dim, data=excluded.data",
                (mem.id, len(embedding), to_bytes(embedding)),
            )
        self._sync_fts(mem)

    def _sync_fts(self, mem: Memory) -> None:
        if not self.fts:
            return
        self.conn.execute("DELETE FROM memories_fts WHERE id=?", (mem.id,))
        # Hub/connector nodes bridge the graph but are not retrievable content.
        if mem.status == Status.ACTIVE and not mem.attributes.get("_hub"):
            self.conn.execute(
                "INSERT INTO memories_fts(content,id,scope) VALUES(?,?,?)",
                (mem.content, mem.id, mem.scope),
            )

    def set_status(self, memory_id: str, status: Status) -> None:
        mem = self.get_memory(memory_id)
        if not mem:
            return
        mem.status = status
        mem.updated_at = mem.updated_at
        self.upsert_memory(mem)

    def add_edge(self, edge: Edge) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO edges(id,from_id,to_id,relation,weight,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (edge.id, edge.from_id, edge.to_id, edge.relation, edge.weight, _iso(edge.created_at)),
        )

    def delete_memory(self, memory_id: str, *, tombstone: bool = True) -> bool:
        """Hard-delete a memory and everything tied to it: vector, FTS row, and any edges.

        Unlike `forget` (soft, recoverable), this is irreversible erasure (GDPR Art. 17). When
        `tombstone=True`, a content fingerprint is recorded so a later merge can't resurrect it.
        """
        mem = self.get_memory(memory_id)
        if mem is None:
            return False
        if tombstone:
            self.add_tombstone(content_fingerprint(mem))
        self.conn.execute("DELETE FROM vectors WHERE id=?", (memory_id,))
        if self.fts:
            self.conn.execute("DELETE FROM memories_fts WHERE id=?", (memory_id,))
        self.conn.execute("DELETE FROM edges WHERE from_id=? OR to_id=?", (memory_id, memory_id))
        self.conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        return True

    def add_tombstone(self, fp: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO tombstones(fp, erased_at) VALUES(?,?)", (fp, _iso(utcnow()))
        )

    def is_tombstoned(self, fp: str) -> bool:
        return (
            self.conn.execute("SELECT 1 FROM tombstones WHERE fp=?", (fp,)).fetchone() is not None
        )

    def tombstone_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM tombstones").fetchone()[0])

    def add_history(self, op: str, memory_id: str, detail: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO history(ts,op,memory_id,detail) VALUES(?,?,?,?)",
            (_iso(utcnow()), op, memory_id, json.dumps(detail or {})),
        )

    # --- reads ---
    def get_memory(self, memory_id: str) -> Memory | None:
        row = self.conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return _row_to_memory(row) if row else None

    def all_memories(
        self, scope: str | None = None, statuses: tuple[str, ...] = ACTIVE, limit: int = 1000
    ) -> list[Memory]:
        q = f"SELECT * FROM memories WHERE status IN ({_ph(statuses)})"
        args: list = list(statuses)
        if scope:
            q += " AND scope=?"
            args.append(scope)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [_row_to_memory(r) for r in self.conn.execute(q, args).fetchall()]

    def count(self, statuses: tuple[str, ...] = ACTIVE) -> int:
        row = self.conn.execute(
            f"SELECT COUNT(*) c FROM memories WHERE status IN ({_ph(statuses)})", list(statuses)
        ).fetchone()
        return int(row["c"])

    def vector_search(
        self, query_vec: list[float], k: int, scope: str | None = None
    ) -> list[tuple[str, float]]:
        q = (
            "SELECT v.id AS id, v.data AS data FROM vectors v "
            "JOIN memories m ON m.id=v.id WHERE m.status='active'"
        )
        args: list = []
        if scope:
            q += " AND (m.scope=? OR m.scope='global')"
            args.append(scope)
        scored: list[tuple[str, float]] = []
        for row in self.conn.execute(q, args):
            sim = cosine(query_vec, from_bytes(row["data"]))
            scored.append((row["id"], sim))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def keyword_search(
        self, query: str, k: int, scope: str | None = None
    ) -> list[tuple[str, float]]:
        if self.fts:
            match = _fts_query(query)
            if not match:
                return []
            q = "SELECT id, rank FROM memories_fts WHERE memories_fts MATCH ?"
            args: list = [match]
            if scope:
                q += " AND (scope=? OR scope='global')"
                args.append(scope)
            q += " ORDER BY rank LIMIT ?"
            args.append(k)
            try:
                rows = self.conn.execute(q, args).fetchall()
            except sqlite3.OperationalError:
                return self._like_search(query, k, scope)
            return [(r["id"], 1.0 / (i + 1)) for i, r in enumerate(rows)]
        return self._like_search(query, k, scope)

    def _like_search(self, query: str, k: int, scope: str | None) -> list[tuple[str, float]]:
        import re

        terms = re.findall(r"[A-Za-z0-9]+", query.lower())[:8]
        if not terms:
            return []
        clause = " OR ".join("lower(content) LIKE ?" for _ in terms)
        q = f"SELECT id, content FROM memories WHERE status='active' AND ({clause})"
        args: list = [f"%{t}%" for t in terms]
        if scope:
            q += " AND (scope=? OR scope='global')"
            args.append(scope)
        rows = self.conn.execute(q, args).fetchall()
        # rank by number of distinct term hits
        out = []
        for r in rows:
            c = r["content"].lower()
            out.append((r["id"], float(sum(1 for t in terms if t in c))))
        out.sort(key=lambda t: t[1], reverse=True)
        return out[:k]

    def neighbors(self, memory_id: str, depth: int = 1) -> list[Memory]:
        seen = {memory_id}
        frontier = {memory_id}
        for _ in range(depth):
            nxt: set[str] = set()
            for nid in frontier:
                for r in self.conn.execute(
                    "SELECT to_id AS o FROM edges WHERE from_id=? "
                    "UNION SELECT from_id AS o FROM edges WHERE to_id=?",
                    (nid, nid),
                ):
                    if r["o"] not in seen:
                        nxt.add(r["o"])
                        seen.add(r["o"])
            frontier = nxt
        ids = seen - {memory_id}
        return [m for m in (self.get_memory(i) for i in ids) if m and m.status == Status.ACTIVE]

    # --- strand transfer support (Phase 4) ---
    def checkpoint(self) -> None:
        self.conn.commit()
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass

    def backup_to(self, dest: str | Path) -> None:
        """Write a clean, standalone snapshot of this strand to `dest` (online backup API)."""
        self.checkpoint()
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()

    def history(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT seq, ts, op, memory_id, detail FROM history ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "seq": r["seq"],
                "ts": r["ts"],
                "op": r["op"],
                "memory_id": r["memory_id"],
                "detail": json.loads(r["detail"] or "{}"),
            }
            for r in rows
        ]

    def history_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM history").fetchone()[0])

    def get_version(self) -> int:
        return int(self.get_meta("version") or 0)

    def bump_version(self) -> int:
        v = self.get_version() + 1
        self.set_meta("version", str(v))
        return v

    def all_edges(self) -> list[Edge]:
        rows = self.conn.execute(
            "SELECT id,from_id,to_id,relation,weight,created_at FROM edges"
        ).fetchall()
        return [
            Edge(
                id=r["id"],
                from_id=r["from_id"],
                to_id=r["to_id"],
                relation=r["relation"],
                weight=r["weight"],
                created_at=_dt(r["created_at"]) or utcnow(),
            )
            for r in rows
        ]

    def edge_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0])

    def edges_by_relation(self, relation: str) -> list[Edge]:
        rows = self.conn.execute(
            "SELECT id,from_id,to_id,relation,weight,created_at FROM edges WHERE relation=?",
            (relation,),
        ).fetchall()
        return [
            Edge(
                id=r["id"],
                from_id=r["from_id"],
                to_id=r["to_id"],
                relation=r["relation"],
                weight=r["weight"],
                created_at=_dt(r["created_at"]) or utcnow(),
            )
            for r in rows
        ]

    def reembed(self, embedder) -> int:
        """Recompute every stored vector with `embedder` and re-pin the embedding space.

        Used on import when a strand's embedding space differs from the local one (ADR-006);
        avoids mixing vector spaces. Hub nodes have no vector and are left untouched.
        """
        rows = self.conn.execute(
            "SELECT v.id AS id, m.content AS content FROM vectors v JOIN memories m ON m.id=v.id"
        ).fetchall()
        if rows:
            vecs = embedder.embed([r["content"] for r in rows])
            for r, vec in zip(rows, vecs):
                self.conn.execute(
                    "UPDATE vectors SET dim=?, data=? WHERE id=?",
                    (len(vec), to_bytes(vec), r["id"]),
                )
        self.set_meta("embedding_provider", "local")
        self.set_meta("embedding_model", embedder.model)
        self.set_meta("embedding_dim", str(embedder.dim))
        self.conn.commit()
        return len(rows)

    def fingerprints(self) -> list[str]:
        """Stable per-row content strings for the integrity Merkle tree (active rows)."""
        out: list[str] = []
        for r in self.conn.execute(
            "SELECT id,type,content,scope,status,valid_from,valid_to FROM memories"
        ):
            out.append(
                "M|"
                + "|".join(
                    str(r[c])
                    for c in ("id", "type", "content", "scope", "status", "valid_from", "valid_to")
                )
            )
        for r in self.conn.execute("SELECT id,from_id,to_id,relation FROM edges"):
            out.append("E|" + "|".join(str(r[c]) for c in ("id", "from_id", "to_id", "relation")))
        return out

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


# --- (de)serialization helpers ---


def _ph(seq) -> str:
    return ",".join("?" for _ in seq)


def _clean_attrs(attrs: dict) -> dict:
    return attrs  # attributes are already JSON-safe (incl. our private _reinforced counter)


def _prov_to_dict(p: Provenance) -> dict:
    return {
        "agent": p.agent,
        "ref": p.ref,
        "extractor": p.extractor,
        "origin": p.origin.value,
        "ingested_at": _iso(p.ingested_at),
    }


def _dict_to_prov(d: dict) -> Provenance:
    return Provenance(
        agent=d.get("agent"),
        ref=d.get("ref"),
        extractor=d.get("extractor"),
        origin=Origin(d.get("origin", Origin.USER_ASSERTED.value)),
        ingested_at=_dt(d.get("ingested_at")) or Provenance().ingested_at,
    )


def _row_to_memory(row: sqlite3.Row) -> Memory:
    return Memory(
        id=row["id"],
        type=MemoryType(row["type"]),
        content=row["content"],
        scope=row["scope"],
        cognitive=Cognitive(row["cognitive"]),
        attributes=json.loads(row["attributes"] or "{}"),
        importance=row["importance"],
        confidence=row["confidence"],
        status=Status(row["status"]),
        provenance=[_dict_to_prov(d) for d in json.loads(row["provenance"] or "[]")],
        valid_from=_dt(row["valid_from"]) or utcnow(),
        valid_to=_dt(row["valid_to"]),  # genuinely optional (None = still valid)
        recorded_at=_dt(row["recorded_at"]) or utcnow(),
        created_at=_dt(row["created_at"]) or utcnow(),
        updated_at=_dt(row["updated_at"]) or utcnow(),
        last_seen_at=_dt(row["last_seen_at"]) or utcnow(),
    )


def _fts_query(query: str) -> str:
    import re

    terms = re.findall(r"[A-Za-z0-9]+", query.lower())
    return " OR ".join(terms[:12])
