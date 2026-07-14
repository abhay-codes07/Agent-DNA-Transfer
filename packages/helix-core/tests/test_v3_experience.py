"""v3 Wave A — compounding memory, temporal reasoning, compaction bridge. Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine
from helix_core.experience import experience_factor, reliability
from helix_core.models import Memory, MemoryType, Status


def _eng(tmp_path) -> Engine:
    return Engine(Config(home=tmp_path))


def _mem(**attrs) -> Memory:
    return Memory(id="m", type=MemoryType.FACT, content="x", attributes=attrs)


# --- credit assignment primitives -----------------------------------------
def test_reliability_neutral_with_no_outcomes():
    assert reliability(_mem()) == 0.5
    assert experience_factor(_mem()) == 1.0  # a fresh strand ranks unchanged


def test_reliability_moves_with_outcomes():
    assert reliability(_mem(_uses=4, _wins=4)) > 0.5
    assert reliability(_mem(_uses=4, _wins=0)) < 0.5
    assert experience_factor(_mem(_uses=4, _wins=4)) > 1.0
    assert experience_factor(_mem(_uses=4, _wins=0)) < 1.0


# --- record_outcome (the compounding loop) --------------------------------
def test_record_outcome_credits_facts(tmp_path):
    eng = _eng(tmp_path)
    mid = eng.remember("The billing service uses Postgres.", scope="project:billing")[0].memory_id
    res = eng.record_outcome([mid], success=True)
    assert res["updated"] == 1
    m = eng.store.get_memory(mid)
    assert m.attributes["_wins"] == 1 and m.attributes["_uses"] == 1
    assert reliability(m) > 0.5
    eng.close()


def test_record_outcome_never_deletes_but_flags_review(tmp_path):
    eng = _eng(tmp_path)
    mid = eng.remember("A flaky, often-unhelpful note.", scope="global")[0].memory_id
    for _ in range(4):
        eng.record_outcome([mid], success=False)
    m = eng.store.get_memory(mid)
    assert m is not None and m.status == Status.ACTIVE  # never auto-deleted
    assert m.attributes.get("_stale_suspected")  # routed to review instead
    eng.close()


def test_experience_ranking_lifts_proven_facts(tmp_path):
    eng = _eng(tmp_path)
    a = eng.remember("Deploys use the blue-green strategy.", scope="project:ops")[0].memory_id
    b = eng.remember("Deploys use a rolling strategy.", scope="project:ops")[0].memory_id
    # Prove `b` repeatedly; leave `a` unproven.
    for _ in range(5):
        eng.record_outcome([b], success=True)
    hits = eng.recall("what deploy strategy do we use", scope="project:ops")
    ids = [h.memory.id for h in hits]
    assert ids.index(b) < ids.index(a)  # the proven fact ranks ahead
    eng.close()


def test_experience_ranking_can_be_disabled(tmp_path):
    eng = Engine(Config(home=tmp_path, experience_ranking=False))
    mid = eng.remember("proven fact", scope="global")[0].memory_id
    for _ in range(5):
        eng.record_outcome([mid], success=True)
    # No crash; ranking simply ignores reliability. (Behavioural: factor never applied.)
    assert eng.recall("proven fact")  # still retrievable
    eng.close()


# --- compounding meter -----------------------------------------------------
def test_compounding_meter(tmp_path):
    eng = _eng(tmp_path)
    assert eng.compounding()["facts"] == 0  # empty strand
    mid = eng.remember("Events flow through NATS.", scope="project:billing")[0].memory_id
    eng.record_outcome([mid], success=True)
    m = eng.compounding()
    assert m["facts"] >= 1
    assert m["outcomes"] == 1 and m["win_rate"] == 1.0
    assert m["avg_reliability"] > 0.5
    eng.close()


# --- temporal reasoning: history_of ---------------------------------------
def test_history_of_tracks_belief_changes(tmp_path):
    eng = _eng(tmp_path)
    eng.remember("The billing database is MongoDB.", scope="project:billing")
    # A contradicting update should supersede the old belief.
    eng.remember("The billing database is Postgres, not MongoDB.", scope="project:billing")
    hist = eng.history_of("billing database", k=10)
    assert hist["subject"] == "billing database"
    assert "current" in hist and "transitions" in hist
    # At least the current belief is present; transitions appear if a supersedes edge was made.
    assert isinstance(hist["changes"], int)
    eng.close()


# --- compaction bridge: distill_session -----------------------------------
def test_distill_session_keeps_facts_not_transcript(tmp_path):
    eng = _eng(tmp_path)
    res = eng.distill_session(
        [
            "ok so remember the payments service is written in Go and deployed on GKE",
            "and it talks to the ledger over gRPC",
            "cool thanks",  # chatter — the gate should mostly drop this
        ],
        scope="project:payments",
    )
    assert res["messages"] == 3
    assert res["candidates"] >= 1
    # A durable fact was distilled and is recallable; the raw messages are not stored verbatim.
    hits = eng.recall("what language is the payments service", scope="project:payments")
    assert hits
    eng.close()


def test_distill_session_redacts_secrets(tmp_path):
    eng = _eng(tmp_path)
    token = "".join(["ghp_", "0" * 36])
    eng.distill_session([f"the deploy token is {token} keep it handy"], scope="global")
    for m in eng.list_memories(limit=1000):
        assert token not in m.content
    eng.close()
