"""The `helix` command (Typer).

Git-like verbs over the engine. Pre-alpha: commands are wired and documented; bodies land
per ROADMAP. The CLI is a thin front-end over helix_core.Engine (no business logic here).
"""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    add_completion=False,
    help="🧬 Helix — take your AI's memory anywhere. Local-first, portable, $0 by default.",
)
console = Console()


@app.command()
def init() -> None:
    """Create a new local memory strand (generates your signing identity)."""
    console.print("[yellow]Phase 1[/]: create ~/.helix strand + Ed25519 identity")


@app.command()
def connect(agent: str) -> None:
    """Wire Helix into an agent over MCP (claude-code, cursor, windsurf, ...)."""
    console.print(f"[yellow]Phase 2[/]: write MCP config for '{agent}' (idempotent)")


@app.command()
def search(query: str, scope: str = typer.Option(None)) -> None:
    """Recall memories matching a query."""
    console.print(f"[yellow]Phase 1[/]: recall '{query}' (scope={scope or 'all'})")


@app.command()
def add(text: str, scope: str = typer.Option("global")) -> None:
    """Teach Helix a fact directly."""
    console.print(f"[yellow]Phase 1[/]: remember (scope={scope})")


@app.command()
def forget(target: str) -> None:
    """Soft-delete a memory by id or query (recoverable via history)."""
    console.print(f"[yellow]Phase 1[/]: forget '{target}'")


@app.command(name="export")
def export_cmd(out: str) -> None:
    """Export your memory to a portable, signed, encrypted .dna strand."""
    console.print(f"[yellow]Phase 4[/]: export -> {out}")


@app.command(name="import")
def import_cmd(path: str) -> None:
    """Import a .dna strand (verifies signature, decrypts, checks compatibility)."""
    console.print(f"[yellow]Phase 4[/]: import {path}")


@app.command()
def merge(path: str) -> None:
    """Merge another .dna strand into yours (conflict-aware, reversible)."""
    console.print(f"[yellow]Phase 4[/]: merge {path}")


@app.command()
def log() -> None:
    """Show how your memory evolved (git-style history)."""
    console.print("[yellow]Phase 4[/]: strand history")


@app.command()
def doctor() -> None:
    """Diagnose setup: config, model cache, store, and agent connections."""
    console.print("[yellow]Phase 1[/]: environment + connection checks")


if __name__ == "__main__":
    app()
