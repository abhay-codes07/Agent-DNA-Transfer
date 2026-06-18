"""Phase 5 tests: the local dashboard daemon (JSON API + served HTML).

Spins the stdlib HTTP server on an ephemeral port in a thread and drives it over HTTP — no
browser needed. Offline, uses the hashing embedder (conftest).
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request

from helix_core.config import Config
from helix_core.daemon import build_server
from helix_core.engine import Engine


def _start(tmp_path):
    engine = Engine(Config(home=tmp_path))
    httpd = build_server("127.0.0.1", 0, engine)  # port 0 -> OS picks a free port
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return httpd, base, engine


def _get(url):
    return json.loads(urllib.request.urlopen(url, timeout=5).read())


def _post(url, obj):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def test_daemon_full_crud_cycle(tmp_path):
    httpd, base, engine = _start(tmp_path)
    try:
        assert _get(base + "/api/health")["ok"] is True

        r = _post(base + "/api/remember",
                  {"content": "We use Postgres for the billing service.", "scope": "project:billing"})
        assert r["results"][0]["op"] == "ADD"
        mid = r["results"][0]["id"]

        q = urllib.parse.quote("billing database")
        s = _get(base + f"/api/search?q={q}&scope=project:billing")
        assert any("postgres" in x["content"].lower() for x in s["results"])

        mems = _get(base + "/api/memories")
        assert any(x["id"] == mid for x in mems["memories"])

        g = _get(base + "/api/graph")
        assert "nodes" in g and "edges" in g

        st = _get(base + "/api/stats")
        assert "embedding_model" in st

        f = _post(base + "/api/forget", {"id": mid})
        assert mid in f["forgot"]
        mems2 = _get(base + "/api/memories")
        assert all(x["id"] != mid for x in mems2["memories"])
    finally:
        httpd.shutdown()
        httpd.server_close()
        engine.close()


def test_dashboard_html_is_served(tmp_path):
    httpd, base, engine = _start(tmp_path)
    try:
        html = urllib.request.urlopen(base + "/", timeout=5).read().decode("utf-8")
        assert "Helix" in html
        assert "/api/search" in html  # the page wires itself to the API
    finally:
        httpd.shutdown()
        httpd.server_close()
        engine.close()
