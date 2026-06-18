"""`helix connect <agent>` — write the MCP server config for each client (docs/MCP_INTEGRATION.md).

Different clients use different config dialects (`mcpServers` / `servers` / `context_servers` /
TOML), so we template per agent and merge idempotently. `home`/`cwd` are overridable for tests.
"""

from __future__ import annotations

import json
from pathlib import Path

SERVER_NAME = "helix"
BASE_ENTRY = {"command": "helix-mcp", "args": ["serve", "--stdio"]}

# agent -> (path_template, config_key, format, needs_type_stdio)
# (claude-desktop uses a per-OS path resolved in _claude_desktop_path)
AGENTS: dict[str, tuple[str, str, str, bool]] = {
    "claude-code": ("~/.claude.json", "mcpServers", "json", False),
    "claude-desktop": ("", "mcpServers", "json", False),
    "cursor": ("~/.cursor/mcp.json", "mcpServers", "json", False),
    "windsurf": ("~/.codeium/windsurf/mcp_config.json", "mcpServers", "json", False),
    "vscode": (".vscode/mcp.json", "servers", "json", True),
    "gemini": ("~/.gemini/settings.json", "mcpServers", "json", False),
    "zed": ("~/.config/zed/settings.json", "context_servers", "json", False),
    "codex": ("~/.codex/config.toml", "mcp_servers", "toml", False),
}


def supported() -> list[str]:
    return sorted(AGENTS)


def _resolve(template: str, home: Path, cwd: Path) -> Path:
    if template.startswith("~"):
        return home / template[2:]
    return cwd / template


def _claude_desktop_path(home: Path) -> Path:
    import sys

    if sys.platform == "win32":
        return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def entry_for(agent: str) -> dict:
    _, _, _, needs_type = AGENTS[agent]
    entry = dict(BASE_ENTRY)
    if needs_type:
        entry = {"type": "stdio", **entry}
    return entry


def _toml_snippet() -> str:
    return (
        f'\n[mcp_servers.{SERVER_NAME}]\n'
        f'command = "{BASE_ENTRY["command"]}"\n'
        f'args = ["serve", "--stdio"]\n'
    )


def connect(
    agent: str, *, home: Path | None = None, cwd: Path | None = None, dry_run: bool = False,
    path_override: str | None = None, key_override: str | None = None,
) -> dict:
    """Write (or preview) the MCP config for `agent`. `--path`/`--key` target any client.

    Returns details for display.
    """
    home = home or Path.home()
    cwd = cwd or Path.cwd()
    needs_type = False
    if agent == "claude-desktop":
        path, key, fmt = _claude_desktop_path(home), "mcpServers", "json"
    elif agent in AGENTS:
        template, key, fmt, needs_type = AGENTS[agent]
        path = _resolve(template, home, cwd)
    elif path_override:
        key, fmt = "mcpServers", "json"
        path = Path(path_override)
    else:
        raise ValueError(
            f"unknown agent '{agent}'. Supported: {', '.join(supported())} (or pass --path)"
        )
    if path_override:
        p = Path(path_override)
        path = p if p.is_absolute() else cwd / p
    if key_override:
        key = key_override
    entry = {"type": "stdio", **BASE_ENTRY} if needs_type else dict(BASE_ENTRY)

    if fmt == "toml":
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        already = f"[mcp_servers.{SERVER_NAME}]" in existing
        new_text = existing if already else existing + _toml_snippet()
        preview = _toml_snippet().strip()
    else:
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError:
                data = {}
        data.setdefault(key, {})[SERVER_NAME] = entry
        new_text = json.dumps(data, indent=2)
        preview = json.dumps({key: {SERVER_NAME: entry}}, indent=2)

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")

    return {"agent": agent, "path": str(path), "key": key, "format": fmt,
            "preview": preview, "written": not dry_run}
