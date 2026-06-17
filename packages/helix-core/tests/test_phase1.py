"""Phase 1 integration + unit tests — all offline, no network, no third-party deps.

Proves the $0/offline path is first-class (CLAUDE.md rule 3): these run with the
dependency-free hashing embedder and embedded SQLite store.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from helix_core.config import Config
from helix_core.decay import salience
from helix_core.embed import HashingEmbedder, cosine, from_bytes, to_bytes
from helix_core.engine import Engine
from helix_core.models import Cognitive, Memory, MemoryType, utcnow
from helix_core.stores import SqliteStore


# --- embeddings ---

def test_embedding_is_normalized_and_semantic():
    e = HashingEmbedder(dim=256)
    v = e.embed(["we use postgres for the billing service"])[0]
    assert len(v) == 256
    assert abs(sum(x * x for x in v) - 1.0) < 1e-5  # unit length

    related = e.embed(["which database does the billing service use"])[0]
    unrelated = e.embed(["the weather in paris is sunny today"])[0]
    base = e.embed(["we use postgres for the billing service"])[0]
    assert cosine(related, base) > cosine(unrelated, base)


def test_vector_byte_roundtrip():
    v = HashingEmbedder(dim=64).embed(["roundtrip"])[0]
    assert from_bytes(to_bytes(v)) == pytest.approx(v, abs=1e-6)


# --- store ---

def test_store_roundtrip_and_search(tmp_path):
    e = HashingEmbedder()
    st = SqliteStore(tmp_path / "s.helix.db")
    st.ensure_embedding_space(e.model, e.dim)
    m = Memory(id="fact_fri_1", type=MemoryType.FACT, content="deploys are frozen on fridays")
    with st.tx():
        st.upsert_memory(m, e.embed([m.content])[0])
    assert st.count() == 1
    assert st.get_memory("fact_fri_1").content == m.content

    hits = st.vector_search(e.embed(["when are deploys frozen"])[0], 5)
    assert hits and hits[0][0] == "fact_fri_1"
    kw = st.keyword_search("deploys frozen", 5)
    assert any(mid == "fact_fri_1" for mid, _ in kw)
    st.close()


def test_embedding_space_mismatch_is_rejected(tmp_path):
    st = SqliteStore(tmp_path / "s.helix.db")
    st.ensure_embedding_space("model-a", 256)
    with pytest.raises(ValueError):
        st.ensure_embedding_space("model-b", 384)
    st.close()


# --- decay ---

def test_episodic_decays_to_half_life():
    m = Memory(
        id="ep1", type=MemoryType.EPISODE, content="x",
        cognitive=Cognitive.EPISODIC, importance=1.0,
    )
    now = m.last_seen_at
    assert salience(m, now) == pytest.approx(1.0, abs=1e-6)
    # one 7-day half-life -> ~0.5
    assert salience(m, now + timedelta(days=7)) == pytest.approx(0.5, abs=0.02)
    # semantic barely decays over the same window
    m.cognitive = Cognitive.SEMANTIC
    assert salience(m, now + timedelta(days=7)) > 0.99


# --- engine: remember / recall / forget ---

def _engine(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


def test_remember_and_recall(tmp_path):
    eng = _engine(tmp_path)
    eng.remember(
        "We chose Postgres over Mongo for billing because it needs ACID transactions.",
        scope="project:billing",
    )
    eng.remember("All API errors use RFC-7807 problem+json.", scope="project:billing")
    eng.remember("I prefer pytest over unittest.")

    hits = eng.recall("which database did we pick for billing", scope="project:billing")
    assert hits
    assert any("postgres" in h.memory.content.lower() for h in hits)
    eng.close()


def test_identical_restatement_is_noop(tmp_path):
    eng = _engine(tmp_path)
    r1 = eng.remember("Deploys are frozen on Fridays.")
    r2 = eng.remember("deploys are FROZEN on fridays")  # same after lowercasing
    assert r1[0].op == "ADD"
    assert r2[0].op in {"NOOP", "UPDATE", "SUPERSEDE"}
    # exactly one active 'deploy' memory survives
    actives = [m for m in eng.list_memories() if "deploy" in m.content.lower()]
    assert len(actives) == 1
    eng.close()


def test_forget_removes_from_recall(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("The staging database password rotates monthly.", scope="project:ops")
    hits = eng.recall("staging database password", scope="project:ops")
    assert hits
    target = hits[0].memory.id
    assert eng.forget(target) == [target]
    after = eng.recall("staging database password", scope="project:ops")
    assert all(h.memory.id != target for h in after)
    eng.close()


def test_scope_isolation(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("This service uses NATS for events.", scope="project:alpha")
    eng.remember("This service uses Kafka for events.", scope="project:beta")
    hits = eng.recall("what message bus do we use", scope="project:alpha")
    contents = " ".join(h.memory.content.lower() for h in hits)
    assert "nats" in contents
    assert "kafka" not in contents  # beta is out of scope
    eng.close()


def test_context_packs_a_block(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("We use FastAPI and Postgres.", scope="project:billing")
    eng.remember("All API errors use RFC-7807.", scope="project:billing")
    block = eng.context(scope="project:billing", budget_tokens=500)
    assert "FastAPI" in block or "RFC-7807" in block
    eng.close()


def test_secrets_are_redacted_before_storage(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("My OpenAI key is sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345 keep it safe")
    for m in eng.list_memories():
        assert "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ012345" not in m.content
    eng.close()


def test_stats_report_offline_zero_cost(tmp_path):
    eng = _engine(tmp_path)
    s = eng.stats()
    assert s["embedding_dim"] > 0
    assert s["active_memories"] == 0
    eng.close()
