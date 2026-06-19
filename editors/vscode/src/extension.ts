/**
 * Helix VS Code extension (v2 plan §5.4).
 *
 * Thin client over the local Helix dashboard daemon (the same JSON API the web dashboard uses) —
 * capture a selection into memory, search/recall, ask the copilot, and open the dashboard, all
 * without leaving the editor. Local-first: it only ever talks to 127.0.0.1. Start the server with
 * `helix dashboard`. A separate command wires Helix into Copilot agent mode over MCP.
 */

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

function endpoint(): string {
  return vscode.workspace.getConfiguration("helix").get<string>("endpoint", "http://127.0.0.1:8787");
}

async function api(p: string, init?: RequestInit): Promise<any> {
  const res = await fetch(endpoint() + p, init);
  if (!res.ok) throw new Error(`Helix ${p} -> ${res.status}`);
  return res.json();
}

function scope(): string {
  return vscode.workspace.name ? "project:" + vscode.workspace.name : "global";
}

function hint(e: unknown): void {
  const msg = e instanceof Error ? e.message : String(e);
  vscode.window
    .showWarningMessage(
      "Helix isn't reachable — run `helix dashboard` to start the local server.",
      "Copy command"
    )
    .then((c) => {
      if (c) vscode.env.clipboard.writeText("helix dashboard");
    });
  console.error("[helix]", msg);
}

async function remember(): Promise<void> {
  const ed = vscode.window.activeTextEditor;
  let text =
    ed && !ed.selection.isEmpty
      ? ed.document.getText(ed.selection)
      : await vscode.window.showInputBox({ prompt: "Teach Helix a fact" });
  if (!text) return;
  try {
    const r = await api("/api/remember", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: text, scope: scope() }),
    });
    vscode.window.showInformationMessage(`🧬 Helix remembered it (${r.results?.[0]?.op ?? "stored"}).`);
  } catch (e) {
    hint(e);
  }
}

async function search(): Promise<void> {
  const q = await vscode.window.showInputBox({ prompt: "Search your memory (semantic + keyword)" });
  if (!q) return;
  try {
    const d = await api("/api/search?q=" + encodeURIComponent(q));
    const items = (d.results || []).map((r: any) => ({
      label: r.content,
      description: `${r.type} · ${Number(r.score).toFixed(2)}`,
    }));
    await vscode.window.showQuickPick(items, { placeHolder: items.length ? q : "no matches" });
  } catch (e) {
    hint(e);
  }
}

async function about(): Promise<void> {
  const q = await vscode.window.showInputBox({ prompt: "What do I know about…?" });
  if (!q) return;
  try {
    const d = await api("/api/about?q=" + encodeURIComponent(q));
    const ch = vscode.window.createOutputChannel("Helix");
    ch.clear();
    ch.appendLine(`What Helix knows about "${q}":\n`);
    (d.facts || []).forEach((f: any, i: number) =>
      ch.appendLine(`[${i + 1}] ${f.content}   (${f.type}, via ${f.source || "?"})`)
    );
    if (!d.facts?.length) ch.appendLine("Nothing yet — capture some facts first.");
    ch.show();
  } catch (e) {
    hint(e);
  }
}

function openDashboard(): void {
  vscode.env.openExternal(vscode.Uri.parse(endpoint()));
}

/** Write .vscode/mcp.json so Copilot agent mode can use Helix's MCP server. */
async function connectMcp(): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    vscode.window.showWarningMessage("Open a folder first.");
    return;
  }
  const dir = path.join(folder.uri.fsPath, ".vscode");
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, "mcp.json");
  let cfg: any = {};
  try {
    cfg = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    cfg = {};
  }
  cfg.servers = cfg.servers || {};
  cfg.servers.helix = { command: "helix-mcp", args: [] };
  fs.writeFileSync(file, JSON.stringify(cfg, null, 2));
  vscode.window.showInformationMessage("Wired Helix into Copilot over MCP (.vscode/mcp.json). Reload to apply.");
}

export function activate(ctx: vscode.ExtensionContext): void {
  const reg = (id: string, fn: () => void) =>
    ctx.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg("helix.remember", remember);
  reg("helix.search", search);
  reg("helix.about", about);
  reg("helix.dashboard", openDashboard);
  reg("helix.connectMcp", connectMcp);

  const sb = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  sb.text = "$(circuit-board) Helix";
  sb.tooltip = "Open Helix memory";
  sb.command = "helix.dashboard";
  sb.show();
  ctx.subscriptions.push(sb);
}

export function deactivate(): void {}
