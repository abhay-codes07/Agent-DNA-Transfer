"""Phase 1 polish tests: .env loading, graph relate/expansion, maintenance, serialization.

All offline, no third-party deps (fastembed test is skipped when absent).
"""

from __future__ import annotations

import importlib.util
import os
from datetime import timedelta

import pytest

from helix_core.config import Config, load_dotenv
from helix_core.engine import Engine
from helix_core.models import Cognitive, Memory, MemoryType, utcnow
from helix_core.retrieve import recall as retrieve_recall
from helix_core.serialize import hit_to_dict


def _engine(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


def test_dotenv_is_loaded_and_env_wins(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "HELIX_TELEMETRY=local\nHELIX_STRAND=teststrand\n# a comment\n", encoding="utf-8"
    )
    saved = dict(os.environ)
    try:
        os.environ.pop("HELIX_TELEMETRY", None)
        os.environ.pop("HELIX_STRAND", None)
        load_dotenv(str(env))
        assert os.environ["HELIX_TELEMETRY"] == "local"
        cfg = Config()
        assert cfg.strand == "teststrand"
        # a real env var must win over .env
        os.environ["HELIX_STRAND"] = "realstrand"
        load_dotenv(str(env))
        assert os.environ["HELIX_STRAND"] == "realstrand"
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_graph_expansion_boosts_connected_memory(tmp_path):
    eng = _engine(tmp_path)
    a = eng.remember("The billing service is owned by the payments team.", scope="project:billing")[
        0
    ].memory_id
    b = eng.remember("Release checklist lives in the team wiki.", scope="project:ops")[0].memory_id
    eng.relate(a, b, "documented_in")

    q = "who owns the billing service"
    base = retrieve_recall(eng.store, eng.embedder, q, expand=False, k=50)
    expanded = retrieve_recall(eng.store, eng.embedder, q, expand=True, k=50)

    def score_of(hits, mid):
        return next((h.score for h in hits if h.memory.id == mid), 0.0)

    assert a in {h.memory.id for h in expanded}
    # b is connected to the strong seed a, so graph expansion raises its score.
    assert score_of(expanded, b) > score_of(base, b)
    eng.close()


def test_hub_nodes_never_surface(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("We deploy with GitHub Actions.", scope="project:billing")
    # the auto-created project hub must not appear in list/search
    assert all(not m.attributes.get("_hub") for m in eng.list_memories())
    hits = eng.recall("project billing", scope="project:billing")
    assert all("Project:" not in h.memory.content for h in hits)
    eng.close()


def test_maintain_archives_stale_episodic(tmp_path):
    eng = _engine(tmp_path)
    old = utcnow() - timedelta(days=60)
    m = Memory(
        id="ep_old_event",
        type=MemoryType.EPISODE,
        content="transient: CI was flaky on tuesday",
        cognitive=Cognitive.EPISODIC,
        importance=0.3,
        valid_from=old,
        recorded_at=old,
        created_at=old,
        updated_at=old,
        last_seen_at=old,
    )
    with eng.store.tx():
        eng.store.upsert_memory(m, eng.embedder.embed([m.content])[0])
    res = eng.maintain()
    assert res["archived"] >= 1
    assert eng.store.get_memory("ep_old_event").status.value == "archived"
    eng.close()


def test_fresh_semantic_not_archived(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("We use Postgres for billing.", scope="project:billing")
    res = eng.maintain()
    assert res["archived"] == 0  # fresh semantic facts survive
    eng.close()


def test_hit_serialization_hides_internal_fields(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("We use Kafka for the event bus.", scope="project:x")
    hits = eng.recall("event bus", scope="project:x")
    d = hit_to_dict(hits[0])
    assert d["content"]
    assert d["score"] >= 0.0
    assert "_reinforced" not in repr(d)  # internal counters stay private
    eng.close()


@pytest.mark.skipif(importlib.util.find_spec("fastembed") is None, reason="fastembed not installed")
def test_fastembed_adapter_when_present():
    from helix_core.embed.local import LocalEmbedder

    e = LocalEmbedder()
    v = e.embed(["hello world"])[0]
    assert len(v) == e.dim > 0
    assert abs(sum(x * x for x in v) - 1.0) < 1e-3  # normalized


@pytest.mark.skipif(importlib.util.find_spec("fastembed") is None, reason="fastembed not installed")
def test_fastembed_captures_semantics_without_shared_words():
    """Real semantics: paraphrases with NO shared words rank above an unrelated sentence —
    something the lexical hashing embedder cannot do."""
    from helix_core.embed import cosine
    from helix_core.embed.local import LocalEmbedder

    e = LocalEmbedder()
    query = e.embed(["how do we persist application data"])[0]
    related = e.embed(["the database we chose for storage"])[0]
    unrelated = e.embed(["my favourite breakfast is pancakes"])[0]
    assert cosine(query, related) > cosine(query, unrelated)
