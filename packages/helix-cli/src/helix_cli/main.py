"""The `helix` command (Typer) — Phase 1: a working local, $0, offline memory CLI.

Thin front-end over helix_core.Engine (no business logic here). Git-like verbs; transfer
commands (export/import/merge) land in Phase 4.
"""

from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.table import Table

from helix_core.engine import Engine
from helix_core.models import GLOBAL
from helix_core.serialize import hit_to_dict, memory_to_dict

# Ensure UTF-8 output so box-drawing/emoji render on Windows legacy consoles (cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

app = typer.Typer(
    add_completion=False,
    help="Helix - take your AI's memory anywhere. Local-first, portable, $0 by default.",
)
# legacy_windows=False avoids rich's cp1252 win32 renderer path.
console = Console(legacy_windows=False)


def _engine() -> Engine:
    return Engine()


@app.command()
def init() -> None:
    """Create (or open) your local memory strand and show its details."""
    eng = _engine()
    s = eng.stats()
    console.print("[bold green]Helix strand ready[/]")
    console.print(f"  strand:     [cyan]{s['strand_path']}[/]")
    console.print(f"  embeddings: {s['embedding_model']} ({s['embedding_dim']}d)")
    console.print(f"  memories:   {s['active_memories']}")
    eng.close()


@app.command()
def add(
    text: str,
    scope: str = typer.Option(GLOBAL, help="global or project:<id>"),
) -> None:
    """Teach Helix a fact (stored locally, free, offline)."""
    eng = _engine()
    results = eng.remember(text, scope=scope, source="cli")
    for r in results:
        color = {"ADD": "green", "UPDATE": "yellow", "NOOP": "dim", "SUPERSEDE": "magenta"}.get(
            r.op, "white"
        )
        console.print(f"  [{color}]{r.op}[/] [cyan]{r.memory_id}[/]")
    if not results:
        console.print("[dim]nothing durable to remember in that input[/]")
    eng.close()


@app.command()
def search(
    query: str,
    scope: str = typer.Option(None, help="restrict to a scope"),
    k: int = typer.Option(8, help="max results"),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """Recall memories matching a query (hybrid search + ranking)."""
    eng = _engine()
    hits = eng.recall(query, scope=scope, k=k)
    if as_json:
        print(json.dumps([hit_to_dict(h) for h in hits], indent=2))
    elif not hits:
        console.print("[dim]no matching memories[/]")
    else:
        table = Table(show_lines=False)
        table.add_column("score", justify="right", style="green")
        table.add_column("type", style="cyan")
        table.add_column("memory")
        for h in hits:
            table.add_row(f"{h.score:.2f}", h.memory.type.value, h.memory.content)
        console.print(table)
    eng.close()


@app.command(name="list")
def list_cmd(
    scope: str = typer.Option(None, help="restrict to a scope"),
    limit: int = typer.Option(50),
    as_json: bool = typer.Option(False, "--json", help="machine-readable output"),
) -> None:
    """List stored memories."""
    eng = _engine()
    mems = eng.list_memories(scope=scope, limit=limit)
    if as_json:
        print(json.dumps([memory_to_dict(m) for m in mems], indent=2))
        eng.close()
        return
    table = Table(show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("type")
    table.add_column("scope", style="dim")
    table.add_column("memory")
    for m in mems:
        table.add_row(m.id, m.type.value, m.scope, m.content)
    console.print(table if mems else "[dim]no memories yet — try `helix add`[/]")
    eng.close()


@app.command()
def context(
    scope: str = typer.Option(None),
    query: str = typer.Option(None, help="optional focusing query"),
    budget: int = typer.Option(1500, help="token budget"),
) -> None:
    """Print a packed context block (what an agent would receive)."""
    eng = _engine()
    console.print(eng.context(scope=scope, query=query, budget_tokens=budget) or "[dim](empty)[/]")
    eng.close()


@app.command()
def forget(target: str) -> None:
    """Soft-delete a memory by id or top query match (recoverable via history)."""
    eng = _engine()
    removed = eng.forget(target)
    console.print(f"[magenta]forgot[/] {removed}" if removed else "[dim]nothing matched[/]")
    eng.close()


@app.command()
def relate(from_id: str, to_id: str, relation: str = typer.Argument("related_to")) -> None:
    """Link two memories with a typed relation (feeds graph-expansion recall)."""
    eng = _engine()
    eid = eng.relate(from_id, to_id, relation)
    console.print(f"[green]linked[/] {from_id} --{relation}--> {to_id}  [dim]({eid})[/]")
    eng.close()


@app.command()
def maintain(
    min_age_days: float = typer.Option(30.0, help="only archive memories older than this"),
) -> None:
    """Housekeeping: archive stale, low-salience memories (decay-driven, never deletes)."""
    eng = _engine()
    res = eng.maintain(min_age_days=min_age_days)
    console.print(f"scanned {res['scanned']}, [magenta]archived {res['archived']}[/]")
    eng.close()


@app.command()
def connect(
    agent: str = typer.Argument(..., help="claude-code | cursor | windsurf | vscode | gemini | zed | codex"),
    print_only: bool = typer.Option(False, "--print", help="preview the config without writing"),
) -> None:
    """Wire Helix into an AI agent over MCP by writing its config (idempotent)."""
    try:
        from helix_mcp.connect import connect as do_connect
    except ImportError:
        console.print("[red]helix-mcp is not installed[/] (pip install helix-mcp)")
        raise typer.Exit(1)
    try:
        res = do_connect(agent, dry_run=print_only)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    verb = "would write" if print_only else "wrote"
    console.print(f"[green]{verb}[/] helix MCP config -> [cyan]{res['path']}[/]  (key: {res['key']})")
    console.print(res["preview"], markup=False)  # don't let rich parse [section] as markup
    if not print_only:
        console.print("[dim]restart the agent to load the new server[/]")


@app.command()
def doctor() -> None:
    """Diagnose setup: strand, embeddings, store, optional accelerators."""
    eng = _engine()
    s = eng.stats()
    table = Table(title="helix doctor", show_header=False)
    table.add_column(style="cyan")
    table.add_column()
    for key, val in s.items():
        table.add_row(key, str(val))
    console.print(table)
    console.print("[green]OK - running fully local and $0[/]" if not s["fastembed"]
                  else "[green]OK - fastembed available (local embeddings)[/]")
    eng.close()


@app.command()
def status() -> None:
    """Alias for `doctor`."""
    doctor()


if __name__ == "__main__":
    app()
