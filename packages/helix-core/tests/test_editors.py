"""Structural guards for the editor + browser surfaces (v2 plan §5.4/§5.5).

Keeps the scaffolds honest (valid JSON, expected commands/files) so they can't silently rot.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_vscode_extension_manifest_is_valid():
    pkg = json.loads((ROOT / "editors/vscode/package.json").read_text(encoding="utf-8"))
    assert pkg["main"] == "./out/extension.js"
    cmds = {c["command"] for c in pkg["contributes"]["commands"]}
    assert {
        "helix.remember",
        "helix.search",
        "helix.about",
        "helix.dashboard",
        "helix.connectMcp",
    } <= cmds
    assert (ROOT / "editors/vscode/src/extension.ts").exists()
    assert (ROOT / "editors/vscode/tsconfig.json").exists()


def test_browser_extension_manifest_is_valid():
    m = json.loads((ROOT / "apps/browser-extension/manifest.json").read_text(encoding="utf-8"))
    assert m["manifest_version"] == 3
    matches = m["content_scripts"][0]["matches"]
    assert any("chatgpt" in x for x in matches) and any("claude" in x for x in matches)
    assert m["background"]["service_worker"] == "background.js"
    # only loopback host permissions (local-first)
    assert all("127.0.0.1" in h or "localhost" in h for h in m["host_permissions"])
    for f in ("background.js", "content.js", "popup.html", "popup.js"):
        assert (ROOT / "apps/browser-extension" / f).exists()
