"""The `helix` command (Typer) — Phase 1: a working local, $0, offline memory CLI.

Thin front-end over helix_core.Engine (no business logic here). Git-like verbs; transfer
commands (export/import/merge) land in Phase 4.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
def ingest(
    path: str,
    scope: str = typer.Option(GLOBAL, help="global or project:<id>"),
) -> None:
    """Seed memory from a markdown/text file or directory of notes."""
    eng = _engine()
    p = Path(path)
    if p.is_dir():
        res = eng.ingest_dir(str(p), scope=scope)
        console.print(
            f"[green]ingested[/] {res['files']} files, {res['slices']} slices -> {res['stored']}"
        )
    else:
        res = eng.ingest_file(str(p), scope=scope)
        console.print(f"[green]ingested[/] {res['slices']} slices -> {res['stored']}")
    eng.close()


@app.command(name="export-md")
def export_md(out: str) -> None:
    """Export your memory as human-readable, portable Markdown."""
    eng = _engine()
    n = eng.export_markdown(out)
    console.print(f"[green]exported[/] {n} memories -> [cyan]{out}[/] (markdown)")
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
    agent: str = typer.Argument(
        ..., help="claude-code | claude-desktop | cursor | windsurf | vscode | gemini | zed | codex"
    ),
    print_only: bool = typer.Option(False, "--print", help="preview the config without writing"),
    path: str = typer.Option(None, "--path", help="write to a custom config file (any MCP client)"),
    key: str = typer.Option(None, "--key", help="config key for --path (default: mcpServers)"),
) -> None:
    """Wire Helix into an AI agent over MCP by writing its config (idempotent)."""
    try:
        from helix_mcp.connect import connect as do_connect
    except ImportError:
        console.print("[red]helix-mcp is not installed[/] (pip install helix-mcp)")
        raise typer.Exit(1)
    try:
        res = do_connect(agent, dry_run=print_only, path_override=path, key_override=key)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    verb = "would write" if print_only else "wrote"
    console.print(
        f"[green]{verb}[/] helix MCP config -> [cyan]{res['path']}[/]  (key: {res['key']})"
    )
    console.print(res["preview"], markup=False)  # don't let rich parse [section] as markup
    if not print_only:
        console.print("[dim]restart the agent to load the new server[/]")


@app.command()
def dashboard(
    port: int = typer.Option(8787),
    host: str = typer.Option("127.0.0.1"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Launch the local memory dashboard (browse, search, edit, curate) in your browser."""
    from helix_core.daemon import serve

    console.print(
        f"[green]Helix dashboard[/] -> [cyan]http://{host}:{port}[/]  [dim](Ctrl-C to stop)[/]"
    )
    serve(host=host, port=port, open_browser=open_browser)


@app.command()
def relay(
    directory: str = typer.Argument("./helix-relay", help="where to store encrypted strands"),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8788),
    token: str = typer.Option(None, help="optional bearer token (or HELIX_RELAY_TOKEN)"),
) -> None:
    """Run a thin HTTP relay so teammates can `push`/`pull` encrypted .dna strands."""
    import os

    from helix_core.relay import serve_relay

    tok = token or os.environ.get("HELIX_RELAY_TOKEN")
    console.print(
        f"[green]Helix relay[/] on [cyan]http://{host}:{port}[/] serving {directory}"
        f"  [dim](Ctrl-C to stop)[/]"
    )
    serve_relay(directory, host=host, port=port, token=tok)


@app.command(name="eval")
def eval_cmd(k: int = typer.Option(5, help="top-k for precision/recall")) -> None:
    """Run the built-in recall-quality benchmark (precision/recall@k, MRR, latency)."""
    from helix_core.eval import CODING_BENCHMARK, run_eval

    res = run_eval(CODING_BENCHMARK, k=k)
    table = Table(title="Helix recall benchmark (coding-agent memory)", show_header=False)
    table.add_column(style="cyan")
    table.add_column(justify="right")
    for key, val in res.as_dict().items():
        table.add_row(key, str(val))
    console.print(table)
    console.print("[dim]metrics depend on the active embedder (hashing vs fastembed)[/]")


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
    console.print(
        "[green]OK - running fully local and $0[/]"
        if not s["fastembed"]
        else "[green]OK - fastembed available (local embeddings)[/]"
    )
    eng.close()


@app.command()
def status() -> None:
    """Alias for `doctor`."""
    doctor()


# --- transfer: the portable .dna strand (Phase 4) ---


@app.command(name="export")
def export_cmd(
    out: str,
    passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE"),
    label: str = typer.Option("", help="a label for this export"),
) -> None:
    """Export your memory to a portable, signed, encrypted .dna strand."""
    eng = _engine()
    try:
        m = eng.export_strand(out, passphrase=passphrase, label=label)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    console.print(f"[green]exported[/] -> [cyan]{out}[/]")
    console.print(f"  version {m.version} · {m.count_memories} memories · {m.count_edges} edges")
    console.print(
        f"  merkle [dim]{m.merkle_root[:16]}…[/]  signed by [dim]{m.created_by_pubkey[:16]}…[/]"
    )
    eng.close()


@app.command()
def verify(file: str) -> None:
    """Verify a .dna signature and integrity (no passphrase needed)."""
    eng = _engine()
    v = eng.verify_strand(file)
    sig = "[green]valid[/]" if v["signature_valid"] else "[red]INVALID[/]"
    dbh = "[green]valid[/]" if v["db_hash_valid"] else "[red]INVALID[/]"
    console.print(f"signature: {sig}   integrity hash: {dbh}")
    console.print(f"signed by: [dim]{v['pubkey']}[/]")
    eng.close()


@app.command(name="import")
def import_cmd(
    file: str,
    passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE"),
    as_strand: str = typer.Option(None, "--as", help="import as a new named strand"),
    replace: bool = typer.Option(False, help="replace the active strand (rollback)"),
) -> None:
    """Import a .dna strand (verifies signature, decrypts, checks integrity)."""
    eng = _engine()
    try:
        res = eng.import_strand(file, passphrase=passphrase, as_strand=as_strand, replace=replace)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    m = res["manifest"]
    console.print(f"[green]imported[/] {m.count_memories} memories -> [cyan]{res['dest']}[/]")
    if not replace and res["strand"] != "default":
        console.print(f"[dim]switch to it with HELIX_STRAND={res['strand']}[/]")
    eng.close()


@app.command()
def merge(file: str, passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE")) -> None:
    """Merge another .dna strand into yours (conflict-aware dedup)."""
    eng = _engine()
    try:
        res = eng.merge_strand(file, passphrase=passphrase)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    o = res["merged"]
    console.print(
        f"[green]merged[/]: {o['ADD']} added, {o['UPDATE']} updated, "
        f"{o['NOOP']} already known, {o['SUPERSEDE']} superseded"
    )
    eng.close()


@app.command()
def diff(file: str, passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE")) -> None:
    """Show what differs between your strand and a .dna."""
    eng = _engine()
    try:
        d = eng.diff_strand(file, passphrase=passphrase)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    console.print(
        f"[green]+{d['added']}[/] in the .dna only, [red]-{d['removed']}[/] here only, "
        f"{d['common']} in common"
    )
    for c in d["added_samples"]:
        console.print(f"  [green]+[/] {c}")
    for c in d["removed_samples"]:
        console.print(f"  [red]-[/] {c}")
    eng.close()


@app.command()
def rollback(
    file: str, passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE")
) -> None:
    """Restore the active strand from a prior .dna export (replaces current)."""
    eng = _engine()
    try:
        eng.import_strand(file, passphrase=passphrase, replace=True)
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    console.print("[magenta]rolled back[/] the active strand to the imported .dna")
    eng.close()


@app.command()
def push(
    location: str,
    passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE"),
    name: str = typer.Option(None, help="strand name on the backend (default: active strand)"),
) -> None:
    """Push your encrypted memory to a shared location (a folder / synced drive)."""
    eng = _engine()
    try:
        res = eng.push(location, passphrase=passphrase, name=name)
    except (ValueError, RuntimeError, NotImplementedError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    console.print(
        f"[green]pushed[/] {res['pushed']} ({res['bytes']} bytes, encrypted) -> {res['location']}"
    )
    eng.close()


@app.command()
def pull(
    location: str,
    passphrase: str = typer.Option(None, help="or set HELIX_PASSPHRASE"),
    name: str = typer.Option(None, help="strand name on the backend (default: active strand)"),
    replace: bool = typer.Option(False, help="replace instead of merge"),
) -> None:
    """Pull a teammate's/your encrypted memory from a shared location and merge it in."""
    eng = _engine()
    try:
        res = eng.pull(location, passphrase=passphrase, name=name, merge=not replace)
    except (ValueError, RuntimeError, NotImplementedError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    if res.get("mode") == "merge":
        o = res["merged"]
        console.print(
            f"[green]pulled + merged[/]: {o['ADD']} added, {o['UPDATE']} updated, "
            f"{o['NOOP']} already known, {o['SUPERSEDE']} superseded"
        )
    else:
        console.print("[green]pulled[/] and replaced the active strand")
    eng.close()


@app.command()
def log(limit: int = typer.Option(20)) -> None:
    """Show how your memory evolved (git-style history)."""
    eng = _engine()
    rows = eng.history(limit)
    if not rows:
        console.print("[dim]no history yet[/]")
    else:
        table = Table(show_lines=False)
        table.add_column("#", justify="right", style="dim")
        table.add_column("op", style="cyan")
        table.add_column("memory")
        for r in rows:
            table.add_row(str(r["seq"]), r["op"], r["memory_id"] or "")
        console.print(table)
    eng.close()


if __name__ == "__main__":
    app()
