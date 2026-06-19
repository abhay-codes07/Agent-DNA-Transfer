"""Dashboard daemon tests — API shapes, served HTML, and DNS-rebinding (Host/Origin) guard.

Uses an ephemeral port (0) so there's no fixed-port flakiness, and http.client so we can set
the Host/Origin headers the security guard checks.
"""

from __future__ import annotations

import http.client
import json
import threading

import pytest

from helix_core.config import Config
from helix_core.daemon import DASHBOARD_HTML, build_server
from helix_core.engine import Engine


@pytest.fixture()
def server(tmp_path):
    eng = Engine(Config(home=tmp_path))
    eng.remember("We use Postgres for the billing service", scope="project:billing")
    httpd = build_server("127.0.0.1", 0, eng)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield port
    finally:
        httpd.shutdown()
        httpd.server_close()
        eng.close()


def _req(port, method, path, *, host=None, origin=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if host:
        headers["Host"] = host  # http.client skips its own Host when one is provided
    if origin:
        headers["Origin"] = origin
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body)
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    return r.status, r.getheader("Content-Type") or "", raw


def test_serves_dashboard_html(server):
    status, ctype, body = _req(server, "GET", "/")
    assert status == 200 and "text/html" in ctype
    assert b"Helix" in body and b"forceGraph" in body  # the canvas graph is present


def test_health_and_analytics(server):
    s, _, b = _req(server, "GET", "/api/health")
    assert s == 200 and json.loads(b)["ok"] is True
    s, _, b = _req(server, "GET", "/api/analytics")
    assert "total" in json.loads(b)
    s, _, b = _req(server, "GET", "/api/savings")
    assert "est_usd_saved" in json.loads(b)


def test_remember_then_list_roundtrip(server):
    _req(server, "POST", "/api/remember", body={"content": "Deploys freeze on Fridays"})
    s, _, b = _req(server, "GET", "/api/memories")
    contents = [m["content"] for m in json.loads(b)["memories"]]
    assert any("Postgres" in c for c in contents)
    assert any("Fridays" in c for c in contents)


def test_about_copilot_endpoint(server):
    s, _, b = _req(server, "GET", "/api/about?q=billing%20database")
    d = json.loads(b)
    assert "facts" in d and d["count"] >= 1


def test_host_validation_blocks_dns_rebinding(server):
    # A non-loopback Host header is rejected (defends against DNS rebinding).
    s, _, _ = _req(server, "GET", "/api/stats", host="evil.example.com")
    assert s == 403
    # A non-loopback Origin is rejected too.
    s, _, _ = _req(server, "GET", "/api/stats", origin="http://evil.example.com")
    assert s == 403
    # Loopback Host + loopback Origin are allowed.
    s, _, _ = _req(server, "GET", "/api/stats", origin="http://localhost:9999")
    assert s == 200


def test_dashboard_html_has_all_views():
    for marker in (
        "vMemories",
        "vCopilot",
        "vGraph",
        "vReview",
        "vInsights",
        "vTimeline",
        "vAudit",
    ):
        assert marker in DASHBOARD_HTML
    assert "confirmErase" in DASHBOARD_HTML  # type-to-confirm erase
    assert "openK" in DASHBOARD_HTML  # cmd-k palette
