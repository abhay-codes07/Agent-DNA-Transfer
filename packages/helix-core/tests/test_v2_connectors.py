"""Wave B — the repo/GitHub connector (v2 plan §5.6). Offline / $0."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.connectors.repo import repo_facts
from helix_core.engine import Engine


def _make_repo(root):
    (root / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length=100\n[tool.black]\n[tool.mypy]\ndeps=['pytest']\n[tool.uv]\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (root / "CODEOWNERS").write_text("* @alice @bob\n# comment\n", encoding="utf-8")
    (root / "CONTRIBUTING.md").write_text(
        "# Contributing\n\n- Always write type hints in core modules.\n- Prefer composition over inheritance.\n",
        encoding="utf-8",
    )
    (root / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")


def test_repo_facts_detects_stack_and_tooling(tmp_path):
    _make_repo(tmp_path)
    facts = " | ".join(repo_facts(tmp_path))
    assert "written in Python" in facts
    assert "ruff" in facts and "black" in facts and "mypy" in facts and "pytest" in facts
    assert "managed with uv" in facts
    assert "GitHub Actions" in facts
    assert "Dockerfile" in facts
    assert "@alice" in facts and "@bob" in facts  # CODEOWNERS


def test_ingest_repo_stores_facts_and_doc(tmp_path):
    repo = tmp_path / "myproj"
    repo.mkdir()
    _make_repo(repo)
    eng = Engine(Config(home=tmp_path / "home"))
    res = eng.ingest_repo(str(repo))
    assert res["scope"] == "project:myproj"
    assert res["facts"] >= 6
    assert res["doc"] == "CONTRIBUTING.md"
    # The learned facts are recallable.
    hits = eng.recall("what linter does this project use", scope="project:myproj")
    assert any("ruff" in h.memory.content.lower() for h in hits)
    eng.close()


def test_repo_facts_empty_for_bare_dir(tmp_path):
    assert repo_facts(tmp_path) == []
