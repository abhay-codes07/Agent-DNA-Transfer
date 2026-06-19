"""Local dashboard daemon (Phase 5 / v2 UI, ADR-033, docs/DASHBOARD_DESIGN.md).

A dependency-free, localhost-only HTTP server (stdlib `http.server`) exposing the engine as a
small JSON API and serving a self-contained, build-free dashboard — no bundler, no node_modules,
no CDN, no runtime network calls. The browser app is hand-rolled vanilla JS + CSS (research-backed
design system); the knowledge graph is a hand-rolled canvas force layout (no graph library).

Security: binds to 127.0.0.1 only AND validates Host + Origin on every request (403 otherwise) to
defend against DNS-rebinding — loopback alone is not enough for a local server.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .engine import Engine
from .serialize import hit_to_dict, memory_detail_dict, memory_to_dict

_LOOPBACK = {"127.0.0.1", "localhost", "::1", ""}


def _card_dict(m) -> dict:
    """Memory dict enriched with the trust flags the UI surfaces (stale / conflict / signed)."""
    d = memory_to_dict(m)
    a = m.attributes
    d["stale"] = bool(a.get("_stale_suspected"))
    d["conflict"] = bool(a.get("_conflict"))
    d["signed"] = bool(a.get("_sig"))
    d["reinforced"] = int(a.get("_reinforced", 0))
    return d


def _make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body: bytes, status: int = 200, ctype: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
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

        def _allowed(self) -> bool:
            """DNS-rebinding defense: Host must be loopback and any Origin must be loopback."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in _LOOPBACK:
                return False
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in _LOOPBACK:
                return False
            return True

        def log_message(self, *args) -> None:  # quiet
            pass

        # --- routing ---
        def do_GET(self) -> None:
            if not self._allowed():
                self._json({"error": "forbidden"}, 403)
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            scope = q.get("scope") or None
            if u.path in ("/", "/index.html"):
                self._send(DASHBOARD_HTML.encode("utf-8"), ctype="text/html; charset=utf-8")
            elif u.path == "/api/health":
                self._json({"ok": True, "version": __version__})
            elif u.path == "/api/stats":
                self._json(engine.stats())
            elif u.path == "/api/memories":
                mems = engine.list_memories(scope=scope, limit=int(q.get("limit", 500)))
                self._json({"memories": [_card_dict(m) for m in mems]})
            elif u.path == "/api/search":
                hits = engine.recall(q.get("q", ""), scope=scope, k=int(q.get("k", 12)))
                self._json({"results": [hit_to_dict(h) for h in hits]})
            elif u.path == "/api/about":
                self._json(engine.about(q.get("q", ""), k=int(q.get("k", 8))))
            elif u.path == "/api/proactive":
                self._json({"facts": engine.proactive(q.get("q", ""), scope=scope)})
            elif u.path == "/api/conflicts":
                self._json({"conflicts": engine.conflicts()})
            elif u.path == "/api/review":
                self._json({"queue": engine.review_queue()})
            elif u.path == "/api/review-incoming":
                self._json({"pending": engine.review_incoming()})
            elif u.path == "/api/analytics":
                self._json(engine.analytics())
            elif u.path == "/api/savings":
                self._json(engine.savings())
            elif u.path == "/api/themes":
                self._json({"themes": engine.themes(scope=scope)})
            elif u.path == "/api/changes":
                self._json({"changes": engine.changes(scope=scope)})
            elif u.path == "/api/asof":
                from datetime import datetime as _dt
                from datetime import timezone as _tz

                try:
                    when = _dt.fromisoformat(q.get("at", ""))
                except ValueError:
                    self._json({"error": "bad date"}, 400)
                    return
                if when.tzinfo is None:  # the UI sends a naive UTC stamp
                    when = when.replace(tzinfo=_tz.utc)
                mems = engine.as_of(when)
                self._json({"count": len(mems), "facts": [memory_to_dict(m) for m in mems]})
            elif u.path == "/api/audit":
                self._json({"intact": engine.verify_audit(), "entries": engine.audit_log(80)})
            elif u.path == "/api/graph":
                self._json(_graph(engine, scope))
            elif u.path == "/api/memory":
                mem = engine.get_memory(q.get("id", ""))
                self._json(
                    memory_detail_dict(mem) if mem else {"error": "not found"}, 200 if mem else 404
                )
            elif u.path == "/api/history":
                self._json({"history": engine.history(int(q.get("limit", 80)))})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:
            if not self._allowed():
                self._json({"error": "forbidden"}, 403)
                return
            u = urlparse(self.path)
            b = self._body()
            if u.path == "/api/remember":
                res = engine.remember(
                    str(b.get("content", "")),
                    scope=str(b.get("scope") or "global"),
                    source="dashboard",
                )
                self._json({"results": [{"op": r.op, "id": r.memory_id} for r in res]})
            elif u.path == "/api/seed":
                self._json(engine.seed_demo())
            elif u.path == "/api/forget":
                self._json({"forgot": engine.forget(str(b.get("id", "")))})
            elif u.path == "/api/erase":
                self._json(engine.erase(str(b.get("id", ""))))
            elif u.path == "/api/relate":
                eid = engine.relate(
                    str(b["from"]), str(b["to"]), str(b.get("relation", "related_to"))
                )
                self._json({"edge": eid})
            elif u.path == "/api/edit":
                mem = engine.edit_memory(
                    str(b.get("id", "")),
                    content=b.get("content"),
                    scope=b.get("scope"),
                    type=b.get("type"),
                    importance=b.get("importance"),
                )
                self._json(
                    memory_detail_dict(mem) if mem else {"error": "not found"}, 200 if mem else 404
                )
            elif u.path == "/api/resolve":
                mem = engine.resolve_stale(str(b.get("id", "")), keep=bool(b.get("keep", True)))
                self._json({"ok": mem is not None})
            elif u.path == "/api/approve":
                mem = engine.approve_incoming(str(b.get("id", "")))
                self._json({"ok": mem is not None})
            elif u.path == "/api/reject":
                self._json({"ok": engine.reject_incoming(str(b.get("id", "")))})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def _graph(engine: Engine, scope: str | None = None) -> dict:
    """Nodes + edges for the canvas force graph, enriched for sizing (recall) and color (type)."""
    nodes = []
    for m in engine.store.all_memories(scope=scope, limit=1500):
        if m.attributes.get("_hub"):
            continue
        nodes.append(
            {
                "id": m.id,
                "type": m.type.value,
                "content": m.content,
                "scope": m.scope,
                "reinforced": int(m.attributes.get("_reinforced", 0)),
                "confidence": round(m.confidence, 2),
            }
        )
    present = {n["id"] for n in nodes}
    edges = [
        {"from": e.from_id, "to": e.to_id, "relation": e.relation}
        for e in engine.store.all_edges()
        if e.from_id in present and e.to_id in present
    ]
    return {"nodes": nodes, "edges": edges}


def build_server(host: str = "127.0.0.1", port: int = 8787, engine: Engine | None = None):
    engine = engine or Engine()
    httpd = ThreadingHTTPServer((host, port), _make_handler(engine))
    httpd.daemon_threads = True
    return httpd


def serve(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    engine: Engine | None = None,
    open_browser: bool = True,
) -> None:
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


# The dashboard is a single self-contained document (no build, no CDN). Raw string so JS regex /
# escape sequences are served verbatim. Design tokens + views per docs/DASHBOARD_DESIGN.md.
DASHBOARD_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Helix — your memory</title>
<style>
:root{
  --bg:#0b0e14;--surface:#141925;--raised:#1b2230;--overlay:#222a3a;
  --line:rgba(255,255,255,.08);--line-strong:rgba(255,255,255,.14);
  --fg:#e6e9ef;--fg-body:#cbd5e1;--dim:#8b95a7;
  --accent:#5b8cff;--accent2:#7b5bff;--green:#4ec9a3;
  --grad:linear-gradient(120deg,#5b8cff,#7b5bff);--grad-teal:linear-gradient(120deg,#4ec9a3,#3ba6ff);
  --success:#3fb950;--warning:#d29922;--danger:#f85149;--info:#58a6ff;
  --r-sm:6px;--r-md:8px;--r-lg:12px;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35);
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif,"Apple Color Emoji";
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  --ease:cubic-bezier(0,0,.2,1);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 var(--sans);-webkit-font-smoothing:antialiased}
.num,table,.metric,.mono{font-variant-numeric:tabular-nums}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums slashed-zero}
button{font:inherit;cursor:pointer}
a{color:var(--accent);text-decoration:none}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--overlay);border-radius:9px;border:2px solid var(--bg)}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}

/* layout */
.app{display:grid;grid-template-columns:240px 1fr;height:100vh}
.side{background:var(--surface);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:14px 12px}
.brand{display:flex;align-items:center;gap:10px;padding:6px 8px 16px}
.brand .mark{width:26px;height:26px}
.brand b{font-size:16px;letter-spacing:-.2px}
.brand span{color:var(--dim);font-size:11px;display:block;margin-top:-2px}
.nav{display:flex;flex-direction:column;gap:2px;flex:1}
.nav button{display:flex;align-items:center;gap:10px;background:none;border:none;color:var(--fg-body);
  padding:8px 10px;border-radius:var(--r-md);text-align:left;width:100%;transition:background .15s var(--ease)}
.nav button:hover{background:var(--raised)}
.nav button.on{background:var(--raised);color:#fff}
.nav button.on .ic{color:var(--accent)}
.nav .ic{width:17px;height:17px;color:var(--dim);flex:none}
.nav .badge{margin-left:auto;background:var(--warning);color:#1a1205;border-radius:9px;font-size:11px;
  padding:0 6px;font-weight:600;min-width:18px;text-align:center}
.side .foot{border-top:1px solid var(--line);padding-top:12px;margin-top:8px}
.side .meter{font-size:12px;color:var(--dim)}
.side .meter b{display:block;color:var(--green);font-size:20px;font-variant-numeric:tabular-nums}
.kbd{font:11px var(--mono);background:var(--overlay);border:1px solid var(--line);border-radius:4px;padding:1px 5px;color:var(--dim)}

.main{overflow:auto;padding:26px 30px;max-width:1280px}
.head{display:flex;align-items:center;margin-bottom:20px;gap:12px}
.head h2{margin:0;font-size:20px;font-weight:600;letter-spacing:-.3px}
.head .sub{color:var(--dim);font-size:13px}
.head .sp{flex:1}

/* controls */
.row{display:flex;gap:8px;margin-bottom:16px}
input,select,textarea{background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:var(--r-md);
  padding:9px 12px;font:inherit;outline:none;transition:border-color .15s var(--ease)}
input:focus,select:focus,textarea:focus{border-color:var(--accent)}
input.grow{flex:1}
.btn{background:var(--raised);color:var(--fg);border:1px solid var(--line);border-radius:var(--r-md);padding:9px 14px}
.btn:hover{border-color:var(--line-strong)}
.btn.pri{background:var(--grad);color:#fff;border:none}
.btn.pri:hover{filter:brightness(1.08)}
.btn.sm{padding:4px 9px;font-size:12px}
.btn.danger:hover{border-color:var(--danger);color:var(--danger)}

/* cards */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:14px 16px;margin-bottom:10px;
  transition:border-color .15s var(--ease),transform .15s var(--ease)}
.card:hover{border-color:var(--line-strong)}
.card .c{font-size:14px;color:var(--fg)}
.card .meta{display:flex;align-items:center;gap:8px;margin-top:9px;flex-wrap:wrap}
.pill{border:1px solid var(--line);border-radius:999px;padding:1px 9px;font-size:11px;color:var(--dim)}
.pill.t{color:var(--accent);border-color:rgba(91,140,255,.3)}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.flag{font-size:11px;padding:1px 8px;border-radius:999px;display:inline-flex;align-items:center;gap:4px}
.flag.stale{background:rgba(210,153,34,.14);color:var(--warning)}
.flag.conflict{background:rgba(248,81,73,.14);color:var(--danger)}
.flag.signed{background:rgba(78,201,163,.14);color:var(--green)}
.score{color:var(--green);font-variant-numeric:tabular-nums;font-size:12px}
.act{margin-left:auto;display:flex;gap:6px}
.act .x{color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font-size:12px;background:none}
.act .x:hover{color:var(--fg);border-color:var(--line-strong)}
.act .x.del:hover{color:var(--danger);border-color:var(--danger)}
.prov{margin-top:10px;border-top:1px dashed var(--line);padding-top:9px;color:var(--dim);font-size:12px}
.muted{color:var(--dim)}.center{text-align:center}
.empty{text-align:center;color:var(--dim);padding:60px 20px}
.empty .g{opacity:.5;margin-bottom:12px}
.confbar{height:4px;border-radius:3px;background:var(--overlay);overflow:hidden;width:54px;display:inline-block;vertical-align:middle}
.confbar i{display:block;height:100%;background:var(--grad-teal)}

/* stats / insights */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:22px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 18px}
.stat .k{color:var(--dim);font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.stat .v{font-size:30px;font-weight:600;margin-top:6px;font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.stat .v.g{background:var(--grad-teal);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.section{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:18px;margin-bottom:16px}
.section h3{margin:0 0 14px;font-size:14px;font-weight:600}
.heat{display:grid;grid-template-rows:repeat(7,11px);grid-auto-flow:column;gap:3px}
.heat i{width:11px;height:11px;border-radius:2px;background:var(--overlay)}
.heat i.l1{background:rgba(78,201,163,.3)}.heat i.l2{background:rgba(78,201,163,.5)}
.heat i.l3{background:rgba(78,201,163,.75)}.heat i.l4{background:var(--green)}
.bar{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px}
.bar .lbl{width:90px;color:var(--fg-body)}.bar .track{flex:1;height:8px;background:var(--overlay);border-radius:5px;overflow:hidden}
.bar .track i{display:block;height:100%;background:var(--grad)}
.bar .n{width:34px;text-align:right;color:var(--dim);font-variant-numeric:tabular-nums}

/* chat */
.chat{display:flex;flex-direction:column;height:calc(100vh - 120px)}
.stream{flex:1;overflow:auto;padding-right:6px}
.msg{margin-bottom:16px;max-width:760px}
.msg.you{margin-left:auto;background:var(--raised);border:1px solid var(--line);border-radius:12px 12px 4px 12px;padding:9px 13px;width:fit-content}
.msg.bot .ans{color:var(--fg-body);margin-bottom:8px}
.srcs{display:flex;flex-direction:column;gap:7px}
.suggest{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.suggest button{background:var(--surface);border:1px solid var(--line);border-radius:999px;padding:7px 13px;color:var(--fg-body)}
.suggest button:hover{border-color:var(--accent);color:var(--accent)}

/* conflict */
.versus{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:stretch;margin-bottom:14px}
.versus .vs{align-self:center;color:var(--dim);font-size:12px}
.side-pick{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:14px}

/* graph */
#gcanvas{width:100%;height:calc(100vh - 150px);background:radial-gradient(circle at 50% 40%,#0e1320,#0b0e14);
  border:1px solid var(--line);border-radius:var(--r-lg);cursor:grab;display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--dim)}
.gtip{position:fixed;pointer-events:none;background:var(--overlay);border:1px solid var(--line-strong);border-radius:8px;
  padding:7px 10px;font-size:12px;max-width:280px;box-shadow:var(--shadow);z-index:30;display:none}

/* cmd-k */
.scrim{position:fixed;inset:0;background:rgba(5,7,12,.6);display:none;align-items:flex-start;justify-content:center;z-index:50}
.scrim.show{display:flex}
.palette{margin-top:12vh;width:560px;max-width:92vw;background:var(--overlay);border:1px solid var(--line-strong);
  border-radius:var(--r-lg);box-shadow:var(--shadow);overflow:hidden}
.palette input{width:100%;border:none;border-bottom:1px solid var(--line);border-radius:0;background:none;padding:14px 16px;font-size:15px}
.palette .res{max-height:340px;overflow:auto;padding:6px}
.palette .it{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:var(--r-md);color:var(--fg-body)}
.palette .it.sel{background:var(--raised);color:#fff}
.palette .it .k{margin-left:auto}
.palette .it .ic{width:15px;height:15px;color:var(--dim)}

/* toast + modal */
.toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:var(--overlay);border:1px solid var(--line-strong);
  border-radius:var(--r-md);padding:10px 14px;box-shadow:var(--shadow);display:flex;gap:14px;align-items:center;z-index:60;
  opacity:0;transition:opacity .2s var(--ease)}
.toast.show{opacity:1}
.toast button{background:none;border:none;color:var(--accent);font-weight:600}
.modal{background:var(--overlay);border:1px solid var(--line-strong);border-radius:var(--r-lg);box-shadow:var(--shadow);
  width:440px;max-width:92vw;margin-top:18vh;padding:20px}
.modal h3{margin:0 0 8px}.modal p{color:var(--fg-body)}
.modal .danger-zone input{width:100%;margin:10px 0}
.fade-in{animation:fi .2s var(--ease)}@keyframes fi{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
</style></head>
<body>
<div class="app">
  <aside class="side">
    <div class="brand">
      <svg class="mark" viewBox="0 0 48 48" fill="none"><defs>
        <linearGradient id="hg" x1="0" y1="0" x2="48" y2="48"><stop stop-color="#5b8cff"/><stop offset="1" stop-color="#7b5bff"/></linearGradient>
        <linearGradient id="hg2" x1="0" y1="0" x2="48" y2="48"><stop stop-color="#4ec9a3"/><stop offset="1" stop-color="#3ba6ff"/></linearGradient></defs>
        <path d="M16 6C16 18 32 18 32 30M32 6C32 18 16 18 16 30M16 18C16 30 32 30 32 42M32 18C32 30 16 30 16 42"
          stroke="url(#hg)" stroke-width="3" stroke-linecap="round"/>
        <circle cx="16" cy="12" r="2.4" fill="url(#hg2)"/><circle cx="32" cy="12" r="2.4" fill="url(#hg2)"/>
        <circle cx="16" cy="36" r="2.4" fill="url(#hg2)"/><circle cx="32" cy="36" r="2.4" fill="url(#hg2)"/></svg>
      <div><b>Helix</b><span>your portable memory</span></div>
    </div>
    <nav class="nav" id="nav"></nav>
    <div class="foot">
      <div class="meter">saved running locally<b id="metersaved">$0.00</b></div>
      <div class="muted" style="margin-top:8px;font-size:11px">Press <span class="kbd">⌘K</span> · local &amp; private</div>
    </div>
  </aside>
  <main class="main" id="main"></main>
</div>
<div class="scrim" id="scrim"></div>
<div class="gtip" id="gtip"></div>

<script>
const $=(s,r=document)=>r.querySelector(s), el=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstElementChild};
const esc=s=>(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function api(p,o){const r=await fetch(p,o);if(!r.ok&&r.status!==404)throw new Error(p+' '+r.status);return r.json()}
async function post(p,b){return api(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})})}
const fmt$=n=>'$'+(n||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});

const TYPES={identity:'#7b5bff',preference:'#5b8cff',project:'#3ba6ff',decision:'#4ec9a3',entity:'#d29922',
  convention:'#58a6ff',snippet:'#3fb950',procedure:'#e879f9',episode:'#8b95a7',fact:'#9aa6bd'};
const tcolor=t=>TYPES[t]||'#9aa6bd';

const ICON={memories:'M4 6h16M4 12h16M4 18h10',copilot:'M12 3a9 9 0 100 18 9 9 0 000-18zM8 10h.01M16 10h.01M8 15c1 1 6 1 8 0',
  graph:'M5 5a2 2 0 110 4 2 2 0 010-4zM19 8a2 2 0 110 4 2 2 0 010-4zM9 17a2 2 0 110 4 2 2 0 010-4zM7 7l10 3M9 16l8-5',
  review:'M9 11l3 3 8-8M4 4h10M4 9h6M4 14h6M4 19h12',insights:'M4 19V5M4 19h16M8 16v-5M13 16V8M18 16v-8',
  timeline:'M12 3v18M7 7h.01M7 12h.01M7 17h.01M12 7h6M12 12h4M12 17h6',audit:'M12 3l8 4v5c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V7zM9 12l2 2 4-4'};
const VIEWS=[['memories','Memories'],['copilot','Copilot'],['graph','Graph'],['review','Review'],['insights','Insights'],['timeline','Timeline'],['audit','Audit']];

function icon(name,cls='ic'){return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${ICON[name]||''}"/></svg>`}
let CUR='memories', REVIEWN=0;

function renderNav(){
  $('#nav').innerHTML=VIEWS.map(([k,l])=>`<button data-v="${k}" class="${k===CUR?'on':''}">${icon(k)}<span>${l}</span>${k==='review'&&REVIEWN?`<span class="badge">${REVIEWN}</span>`:''}</button>`).join('');
  $('#nav').querySelectorAll('button').forEach(b=>b.onclick=()=>go(b.dataset.v));
}
function go(v){CUR=v;location.hash=v;renderNav();VIEWMAP[v]()}
window.onhashchange=()=>{const v=location.hash.slice(1);if(v&&VIEWMAP[v]&&v!==CUR)go(v)};

function head(title,sub){return `<div class="head"><h2>${title}</h2><span class="sub">${sub||''}</span><span class="sp"></span><button class="btn sm" onclick="openK()">⌘K Search</button></div>`}
function confBand(c){const col=c>=.7?'var(--green)':c>=.4?'var(--warning)':'var(--danger)';
  return `<span class="confbar" title="confidence ${c}"><i style="width:${Math.round(c*100)}%;background:${col}"></i></span>`}
function flags(m){let s='';if(m.signed)s+='<span class="flag signed">✓ signed</span>';if(m.stale)s+='<span class="flag stale">⚠ stale?</span>';if(m.conflict)s+='<span class="flag conflict">⚡ conflict</span>';return s}
function card(m,score){
  return `<div class="card fade-in" id="c_${m.id}"><div class="c">${esc(m.content)}</div>
   <div class="meta">${score!==undefined?`<span class="score">${score.toFixed(2)}</span>`:''}
   <span class="dot" style="background:${tcolor(m.type)}"></span><span class="pill t">${m.type}</span>
   <span class="pill">${esc(m.scope)}</span>${confBand(m.confidence)}${flags(m)}
   <span class="act"><button class="x" onclick="why('${m.id}')">why?</button>
   <button class="x" onclick="editM('${m.id}')">edit</button>
   <button class="x" onclick="forgetM('${m.id}')">forget</button>
   <button class="x del" onclick="eraseM('${m.id}')">erase</button></span></div>
   <div id="x_${m.id}"></div></div>`}

/* ---------- Memories ---------- */
async function vMemories(){
  $('#main').innerHTML=head('Memories','everything Helix knows — sourced &amp; editable')+
   `<div class="row"><input id="q" class="grow" placeholder="Search your memory… (semantic + keyword)">
      <button class="btn pri" onclick="doSearch()">Search</button></div>
    <div class="row"><input id="nc" class="grow" placeholder="Teach Helix a fact…">
      <input id="ns" value="global" style="width:150px" placeholder="scope">
      <button class="btn" onclick="addM()">Add</button></div><div id="list"></div>`;
  $('#q').onkeydown=e=>{if(e.key==='Enter')doSearch()};
  $('#nc').onkeydown=e=>{if(e.key==='Enter')addM()};
  loadList();
}
async function loadList(){const d=await api('/api/memories');
  $('#list').innerHTML=d.memories.length?d.memories.map(m=>card(m)).join(''):emptyState('No memories yet','Teach Helix a fact above, or connect an agent over MCP.')}
async function doSearch(){const q=$('#q').value.trim();if(!q)return loadList();const d=await api('/api/search?q='+encodeURIComponent(q));
  $('#list').innerHTML=d.results.length?d.results.map(r=>card(r,r.score)).join(''):emptyState('No matches','Try different words — search is semantic + keyword.')}
async function addM(){const c=$('#nc').value.trim();if(!c)return;await post('/api/remember',{content:c,scope:$('#ns').value||'global'});
  $('#nc').value='';toast('Remembered');loadList();refreshMeta()}
async function why(id){const b=$('#x_'+id);if(b.innerHTML){b.innerHTML='';return}
  const m=await api('/api/memory?id='+encodeURIComponent(id));
  const p=(m.provenance||[]).map(x=>`source <b>${esc(x.agent||'?')}</b> · ${esc(x.extractor||'?')} · ${esc(x.origin||'')}`).join('<br>');
  b.innerHTML=`<div class="prov">${p||'no provenance'}<br>created ${(m.created_at||'').replace('T',' ').slice(0,16)} · confidence ${m.confidence} · importance ${m.importance}</div>`}
async function editM(id){const m=await api('/api/memory?id='+encodeURIComponent(id));const b=$('#x_'+id);
  b.innerHTML=`<div style="margin-top:10px"><textarea id="e_${id}" style="width:100%;min-height:60px">${esc(m.content)}</textarea>
    <div class="row" style="margin-top:6px"><input id="es_${id}" class="grow" value="${esc(m.scope)}">
    <button class="btn pri sm" onclick="saveE('${id}')">Save</button></div></div>`}
async function saveE(id){await post('/api/edit',{id,content:$('#e_'+id).value,scope:$('#es_'+id).value});toast('Saved');loadList()}
async function forgetM(id){await post('/api/forget',{id});toast('Forgotten — recoverable in history',()=>{});refreshIf('memories')}
function eraseM(id){confirmErase(id)}

/* ---------- Copilot ---------- */
function vCopilot(){
  $('#main').innerHTML=head('Copilot','ask what Helix knows — answers are sourced, never a black box')+
   `<div class="chat"><div class="stream" id="stream">${copilotEmpty()}</div>
    <div class="row" style="margin-top:12px"><input id="ask" class="grow" placeholder="What do you know about…?">
    <button class="btn pri" onclick="ask()">Ask</button></div></div>`;
  $('#ask').onkeydown=e=>{if(e.key==='Enter')ask()};$('#ask').focus()}
function copilotEmpty(){return `<div class="empty"><div class="g">${bigHelix()}</div>
  <div style="color:var(--fg-body);margin-bottom:14px">Ask Helix what it remembers.</div>
  <div class="suggest" style="justify-content:center">
   ${['What do I know about the billing service?','What conventions do I follow?','What decisions have I made?'].map(s=>`<button onclick="ask(this.textContent)">${s}</button>`).join('')}</div></div>`}
async function ask(q){q=q||$('#ask').value.trim();if(!q)return;$('#ask').value='';
  const st=$('#stream');if(st.querySelector('.empty'))st.innerHTML='';
  st.insertAdjacentHTML('beforeend',`<div class="msg you">${esc(q)}</div>`);
  const d=await api('/api/about?q='+encodeURIComponent(q));
  const facts=d.facts.length?`<div class="srcs">${d.facts.map((f,i)=>
    `<div class="card" style="margin:0"><div class="c"><sup style="color:var(--accent)">[${i+1}]</sup> ${esc(f.content)}</div>
     <div class="meta"><span class="dot" style="background:${tcolor(f.type)}"></span><span class="pill t">${f.type}</span>
     ${confBand(f.confidence)}<span class="muted">via ${esc(f.source||'?')}</span>${f.stale?'<span class="flag stale">⚠ stale?</span>':''}</div></div>`).join('')}</div>`
    :`<div class="muted">I don't have anything on that yet.</div>`;
  st.insertAdjacentHTML('beforeend',`<div class="msg bot"><div class="ans">Here's what I know about <b>${esc(q)}</b>${d.facts.length?' — '+d.facts.length+' fact(s), each with its source:':':'}</div>${facts}</div>`);
  st.scrollTop=st.scrollHeight}

/* ---------- Graph ---------- */
async function vGraph(assemble){
  $('#main').innerHTML=head(assemble?'Building your memory…':'Graph','your memory as a living network — size = recall, color = type')+
    `<canvas id="gcanvas"></canvas><div class="legend" id="legend"></div><div id="assemblecta"></div>`;
  $('#legend').innerHTML=Object.entries(TYPES).map(([t,c])=>`<span><span class="dot" style="background:${c}"></span> ${t}</span>`).join('');
  const d=await api('/api/graph');forceGraph($('#gcanvas'),d,{assemble:!!assemble,onSettle:assemble?onAssembled:null})}
function onAssembled(){const cta=$('#assemblecta');if(!cta)return;
  $('.head h2')&&($('.head h2').textContent='Graph');
  cta.innerHTML=`<div class="card fade-in" style="margin-top:14px;text-align:center;background:var(--raised);border-color:var(--line-strong)">
    <div style="font-size:15px;color:var(--fg)">🧬 That's your agent's brain — assembled in seconds.</div>
    <div class="muted" style="margin:6px 0 12px">Every fact is sourced, editable, and yours. Now ask Helix what it knows.</div>
    <button class="btn pri" onclick="go('copilot')">Ask the copilot →</button></div>`}
function goGraphAssemble(){CUR='graph';location.hash='graph';renderNav();vGraph(true)}

function forceGraph(cv,data,opts){opts=opts||{};
  const tip=$('#gtip');const dpr=Math.min(devicePixelRatio||1,2);
  const RM=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const assemble=opts.assemble&&!RM;
  function size(){cv.width=cv.clientWidth*dpr;cv.height=cv.clientHeight*dpr}
  size();const W=()=>cv.width/dpr,H=()=>cv.height/dpr;
  const spread=assemble?14:240;
  const ns=data.nodes.slice(0,400).map((n,i)=>({...n,x:W()/2+(Math.random()-.5)*spread,y:H()/2+(Math.random()-.5)*spread,vx:0,vy:0,born:assemble?i*32:0}));
  const idx={};ns.forEach((n,i)=>idx[n.id]=i);
  const ls=data.edges.map(e=>({s:idx[e.from],t:idx[e.to],rel:e.relation})).filter(l=>l.s!=null&&l.t!=null);
  const deg={};ls.forEach(l=>{deg[l.s]=(deg[l.s]||0)+1;deg[l.t]=(deg[l.t]||0)+1});
  let view={x:0,y:0,k:1},hot=null,alpha=assemble?2.2:1,dragN=null,pan=null,settled=false;
  const t0=performance.now(),lastBorn=assemble?(ns.length-1)*32:0;
  const el=()=>performance.now()-t0, shown=n=>!assemble||el()>=n.born, fade=n=>assemble?Math.min((el()-n.born)/300,1):1;
  const R=n=>4+Math.sqrt((n.reinforced||0))*2.2+Math.min((deg[idx[n.id]]||0),6)*.6;
  function step(){
    if(alpha<.005)return;alpha*=.985;
    for(let i=0;i<ns.length;i++){const a=ns[i];
      for(let j=i+1;j<ns.length;j++){const b=ns[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy||1;
        if(d2<40000){const f=900/d2;const d=Math.sqrt(d2);dx/=d;dy/=d;a.vx+=dx*f*alpha;a.vy+=dy*f*alpha;b.vx-=dx*f*alpha;b.vy-=dy*f*alpha}}
      a.vx+=(W()/2-a.x)*.0009*alpha;a.vy+=(H()/2-a.y)*.0009*alpha}
    ls.forEach(l=>{const a=ns[l.s],b=ns[l.t];let dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)||1,f=(d-90)*.012*alpha;
      dx/=d;dy/=d;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f});
    ns.forEach(n=>{if(n===dragN)return;n.x+=n.vx*.85;n.y+=n.vy*.85;n.vx*=.82;n.vy*=.82})}
  function draw(){const c=cv.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W(),H());
    c.save();c.translate(view.x,view.y);c.scale(view.k,view.k);
    const near=hot!=null?new Set([hot,...ls.filter(l=>l.s===hot||l.t===hot).flatMap(l=>[l.s,l.t])]):null;
    ls.forEach(l=>{const a=ns[l.s],b=ns[l.t];if(!shown(a)||!shown(b))return;const on=near&&(l.s===hot||l.t===hot);
      c.globalAlpha=Math.min(fade(a),fade(b));
      c.strokeStyle=on?'rgba(123,91,255,.7)':near?'rgba(140,150,170,.05)':'rgba(91,140,255,.16)';
      c.lineWidth=on?1.6:1;c.beginPath();c.moveTo(a.x,a.y);c.lineTo(b.x,b.y);c.stroke()});
    ns.forEach((n,i)=>{if(!shown(n))return;const dim=near&&!near.has(i);c.globalAlpha=(dim?.18:1)*fade(n);
      c.beginPath();c.arc(n.x,n.y,R(n),0,7);c.fillStyle=tcolor(n.type);c.fill();
      if(i===hot){c.lineWidth=2;c.strokeStyle='#fff';c.stroke()}
      if(R(n)>7||i===hot){c.globalAlpha=(dim?.18:.85)*fade(n);c.fillStyle='#cbd5e1';c.font='10px ui-sans-serif';
        c.fillText((n.content||'').slice(0,22),n.x+R(n)+3,n.y+3)}});
    c.restore();c.globalAlpha=1}
  function loop(){step();draw();
    if(!settled&&opts.onSettle&&(assemble?(el()>lastBorn+700&&alpha<.04):false)){settled=true;opts.onSettle()}
    requestAnimationFrame(loop)}loop();
  if(opts.onSettle&&(RM||!assemble))setTimeout(()=>{if(!settled){settled=true;opts.onSettle()}},400);
  function at(ev){const r=cv.getBoundingClientRect();const mx=(ev.clientX-r.left-view.x)/view.k,my=(ev.clientY-r.top-view.y)/view.k;
    let best=null,bd=1e9;ns.forEach((n,i)=>{const d=(n.x-mx)**2+(n.y-my)**2;if(d<bd&&d<Math.max(R(n)*R(n),120)){bd=d;best=i}});return best}
  cv.onmousedown=e=>{const i=at(e);if(i!=null){dragN=ns[i]}else pan={x:e.clientX-view.x,y:e.clientY-view.y};cv.style.cursor='grabbing'};
  cv.onmousemove=e=>{const r=cv.getBoundingClientRect();
    if(dragN){dragN.x=(e.clientX-r.left-view.x)/view.k;dragN.y=(e.clientY-r.top-view.y)/view.k;alpha=Math.max(alpha,.3);return}
    if(pan){view.x=e.clientX-pan.x;view.y=e.clientY-pan.y;return}
    const i=at(e);hot=i;if(i!=null){tip.style.display='block';tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY+12+'px';
      tip.innerHTML=`<b style="color:${tcolor(ns[i].type)}">${ns[i].type}</b> · recalled ${ns[i].reinforced}×<br>${esc(ns[i].content)}`}
    else tip.style.display='none';cv.style.cursor=i!=null?'pointer':'grab'};
  window.addEventListener('mouseup',()=>{dragN=null;pan=null;cv.style.cursor='grab'});
  cv.onwheel=e=>{e.preventDefault();const f=e.deltaY<0?1.1:.9;view.k=Math.max(.2,Math.min(4,view.k*f))};
}

/* ---------- Review ---------- */
async function vReview(){
  const[q,cf]=await Promise.all([api('/api/review'),api('/api/conflicts')]);
  let html=head('Review','keep your memory honest — resolve stale &amp; conflicting facts');
  if(cf.conflicts.length){html+='<div class="section"><h3>Conflicts — pick a winner</h3>'+cf.conflicts.map(p=>
    `<div class="versus"><div class="side-pick"><div>${esc(p.a.content)}</div><div class="meta"><span class="pill t">${p.a.type}</span></div>
      <button class="btn sm pri" style="margin-top:8px" onclick="resolveC('${p.b.id}','${p.a.id}')">Keep this</button></div>
     <div class="vs">vs</div>
     <div class="side-pick"><div>${esc(p.b.content)}</div><div class="meta"><span class="pill t">${p.b.type}</span></div>
      <button class="btn sm pri" style="margin-top:8px" onclick="resolveC('${p.a.id}','${p.b.id}')">Keep this</button></div></div>`).join('')+'</div>'}
  const stale=q.queue.filter(i=>i.kind==='stale');
  html+='<div class="section"><h3>Possibly stale ('+stale.length+')</h3>'+(stale.length?stale.map(i=>
    `<div class="card" id="r_${i.id}" style="margin:0 0 8px"><div class="c">${esc(i.content)}</div>
     <div class="meta"><span class="flag stale">⚠ ${esc(i.reason||'stale')}</span>
     <span class="act"><button class="btn sm" onclick="resolveS('${i.id}',true)">Keep</button>
     <button class="btn sm danger" onclick="resolveS('${i.id}',false)">Dismiss</button></span></div></div>`).join('')
    :'<div class="center muted" style="padding:24px">✓ Nothing stale — your memory is fresh.</div>')+'</div>';
  $('#main').innerHTML=html}
async function resolveS(id,keep){await post('/api/resolve',{id,keep});toast(keep?'Kept':'Dismissed');vReview();refreshMeta()}
async function resolveC(loseId,keepId){await post('/api/forget',{id:loseId});toast('Conflict resolved');vReview()}

/* ---------- Insights ---------- */
async function vInsights(){
  const[a,s,th]=await Promise.all([api('/api/analytics'),api('/api/savings'),api('/api/themes')]);
  const days=Object.entries(a.facts_per_day||{});const max=Math.max(1,...days.map(([,v])=>v));
  const cells=buildHeat(a.facts_per_day||{});
  const tmax=Math.max(1,...Object.values(a.by_type||{}));
  $('#main').innerHTML=head('Insights','your agent\'s brain, quantified')+
   `<div class="grid">
     <div class="stat"><div class="k">Memories</div><div class="v num">${a.total}</div></div>
     <div class="stat"><div class="k">To review</div><div class="v num" style="color:${a.to_review?'var(--warning)':'var(--fg)'}">${a.to_review}</div></div>
     <div class="stat"><div class="k">Saved vs cloud</div><div class="v g num" id="bigsave">$0.00</div></div>
     <div class="stat"><div class="k">Tombstones</div><div class="v num">${a.tombstones}</div></div></div>
    <div class="section"><h3>Facts learned (last ~16 weeks)</h3><div class="heat">${cells}</div></div>
    <div class="section"><h3>By type</h3>${Object.entries(a.by_type||{}).sort((x,y)=>y[1]-x[1]).map(([t,n])=>
      `<div class="bar"><span class="lbl"><span class="dot" style="background:${tcolor(t)}"></span> ${t}</span>
       <span class="track"><i style="width:${Math.round(n/tmax*100)}%"></i></span><span class="n">${n}</span></div>`).join('')||'<span class="muted">no data</span>'}</div>
    <div class="section"><h3>Top themes</h3>${(th.themes||[]).map(t=>
      `<div class="bar"><span class="lbl mono">${esc(t.topic)}</span><span class="track"><i style="width:${Math.round(t.mentions/(th.themes[0].mentions||1)*100)}%;background:var(--grad-teal)"></i></span><span class="n">${t.mentions}</span></div>`).join('')||'<span class="muted">no themes yet</span>'}</div>`;
  countUp($('#bigsave'),s.est_usd_saved||0)}
function buildHeat(byday){const today=new Date();let out='';for(let i=111;i>=0;i--){const d=new Date(today);d.setDate(d.getDate()-i);
  const key=d.toISOString().slice(0,10);const v=byday[key]||0;const l=v===0?0:v<2?1:v<4?2:v<7?3:4;out+=`<i class="l${l}" title="${key}: ${v}"></i>`}return out}

/* ---------- Timeline ---------- */
async function vTimeline(){
  const[c,h]=await Promise.all([api('/api/changes'),api('/api/history')]);
  let html=head('Timeline','how your memory evolved');
  html+=`<div class="section"><h3>Time travel — what did Helix believe?</h3>
    <input type="range" id="asofr" min="0" max="120" value="120" style="width:100%;accent-color:var(--accent)" oninput="asof(this.value)">
    <div style="display:flex;justify-content:space-between;color:var(--dim);font-size:11px;margin-top:2px"><span>~4 months ago</span><span>now</span></div>
    <div id="asofout" style="margin:12px 0 6px;color:var(--fg)">today — drag to rewind</div>
    <div id="asoflist"></div></div>`;
  if(c.changes.length){html+='<div class="section"><h3>Changes</h3>'+c.changes.map(x=>
    `<div class="bar" style="display:block"><span class="muted mono">${(x.changed_at||'').slice(0,10)}</span>
     &nbsp; <span style="color:var(--danger)">${esc(x.from)}</span> → <span style="color:var(--green)">${esc(x.to)}</span></div>`).join('')+'</div>'}
  html+='<div class="section"><h3>Events</h3>'+(h.history||[]).map(e=>
    `<div class="bar"><span class="muted mono" style="width:130px">${(e.ts||'').replace('T',' ').slice(0,16)}</span>
     <span class="pill t">${e.op}</span><span class="muted mono" style="font-size:11px">${esc(e.memory_id||'')}</span></div>`).join('')+'</div>';
  $('#main').innerHTML=html;asof(120)}
async function asof(v){const max=120,dago=max-(+v);const d=new Date();d.setDate(d.getDate()-dago);
  if(dago>0)d.setHours(23,59,59,0);
  const r=await api('/api/asof?at='+encodeURIComponent(d.toISOString().slice(0,19)));
  const lbl=dago===0?'today':d.toISOString().slice(0,10);
  if($('#asofout'))$('#asofout').innerHTML=`<b>${lbl}</b> — ${r.count} fact${r.count===1?'':'s'} believed`;
  if($('#asoflist'))$('#asoflist').innerHTML=r.facts.slice(0,8).map(f=>
    `<div class="bar" style="display:block"><span class="dot" style="background:${tcolor(f.type)}"></span> <span class="pill t">${f.type}</span> ${esc(f.content)}</div>`).join('')||'<span class="muted">nothing believed yet at that point</span>'}

/* ---------- Audit ---------- */
async function vAudit(){const d=await api('/api/audit');
  $('#main').innerHTML=head('Audit','tamper-evident governance log')+
   `<div class="section"><h3>Chain ${d.intact?'<span class="flag signed">✓ intact</span>':'<span class="flag conflict">⚠ TAMPERED</span>'}</h3>`+
   ((d.entries||[]).map(e=>`<div class="bar"><span class="muted mono" style="width:140px">${(e.ts||'').replace('T',' ').slice(0,16)}</span>
     <span class="pill t">${esc(e.action)}</span><span class="mono">${esc(e.actor)}</span>
     <span class="muted mono" style="font-size:11px;margin-left:auto">${esc(e.target||'')}</span></div>`).join('')||'<span class="muted">no governance events yet</span>')+'</div>'}

/* ---------- shared bits ---------- */
function emptyState(t,s){return `<div class="empty"><div class="g">${bigHelix()}</div><div style="color:var(--fg-body);font-size:15px">${t}</div><div style="margin-top:6px">${s}</div></div>`}
function bigHelix(){return `<svg width="64" height="64" viewBox="0 0 48 48" fill="none" stroke="url(#hg)" stroke-width="3" stroke-linecap="round" opacity=".7"><path d="M16 6C16 18 32 18 32 30M32 6C32 18 16 18 16 30M16 18C16 30 32 30 32 42M32 18C32 30 16 30 16 42"/></svg>`}
function countUp(node,to){let t0=null;const dur=900;function f(t){if(!t0)t0=t;const p=Math.min((t-t0)/dur,1);const e=1-Math.pow(1-p,3);
  node.textContent=fmt$(to*e);if(p<1)requestAnimationFrame(f)}requestAnimationFrame(f)}
function toast(msg,undo){const t=el(`<div class="toast"><span>${esc(msg)}</span></div>`);if(undo)t.insertAdjacentHTML('beforeend','<button>Undo</button>');
  document.body.appendChild(t);requestAnimationFrame(()=>t.classList.add('show'));setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),250)},2600)}
function refreshIf(v){if(CUR===v)VIEWMAP[v]()}
function refreshMeta(){api('/api/savings').then(s=>{$('#metersaved').textContent=fmt$(s.est_usd_saved||0)});
  api('/api/review').then(d=>{REVIEWN=d.queue.length;renderNav()})}

/* erase = type-to-confirm (irreversible) */
function confirmErase(id){const sc=$('#scrim');
  sc.innerHTML=`<div class="modal fade-in"><h3 style="color:var(--danger)">Erase this memory?</h3>
   <p>This is <b>irreversible</b> — it deletes the fact, its embedding, and tombstones it so a merge can't bring it back. Unlike <b>forget</b>, it cannot be undone.</p>
   <div class="danger-zone"><input id="erasec" placeholder='type ERASE to confirm'></div>
   <div class="row" style="margin:4px 0 0;justify-content:flex-end"><button class="btn" onclick="closeK()">Cancel</button>
   <button class="btn danger" id="erasebtn" disabled style="opacity:.5">Erase</button></div></div>`;
  sc.classList.add('show');const inp=$('#erasec'),btn=$('#erasebtn');inp.focus();
  inp.oninput=()=>{const ok=inp.value.trim()==='ERASE';btn.disabled=!ok;btn.style.opacity=ok?1:.5};
  btn.onclick=async()=>{await post('/api/erase',{id});closeK();toast('Erased');refreshIf('memories');refreshMeta()}}

/* cmd-k palette */
let KSEL=0,KITEMS=[];
function openK(){const sc=$('#scrim');sc.innerHTML=`<div class="palette fade-in"><input id="kq" placeholder="Search memories &amp; actions…"><div class="res" id="kres"></div></div>`;
  sc.classList.add('show');const q=$('#kq');q.focus();q.oninput=()=>kSearch(q.value);q.onkeydown=kNav;kSearch('')}
function closeK(){$('#scrim').classList.remove('show');$('#scrim').innerHTML=''}
$('#scrim').onclick=e=>{if(e.target.id==='scrim')closeK()};
const ACTIONS=VIEWS.map(([k,l])=>({label:'Go to '+l,run:()=>{closeK();go(k)},kind:'view'}))
  .concat([{label:'Add a memory',run:()=>{closeK();go('memories');setTimeout(()=>$('#nc')&&$('#nc').focus(),50)},kind:'action'}]);
async function kSearch(q){KSEL=0;let items=ACTIONS.filter(a=>fz(a.label,q));
  if(q.trim()){const d=await api('/api/search?q='+encodeURIComponent(q)+'&k=6');items=items.concat(d.results.map(r=>({label:r.content,sub:r.type,run:()=>{closeK();go('memories')},kind:'mem'})))}
  KITEMS=items.slice(0,12);$('#kres').innerHTML=KITEMS.map((it,i)=>`<div class="it ${i===KSEL?'sel':''}" data-i="${i}">${icon(it.kind==='view'?'graph':it.kind==='mem'?'memories':'copilot')}<span>${esc(it.label)}</span>${it.sub?`<span class="k pill">${it.sub}</span>`:''}</div>`).join('')||'<div class="it muted">no matches</div>';
  $('#kres').querySelectorAll('.it[data-i]').forEach(d=>d.onclick=()=>KITEMS[+d.dataset.i].run())}
function kNav(e){if(e.key==='ArrowDown'){KSEL=Math.min(KSEL+1,KITEMS.length-1);e.preventDefault()}
  else if(e.key==='ArrowUp'){KSEL=Math.max(KSEL-1,0);e.preventDefault()}
  else if(e.key==='Enter'){KITEMS[KSEL]&&KITEMS[KSEL].run();return}else return;
  $('#kres').querySelectorAll('.it').forEach((d,i)=>d.classList.toggle('sel',i===KSEL))}
function fz(s,q){s=s.toLowerCase();q=q.toLowerCase().trim();if(!q)return true;let j=0;for(const ch of s){if(ch===q[j])j++;if(j===q.length)return true}return false}

function vOnboard(){
  $('#main').innerHTML=`<div class="empty" style="padding:7vh 20px">
    <div class="g" style="margin-bottom:18px">${bigHelix()}</div>
    <h2 style="font-size:25px;margin:0 0 8px;letter-spacing:-.5px;color:var(--fg)">Give your AI a memory that's yours</h2>
    <div style="color:var(--fg-body);max-width:460px;margin:0 auto 24px;line-height:1.6">Helix remembers your projects, decisions, and conventions — local, private, and portable across every agent. Watch it build one in seconds.</div>
    <div class="row" style="justify-content:center">
      <button class="btn pri" onclick="seedDemo()">✨ Load a sample memory</button>
      <button class="btn" onclick="go('memories')">I'll add my own</button></div>
    <div class="muted" style="margin-top:16px;font-size:12px">or connect an agent: <span class="mono">helix connect cursor</span></div></div>`}
async function seedDemo(){$('#main').innerHTML=`<div class="empty" style="padding:14vh 20px"><div class="g">${bigHelix()}</div><div class="muted" style="margin-top:10px">Distilling a sample memory…</div></div>`;
  await post('/api/seed');await new Promise(r=>setTimeout(r,250));refreshMeta();goGraphAssemble()}
const VIEWMAP={memories:vMemories,copilot:vCopilot,graph:vGraph,review:vReview,insights:vInsights,timeline:vTimeline,audit:vAudit};
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();openK()}
  if(e.key==='Escape')closeK()});
async function boot(){let d={memories:[]};try{d=await api('/api/memories')}catch(e){}
  refreshMeta();const hash=location.hash.slice(1);
  if(!d.memories.length&&!(hash&&VIEWMAP[hash])){CUR='memories';renderNav();vOnboard();return}
  const start=(hash&&VIEWMAP[hash])?hash:'memories';CUR=start;renderNav();VIEWMAP[start]()}
boot();
setInterval(()=>{if(!document.hidden)refreshMeta()},6000);  /* live $0-meter + review badge */
</script></body></html>"""
