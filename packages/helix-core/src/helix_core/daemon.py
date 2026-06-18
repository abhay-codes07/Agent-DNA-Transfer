"""Local dashboard daemon (Phase 5, ADR-033).

A dependency-free, localhost-only HTTP server (stdlib `http.server`) exposing the engine as a
small JSON API and serving a self-contained, build-free dashboard so a user can browse, search,
add, relate, and forget memories. Single-threaded (serial) — right for a single-user local UI.
Binds to 127.0.0.1 only.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .engine import Engine
from .serialize import hit_to_dict, memory_to_dict


def _make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # --- helpers ---
        def _send(self, body: bytes, status: int = 200, ctype: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status: int = 200) -> None:
            self._send(json.dumps(obj).encode("utf-8"), status)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return {}

        def log_message(self, *args) -> None:  # quiet
            pass

        # --- routing ---
        def do_GET(self) -> None:
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path in ("/", "/index.html"):
                self._send(DASHBOARD_HTML.encode("utf-8"), ctype="text/html; charset=utf-8")
            elif u.path == "/api/health":
                self._json({"ok": True, "version": __version__})
            elif u.path == "/api/stats":
                self._json(engine.stats())
            elif u.path == "/api/memories":
                mems = engine.list_memories(scope=q.get("scope") or None,
                                            limit=int(q.get("limit", 200)))
                self._json({"memories": [memory_to_dict(m) for m in mems]})
            elif u.path == "/api/search":
                hits = engine.recall(q.get("q", ""), scope=q.get("scope") or None,
                                     k=int(q.get("k", 10)))
                self._json({"results": [hit_to_dict(h) for h in hits]})
            elif u.path == "/api/context":
                self._json({"context": engine.context(scope=q.get("scope") or None,
                                                       query=q.get("q") or None)})
            elif u.path == "/api/graph":
                self._json(_graph(engine))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            u = urlparse(self.path)
            body = self._body()
            if u.path == "/api/remember":
                res = engine.remember(str(body.get("content", "")),
                                      scope=str(body.get("scope") or "global"), source="dashboard")
                self._json({"results": [{"op": r.op, "id": r.memory_id} for r in res]})
            elif u.path == "/api/forget":
                self._json({"forgot": engine.forget(str(body.get("id", "")))})
            elif u.path == "/api/relate":
                eid = engine.relate(str(body["from"]), str(body["to"]),
                                    str(body.get("relation", "related_to")))
                self._json({"edge": eid})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def _graph(engine: Engine) -> dict:
    nodes = []
    for m in engine.store.all_memories(limit=2000):
        nodes.append({"id": m.id, "type": m.type.value, "content": m.content,
                      "scope": m.scope, "hub": bool(m.attributes.get("_hub"))})
    edges = [
        {"from": r["from_id"], "to": r["to_id"], "relation": r["relation"]}
        for r in engine.store.conn.execute("SELECT from_id,to_id,relation FROM edges")
    ]
    return {"nodes": nodes, "edges": edges}


def build_server(host: str = "127.0.0.1", port: int = 8787, engine: Engine | None = None):
    engine = engine or Engine()
    return HTTPServer((host, port), _make_handler(engine))


def serve(host: str = "127.0.0.1", port: int = 8787, *, engine: Engine | None = None,
          open_browser: bool = True) -> None:
    httpd = build_server(host, port, engine)
    url = f"http://{host}:{port}"
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Helix — your memory</title>
<style>
:root{--bg:#0b0e14;--panel:#141925;--line:#232a3a;--fg:#e6e9ef;--dim:#8b95a7;--accent:#5b8cff;--green:#4ec9a3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto}
header{padding:16px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px}
header h1{font-size:18px;margin:0}header .tag{color:var(--dim);font-size:12px}
.wrap{max-width:980px;margin:0 auto;padding:20px}
.tabs{display:flex;gap:6px;margin-bottom:16px}
.tabs button{background:var(--panel);color:var(--fg);border:1px solid var(--line);padding:7px 14px;border-radius:8px;cursor:pointer}
.tabs button.active{border-color:var(--accent);color:var(--accent)}
.row{display:flex;gap:8px;margin-bottom:14px}
input,select{background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px;flex:1}
button.go{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:9px 16px;cursor:pointer}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:9px}
.card .meta{color:var(--dim);font-size:12px;display:flex;gap:10px;margin-top:5px;align-items:center}
.pill{border:1px solid var(--line);border-radius:999px;padding:1px 8px;font-size:11px}
.score{color:var(--green);font-variant-numeric:tabular-nums}
.x{margin-left:auto;color:var(--dim);cursor:pointer;border:1px solid var(--line);border-radius:6px;padding:1px 8px}
.x:hover{color:#ff6b6b;border-color:#ff6b6b}
.stat{display:flex;justify-content:space-between;border-bottom:1px solid var(--line);padding:7px 0}
.muted{color:var(--dim)}.hidden{display:none}.edge{color:var(--dim);font-size:12px}
</style></head><body>
<header><h1>🧬 Helix</h1><span class="tag">your portable memory — local & private</span></header>
<div class="wrap">
  <div class="tabs">
    <button data-t="memories" class="active">Memories</button>
    <button data-t="graph">Graph</button>
    <button data-t="stats">Stats</button>
  </div>

  <section id="memories">
    <div class="row"><input id="q" placeholder="Search your memory… (semantic + keyword)"><button class="go" onclick="search()">Search</button></div>
    <div class="row"><input id="newc" placeholder="Teach Helix a fact…"><select id="news"><option value="global">global</option></select><button class="go" onclick="add()">Add</button></div>
    <div id="list"></div>
  </section>

  <section id="graph" class="hidden"><div id="graphbox"></div></section>
  <section id="stats" class="hidden"><div id="statbox"></div></section>
</div>
<script>
const api=(p,o)=>fetch(p,o).then(r=>r.json());
const esc=s=>(s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function tab(name){for(const s of ['memories','graph','stats'])document.getElementById(s).classList.toggle('hidden',s!==name);
  document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.t===name));
  if(name==='graph')loadGraph(); if(name==='stats')loadStats(); if(name==='memories')loadAll();}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>tab(b.dataset.t));
function card(m,score){const sc=score!==undefined?`<span class="score">${score.toFixed(2)}</span>`:'';
  return `<div class="card"><div>${esc(m.content)}</div><div class="meta">${sc}<span class="pill">${m.type}</span><span class="pill">${esc(m.scope)}</span><span class="muted">${(m.origin||'')}</span><span class="x" onclick="forget('${m.id}')">forget</span></div></div>`;}
async function loadAll(){const d=await api('/api/memories');document.getElementById('list').innerHTML=d.memories.map(m=>card(m)).join('')||'<p class="muted">No memories yet — add one above.</p>';}
async function search(){const q=document.getElementById('q').value;if(!q)return loadAll();const d=await api('/api/search?q='+encodeURIComponent(q));
  document.getElementById('list').innerHTML=d.results.map(r=>card(r,r.score)).join('')||'<p class="muted">No matches.</p>';}
async function add(){const c=document.getElementById('newc').value.trim();if(!c)return;const s=document.getElementById('news').value;
  await api('/api/remember',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:c,scope:s})});
  document.getElementById('newc').value='';loadAll();refreshScopes();}
async function forget(id){await api('/api/forget',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});search();}
async function loadGraph(){const g=await api('/api/graph');const byId={};g.nodes.forEach(n=>byId[n.id]=n);
  const edges=g.edges.map(e=>`<div class="edge">${esc((byId[e.from]||{}).content||e.from)} —<b>${e.relation}</b>→ ${esc((byId[e.to]||{}).content||e.to)}</div>`).join('');
  const nodes=g.nodes.filter(n=>!n.hub).map(n=>card(n)).join('');
  document.getElementById('graphbox').innerHTML=`<h3>Relations</h3>${edges||'<p class="muted">No links yet (use relate).</p>'}<h3>Nodes</h3>${nodes}`;}
async function loadStats(){const s=await api('/api/stats');
  document.getElementById('statbox').innerHTML=Object.entries(s).map(([k,v])=>`<div class="stat"><span class="muted">${k}</span><span>${esc(String(v))}</span></div>`).join('');}
async function refreshScopes(){const d=await api('/api/memories');const set=new Set(['global']);d.memories.forEach(m=>set.add(m.scope));
  const sel=document.getElementById('news');const cur=sel.value;sel.innerHTML=[...set].map(s=>`<option ${s===cur?'selected':''}>${esc(s)}</option>`).join('');}
loadAll();refreshScopes();
</script></body></html>"""
