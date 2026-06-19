"""GitHub / code-repo connector (local form, v2 plan §5.6).

Distills durable, high-value facts from a repository's docs and configs — the stack, the tooling,
CI, ownership — the things a coding agent should just *know*. Reads only what's on disk (a clone),
emits distilled facts (never raw file contents), and is fully $0/offline. The hosted GitHub App
(webhooks over PRs/pushes) is the networked extension of this; the distillation logic is shared.
"""

from __future__ import annotations

import json
from pathlib import Path


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""


def _codeowners(root: Path) -> str | None:
    for cand in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        p = root / cand
        if p.exists():
            owners: list[str] = []
            for line in _read(p).splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                owners += [t for t in line.split()[1:] if t.startswith("@")]
            uniq = sorted(dict.fromkeys(owners))
            if uniq:
                return ", ".join(uniq[:6])
    return None


def repo_facts(root: Path) -> list[str]:
    """Pure: derive durable facts from a repo on disk. Deterministic, no network, no side effects."""
    facts: list[str] = []

    # --- stack + Python tooling ---
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        txt = _read(pyproject)
        facts.append("This project is written in Python.")
        if "[tool.ruff" in txt:
            facts.append("This project uses ruff for linting.")
        if "[tool.black" in txt:
            facts.append("This project uses black for formatting.")
        if "[tool.mypy" in txt:
            facts.append("This project uses mypy for type checking.")
        if "pytest" in txt:
            facts.append("This project uses pytest for tests.")
        if "[tool.uv" in txt or (root / "uv.lock").exists():
            facts.append("This project is managed with uv.")

    pkg = root / "package.json"
    if pkg.exists():
        facts.append("This project uses Node.js / JavaScript.")
        try:
            data = json.loads(_read(pkg) or "{}")
        except json.JSONDecodeError:
            data = {}
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        for name, fact in [
            ("typescript", "This project uses TypeScript."),
            ("react", "This project uses React."),
            ("vue", "This project uses Vue."),
            ("eslint", "This project uses ESLint for linting."),
            ("prettier", "This project uses Prettier for formatting."),
            ("vitest", "This project uses Vitest for tests."),
        ]:
            if name in deps:
                facts.append(fact)

    for fname, fact in [
        ("Cargo.toml", "This project is written in Rust."),
        ("go.mod", "This project is written in Go."),
        ("Gemfile", "This project is written in Ruby."),
        ("pom.xml", "This project uses Java/Maven."),
        ("Dockerfile", "This project ships a Dockerfile."),
    ]:
        if (root / fname).exists():
            facts.append(fact)

    # --- CI ---
    wf = root / ".github" / "workflows"
    if wf.is_dir() and any(wf.glob("*.yml")) or (wf.is_dir() and any(wf.glob("*.yaml"))):
        facts.append("CI runs via GitHub Actions.")

    # --- ownership ---
    owners = _codeowners(root)
    if owners:
        facts.append(f"Code ownership (CODEOWNERS): {owners}.")

    return facts


def contributing_doc(root: Path) -> Path | None:
    """The contributing/AGENTS doc to ingest as distilled notes, if present."""
    for cand in ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "AGENTS.md", "CLAUDE.md"):
        p = root / cand
        if p.exists():
            return p
    return None
