"""Wave B — proactive surfacing (§2.4) + lazy thematic view (§2.6). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.models import Cognitive, Memory, MemoryType, utcnow


def _put(eng, mid, content, *, confidence=0.8, scope="project:billing", stale=False):
    now = utcnow()
    attrs = {"_stale_suspected": True} if stale else {}
    m = Memory(
        id=mid,
        type=MemoryType.FACT,
        content=content,
        scope=scope,
        cognitive=Cognitive.SEMANTIC,
        confidence=confidence,
        attributes=attrs,
        valid_from=now,
        recorded_at=now,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )
    with eng.store.tx():
        eng.store.upsert_memory(m, eng.embedder.embed([content])[0])


def test_proactive_gates_on_confidence_and_staleness(tmp_path):
    eng = Engine(Config(home=tmp_path))
    _put(eng, "hi", "We use Postgres for the billing database", confidence=0.9)
    _put(eng, "lo", "We might switch the billing database to MySQL", confidence=0.3)
    _put(eng, "st", "The billing database runs on an old box", confidence=0.9, stale=True)
    facts = eng.proactive("editing the billing database layer", scope="project:billing", k=3)
    contents = [f["content"] for f in facts]
    assert any("Postgres" in c for c in contents)
    assert all("MySQL" not in c for c in contents)  # below the confidence gate
    assert all("old box" not in c for c in contents)  # stale-suspected, not surfaced
    eng.close()


def test_proactive_returns_nothing_when_unsure(tmp_path):
    eng = Engine(Config(home=tmp_path))
    _put(eng, "lo", "Maybe we will use Redis", confidence=0.2)
    assert eng.proactive("caching layer", scope="project:billing") == []
    eng.close()


def test_themes_ranks_recurring_subjects(tmp_path):
    eng = Engine(Config(home=tmp_path))
    _put(eng, "a", "Postgres is our main database", confidence=0.8)
    _put(eng, "b", "Postgres connection pooling uses pgbouncer", confidence=0.8)
    _put(eng, "c", "We deploy on Fly.io", confidence=0.8)
    rows = eng.themes(scope="project:billing")
    topics = {r["topic"]: r["mentions"] for r in rows}
    assert topics.get("postgres", 0) >= 2
    assert "fly.io" in topics
    eng.close()
