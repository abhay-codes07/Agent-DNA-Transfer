"""Wave C — the Portable Agent Memory open standard (v2 plan §8). Offline / $0."""

from __future__ import annotations

import json

from helix_core import standard
from helix_core.config import Config
from helix_core.engine import Engine


def _eng(tmp_path) -> Engine:
    eng = Engine(Config(home=tmp_path))
    eng.remember("We chose Postgres for the billing service.", scope="project:billing")
    eng.remember("All API errors use RFC-7807.", scope="project:billing")
    return eng


def test_export_is_conformant_core(tmp_path):
    eng = _eng(tmp_path)
    res = eng.export_portable(tmp_path / "brain.json")
    assert res["memories"] >= 2 and res["level"] == "core"
    doc = json.loads((tmp_path / "brain.json").read_text())
    assert doc["format"] == "portable-agent-memory"
    rep = standard.validate(doc)
    assert rep["valid"] and rep["level"] == "core"
    # Every record has the required fields.
    for m in doc["memories"]:
        for key in ("id", "type", "content", "created_at", "provenance"):
            assert key in m
    eng.close()


def test_signed_export_reaches_signed_level(tmp_path):
    eng = _eng(tmp_path)
    eng.export_portable(tmp_path / "brain.json", sign=True)
    doc = json.loads((tmp_path / "brain.json").read_text())
    rep = standard.validate(doc)
    assert rep["valid"] and rep["level"] == "signed"
    assert "integrity" in doc and all(m.get("signature") for m in doc["memories"])
    eng.close()


def test_conform_via_engine_and_detects_violations(tmp_path):
    eng = _eng(tmp_path)
    eng.export_portable(tmp_path / "ok.json")
    assert eng.conform(tmp_path / "ok.json")["valid"] is True

    # A broken doc is rejected with specific errors.
    bad = {"format": "portable-agent-memory", "version": "1.0", "memories": [{"content": "x"}]}
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    rep = eng.conform(tmp_path / "bad.json")
    assert rep["valid"] is False
    assert any("missing required 'id'" in e for e in rep["errors"])
    assert any("unknown type" in e for e in rep["errors"])
    eng.close()


def test_validate_rejects_wrong_format():
    assert standard.validate({"format": "nope", "version": "1.0", "memories": []})["valid"] is False
    assert standard.validate("not a dict")["valid"] is False
