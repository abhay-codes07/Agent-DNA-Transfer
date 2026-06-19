# Helix for VS Code

Browse, capture, and recall your AI's memory from inside the editor — local-first, $0.

## Commands

| Command | Default key | What it does |
|---|---|---|
| **Helix: Remember selection** | `ctrl/cmd+alt+m` | Save the selected text (or a prompt) as a fact, scoped to the workspace |
| **Helix: Search memory** | `ctrl/cmd+alt+k` | Hybrid search across your memory |
| **Helix: What do I know about…?** | — | Ask the copilot; sourced facts in an output channel |
| **Helix: Open dashboard** | — | Open the local dashboard in your browser |
| **Helix: Configure MCP for Copilot** | — | Write `.vscode/mcp.json` so Copilot agent mode uses Helix over MCP |

A status-bar item (`🧬 Helix`) opens the dashboard.

## Setup

1. Install Helix and start the local server: `pipx install helix-dna` then `helix dashboard`
   (the extension talks only to `http://127.0.0.1:8787` — set `helix.endpoint` to change it).
2. For Copilot agent mode, run **Helix: Configure MCP for Copilot** (needs `helix-mcp` on PATH).

## Develop

```bash
npm install
npm run compile   # or: npm run watch
# press F5 in VS Code to launch an Extension Development Host
```

Local-first by design: the extension never makes a network call beyond your own loopback daemon.
