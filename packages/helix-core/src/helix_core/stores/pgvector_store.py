"""PgVectorStore — EXPERIMENTAL Postgres + pgvector backend (ADR-010/018).

For large, shared/team strands that outgrow a single SQLite file. Implements the same `Store`
surface as `SqliteStore` using psycopg (v3) + the pgvector extension. Requires `psycopg` and
`pgvector`, and a Postgres with `CREATE EXTENSION vector`.

Status: **experimental — not exercised in CI** (no Postgres in the test env). The SQL mirrors
`SqliteStore`; wire it to a real Postgres (set `HELIX_TEST_PG_DSN`) to run the integration test.
The portable single-file `.dna` flow stays on SQLite; this backend targets server-side scale.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime

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


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class PgVectorStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from pgvector.psycopg import register_vector
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "PgVectorStore needs psycopg + pgvector — `pip install psycopg pgvector` and a "
                "Postgres with `CREATE EXTENSION vector`."
            ) from exc
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=psycopg.rows.dict_row)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, type TEXT, cognitive TEXT, content TEXT, scope TEXT,
                attributes JSONB DEFAULT '{}', importance REAL DEFAULT 0.5,
                confidence REAL DEFAULT 0.5, status TEXT DEFAULT 'active',
                provenance JSONB DEFAULT '[]', valid_from TEXT, valid_to TEXT,
                recorded_at TEXT, created_at TEXT, updated_at TEXT, last_seen_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_mem_scope_status ON memories(scope, status);
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY, from_id TEXT, to_id TEXT, relation TEXT,
                weight REAL DEFAULT 1.0, created_at TEXT);
            CREATE TABLE IF NOT EXISTS history (
                seq BIGSERIAL PRIMARY KEY, ts TEXT, op TEXT, memory_id TEXT, detail JSONB);
            """
        )

    # --- vectors table is created lazily once the embedding dim is known ---
    def _ensure_vectors_table(self, dim: int) -> None:
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY "
            f"REFERENCES memories(id) ON DELETE CASCADE, embedding vector({dim}))"
        )

    @contextmanager
    def tx(self):
        with self.conn.transaction():
            yield self.conn

    # --- meta / embedding space ---
    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(%s,%s) "
            "ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=%s", (key,)).fetchone()
        return row["value"] if row else None

    def ensure_embedding_space(self, model: str, dim: int) -> None:
        cur = self.get_meta("embedding_model")
        if cur is None:
            self.set_meta("embedding_model", model)
            self.set_meta("embedding_dim", str(dim))
            self.set_meta("schema_version", "1")
            self._ensure_vectors_table(dim)
            return
        if cur != model or int(self.get_meta("embedding_dim") or 0) != dim:
            raise ValueError(f"strand uses {cur}; re-embed required for {model}")

    # --- writes ---
    def upsert_memory(self, mem: Memory, embedding: list[float] | None = None) -> None:
        self.conn.execute(
            """INSERT INTO memories
               (id,type,cognitive,content,scope,attributes,importance,confidence,status,
                provenance,valid_from,valid_to,recorded_at,created_at,updated_at,last_seen_at)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(id) DO UPDATE SET
                 type=EXCLUDED.type, cognitive=EXCLUDED.cognitive, content=EXCLUDED.content,
                 scope=EXCLUDED.scope, attributes=EXCLUDED.attributes,
                 importance=EXCLUDED.importance, confidence=EXCLUDED.confidence,
                 status=EXCLUDED.status, provenance=EXCLUDED.provenance,
                 valid_from=EXCLUDED.valid_from, valid_to=EXCLUDED.valid_to,
                 recorded_at=EXCLUDED.recorded_at, updated_at=EXCLUDED.updated_at,
                 last_seen_at=EXCLUDED.last_seen_at""",
            (
                mem.id,
                mem.type.value,
                mem.cognitive.value,
                mem.content,
                mem.scope,
                json.dumps(mem.attributes),
                mem.importance,
                mem.confidence,
                mem.status.value,
                json.dumps([_prov(p) for p in mem.provenance]),
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
                "INSERT INTO vectors(id,embedding) VALUES(%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET embedding=EXCLUDED.embedding",
                (mem.id, embedding),
            )

    def add_edge(self, edge: Edge) -> None:
        self.conn.execute(
            "INSERT INTO edges(id,from_id,to_id,relation,weight,created_at) "
            "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING",
            (edge.id, edge.from_id, edge.to_id, edge.relation, edge.weight, _iso(edge.created_at)),
        )

    def add_history(self, op: str, memory_id: str, detail: dict | None = None) -> None:
        self.conn.execute(
            "INSERT INTO history(ts,op,memory_id,detail) VALUES(%s,%s,%s,%s)",
            (_iso(utcnow()), op, memory_id, json.dumps(detail or {})),
        )

    # --- reads ---
    def get_memory(self, memory_id: str) -> Memory | None:
        row = self.conn.execute("SELECT * FROM memories WHERE id=%s", (memory_id,)).fetchone()
        return _row_to_memory(row) if row else None

    def all_memories(self, scope=None, statuses=ACTIVE, limit: int = 1000) -> list[Memory]:
        q = "SELECT * FROM memories WHERE status = ANY(%s)"
        args: list = [list(statuses)]
        if scope:
            q += " AND scope=%s"
            args.append(scope)
        q += " ORDER BY created_at DESC LIMIT %s"
        args.append(limit)
        return [_row_to_memory(r) for r in self.conn.execute(q, args).fetchall()]

    def count(self, statuses=ACTIVE) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM memories WHERE status = ANY(%s)", (list(statuses),)
        ).fetchone()
        return int(row["c"])

    def vector_search(self, query_vec, k: int, scope=None) -> list[tuple[str, float]]:
        q = (
            "SELECT v.id AS id, 1 - (v.embedding <=> %s) AS sim FROM vectors v "
            "JOIN memories m ON m.id=v.id WHERE m.status='active'"
        )
        args: list = [query_vec]
        if scope:
            q += " AND (m.scope=%s OR m.scope='global')"
            args.append(scope)
        q += " ORDER BY v.embedding <=> %s LIMIT %s"
        args += [query_vec, k]
        return [(r["id"], float(r["sim"])) for r in self.conn.execute(q, args).fetchall()]

    def keyword_search(self, query: str, k: int, scope=None) -> list[tuple[str, float]]:
        import re

        terms = re.findall(r"[A-Za-z0-9]+", query.lower())[:8]
        if not terms:
            return []
        clause = " OR ".join("content ILIKE %s" for _ in terms)
        q = f"SELECT id, content FROM memories WHERE status='active' AND ({clause})"
        args: list = [f"%{t}%" for t in terms]
        if scope:
            q += " AND (scope=%s OR scope='global')"
            args.append(scope)
        rows = self.conn.execute(q, args).fetchall()
        out = [(r["id"], float(sum(1 for t in terms if t in r["content"].lower()))) for r in rows]
        out.sort(key=lambda t: t[1], reverse=True)
        return out[:k]

    def neighbors(self, memory_id: str, depth: int = 1) -> list[Memory]:
        seen = {memory_id}
        frontier = {memory_id}
        for _ in range(depth):
            nxt: set[str] = set()
            for nid in frontier:
                for r in self.conn.execute(
                    "SELECT to_id AS o FROM edges WHERE from_id=%s "
                    "UNION SELECT from_id AS o FROM edges WHERE to_id=%s",
                    (nid, nid),
                ).fetchall():
                    if r["o"] not in seen:
                        nxt.add(r["o"])
                        seen.add(r["o"])
            frontier = nxt
        ids = seen - {memory_id}
        return [m for m in (self.get_memory(i) for i in ids) if m and m.status == Status.ACTIVE]

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
        return int(self.conn.execute("SELECT COUNT(*) c FROM edges").fetchone()["c"])

    def history(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT seq,ts,op,memory_id,detail FROM history ORDER BY seq DESC LIMIT %s", (limit,)
        ).fetchall()
        return [
            {
                "seq": r["seq"],
                "ts": r["ts"],
                "op": r["op"],
                "memory_id": r["memory_id"],
                "detail": r["detail"] or {},
            }
            for r in rows
        ]

    def fingerprints(self) -> list[str]:
        out: list[str] = []
        for r in self.conn.execute(
            "SELECT id,type,content,scope,status,valid_from,valid_to FROM memories"
        ).fetchall():
            out.append(
                "M|"
                + "|".join(
                    str(r[c])
                    for c in ("id", "type", "content", "scope", "status", "valid_from", "valid_to")
                )
            )
        for r in self.conn.execute("SELECT id,from_id,to_id,relation FROM edges").fetchall():
            out.append("E|" + "|".join(str(r[c]) for c in ("id", "from_id", "to_id", "relation")))
        return out

    def reembed(self, embedder) -> int:
        rows = self.conn.execute(
            "SELECT v.id AS id, m.content AS content FROM vectors v JOIN memories m ON m.id=v.id"
        ).fetchall()
        if rows:
            vecs = embedder.embed([r["content"] for r in rows])
            for r, vec in zip(rows, vecs):
                self.conn.execute("UPDATE vectors SET embedding=%s WHERE id=%s", (vec, r["id"]))
        self.set_meta("embedding_provider", "local")
        self.set_meta("embedding_model", embedder.model)
        self.set_meta("embedding_dim", str(embedder.dim))
        return len(rows)

    def get_version(self) -> int:
        return int(self.get_meta("version") or 0)

    def bump_version(self) -> int:
        v = self.get_version() + 1
        self.set_meta("version", str(v))
        return v

    def checkpoint(self) -> None:  # no-op for Postgres
        pass

    def backup_to(self, dest) -> None:  # pragma: no cover
        raise NotImplementedError(
            "snapshotting a Postgres strand to a single .dna file isn't supported yet; "
            "export from a SQLite strand, or use pg_dump for server-side backups."
        )

    def close(self) -> None:
        self.conn.close()


# --- (de)serialization (mirrors sqlite_store) ---
def _prov(p: Provenance) -> dict:
    return {
        "agent": p.agent,
        "ref": p.ref,
        "extractor": p.extractor,
        "origin": p.origin.value,
        "ingested_at": _iso(p.ingested_at),
    }


def _to_prov(d: dict) -> Provenance:
    return Provenance(
        agent=d.get("agent"),
        ref=d.get("ref"),
        extractor=d.get("extractor"),
        origin=Origin(d.get("origin", Origin.USER_ASSERTED.value)),
        ingested_at=_dt(d.get("ingested_at")) or utcnow(),
    )


def _row_to_memory(row: dict) -> Memory:
    attrs = (
        row["attributes"]
        if isinstance(row["attributes"], dict)
        else json.loads(row["attributes"] or "{}")
    )
    prov = (
        row["provenance"]
        if isinstance(row["provenance"], list)
        else json.loads(row["provenance"] or "[]")
    )
    return Memory(
        id=row["id"],
        type=MemoryType(row["type"]),
        content=row["content"],
        scope=row["scope"],
        cognitive=Cognitive(row["cognitive"]),
        attributes=attrs,
        importance=row["importance"],
        confidence=row["confidence"],
        status=Status(row["status"]),
        provenance=[_to_prov(d) for d in prov],
        valid_from=_dt(row["valid_from"]) or utcnow(),
        valid_to=_dt(row["valid_to"]),
        recorded_at=_dt(row["recorded_at"]) or utcnow(),
        created_at=_dt(row["created_at"]) or utcnow(),
        updated_at=_dt(row["updated_at"]) or utcnow(),
        last_seen_at=_dt(row["last_seen_at"]) or utcnow(),
    )
