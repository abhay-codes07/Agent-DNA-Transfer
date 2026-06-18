"""Phase 2 tests: the MCP toolset, FastMCP server registration, and connect config-writers.

Offline; uses the dependency-free engine. The server test exercises the real `mcp` SDK.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from helix_core.config import Config
from helix_core.engine import Engine
from helix_mcp.connect import connect, entry_for, supported
from helix_mcp.server import TOOLS, build_server
from helix_mcp.toolset import HelixToolset


def _toolset(tmp_path) -> HelixToolset:
    return HelixToolset(Engine(Config(home=tmp_path)))


# --- toolset ---

def test_toolset_write_search_get(tmp_path):
    t = _toolset(tmp_path)
    w = t.write("We use Postgres for the billing service.", scope="project:billing")
    assert w["ok"] and w["results"][0]["op"] == "ADD"
    mid = w["results"][0]["id"]

    s = t.search("billing database", scope="project:billing")
    assert s["ok"] and s["count"] >= 1
    # concise rows expose only the small surface
    assert all(set(r) <= {"id", "type", "content", "scope", "score"} for r in s["results"])

    assert t.get(mid)["ok"] is True
    assert t.get("does-not-exist")["ok"] is False


def test_toolset_detailed_and_budget(tmp_path):
    t = _toolset(tmp_path)
    t.write("Alpha note about caching.", scope="project:p")
    t.write("Beta note about caching layers.", scope="project:p")
    detailed = t.search("caching", scope="project:p", response_format="detailed")
    assert "confidence" in detailed["results"][0]
    trimmed = t.search("caching", scope="project:p", budget_tokens=1)
    assert trimmed["count"] <= detailed["count"]


def test_toolset_relate_and_forget(tmp_path):
    t = _toolset(tmp_path)
    a = t.write("Service A uses Redis.", scope="project:p")["results"][0]["id"]
    b = t.write("Service B also uses Redis.", scope="project:p")["results"][0]["id"]
    assert t.relate(a, b, "related_to")["ok"] is True
    assert t.relate(a, "missing-id")["ok"] is False
    f = t.forget(a)
    assert f["ok"] and a in f["forgot"]


# --- server (real mcp SDK) ---

def test_server_registers_the_tool_surface(tmp_path):
    server = build_server(_toolset(tmp_path))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    for expected in TOOLS:
        assert expected in names


def test_server_call_tool_round_trip(tmp_path):
    server = build_server(_toolset(tmp_path))
    asyncio.run(server.call_tool("memory_write",
                                 {"content": "We deploy on Fridays.", "scope": "project:p"}))
    result = asyncio.run(server.call_tool("memory_search",
                                          {"query": "when do we deploy", "scope": "project:p"}))
    # FastMCP returns content; find the JSON text payload and verify it parsed.
    blob = _extract_text(result)
    payload = json.loads(blob)
    assert payload["ok"] and payload["count"] >= 1


def test_server_exposes_resources(tmp_path):
    server = build_server(_toolset(tmp_path))
    resources = asyncio.run(server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert "helix://strand/manifest" in uris
    assert "helix://graph" in uris


def _extract_text(result) -> str:
    # FastMCP.call_tool returns either a list[Content] or (content, structured) across versions.
    content = result[0] if isinstance(result, tuple) else result
    item = content[0]
    return getattr(item, "text", None) or json.dumps(item)


# --- connect ---

def test_connect_writes_json_dialects(tmp_path):
    for agent, key in [("cursor", "mcpServers"), ("vscode", "servers"), ("zed", "context_servers")]:
        res = connect(agent, home=tmp_path, cwd=tmp_path)
        data = json.loads(Path(res["path"]).read_text(encoding="utf-8"))
        assert "helix" in data[key]
        assert data[key]["helix"]["command"] == "helix-mcp"
    assert entry_for("vscode").get("type") == "stdio"  # VS Code needs the stdio type


def test_connect_is_idempotent(tmp_path):
    connect("cursor", home=tmp_path, cwd=tmp_path)
    connect("cursor", home=tmp_path, cwd=tmp_path)
    data = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert list(data["mcpServers"]) == ["helix"]


def test_connect_codex_toml(tmp_path):
    res = connect("codex", home=tmp_path, cwd=tmp_path)
    connect("codex", home=tmp_path, cwd=tmp_path)  # again -> must not duplicate
    text = Path(res["path"]).read_text(encoding="utf-8")
    assert text.count("[mcp_servers.helix]") == 1


def test_connect_dry_run_writes_nothing(tmp_path):
    res = connect("cursor", home=tmp_path, cwd=tmp_path, dry_run=True)
    assert not Path(res["path"]).exists()
    assert "helix" in res["preview"]


def test_connect_unknown_agent(tmp_path):
    with pytest.raises(ValueError):
        connect("not-an-agent", home=tmp_path, cwd=tmp_path)
    assert "cursor" in supported()


def test_connect_claude_desktop_per_os(tmp_path):
    res = connect("claude-desktop", home=tmp_path, cwd=tmp_path)
    data = json.loads(Path(res["path"]).read_text(encoding="utf-8"))
    assert data["mcpServers"]["helix"]["command"] == "helix-mcp"
    assert "claude-desktop" in supported()


def test_connect_custom_path_and_key_override(tmp_path):
    custom = tmp_path / "nested" / "any_client.json"
    res = connect("some-mcp-client", home=tmp_path, cwd=tmp_path,
                  path_override=str(custom), key_override="servers")
    data = json.loads(custom.read_text(encoding="utf-8"))
    assert "helix" in data["servers"]
    assert res["path"] == str(custom)
