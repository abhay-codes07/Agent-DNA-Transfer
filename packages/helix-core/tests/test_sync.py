"""Phase 7 tests: optional encrypted team sync (bring-your-own-storage).

Requires PyNaCl (the .dna backend); skipped if unavailable. Offline.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nacl")

from helix_core.config import Config  # noqa: E402
from helix_core.engine import Engine  # noqa: E402
from helix_core.sync import (  # noqa: E402
    HttpBackend,
    LocalDirBackend,
    S3Backend,
    backend_from_uri,
)

PW = "team-shared-passphrase"


def _engine(home):
    return Engine(Config(home=home))


def test_push_then_pull_merges_memory_across_machines(tmp_path):
    shared = tmp_path / "shared"
    a = _engine(tmp_path / "a")
    a.remember("We use Postgres for the billing service.", scope="project:billing")
    a.remember("We deploy on Fridays only.", scope="project:billing")
    a.push(str(shared), passphrase=PW, name="team.dna")
    a.close()

    b = _engine(tmp_path / "b")
    b.remember("We use Postgres for the billing service.", scope="project:billing")  # duplicate
    res = b.pull(str(shared), passphrase=PW, name="team.dna")
    assert res["mode"] == "merge"
    assert res["merged"]["ADD"] >= 1  # the Fridays fact was new

    contents = [m.content.lower() for m in b.list_memories()]
    assert any("fridays" in c for c in contents)  # came from A
    assert sum("postgres" in c for c in contents) == 1  # deduped, not duplicated
    b.close()


def test_pushed_file_is_encrypted_at_rest(tmp_path):
    shared = tmp_path / "shared"
    a = _engine(tmp_path / "a")
    a.remember("SECRETMARKER about the deploy process", scope="g")
    a.push(str(shared), passphrase=PW, name="team.dna")
    a.close()
    data = (shared / "team.dna").read_bytes()
    assert b"SECRETMARKER" not in data  # the backend only ever sees ciphertext


def test_pull_missing_strand_raises(tmp_path):
    b = _engine(tmp_path / "b")
    with pytest.raises(ValueError):
        b.pull(str(tmp_path / "empty-dir"), passphrase=PW, name="nope.dna")
    b.close()


def test_backend_selection(tmp_path):
    assert isinstance(backend_from_uri(str(tmp_path / "d")), LocalDirBackend)
    assert isinstance(backend_from_uri("dir:" + str(tmp_path / "d")), LocalDirBackend)
    assert isinstance(backend_from_uri("s3://bucket/prefix"), S3Backend)
    assert isinstance(backend_from_uri("https://example.com/store"), HttpBackend)
    assert isinstance(backend_from_uri("http://127.0.0.1:9/store"), HttpBackend)


# --- HTTP object-store backend (tested against a local stub server) ---


def _start_object_server():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    blobs: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            blobs[self.path] = self.rfile.read(n)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            data = blobs.get(self.path)
            if data is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def test_http_backend_roundtrip():
    httpd, base = _start_object_server()
    try:
        backend = HttpBackend(base)
        backend.put("x.dna", b"hello-bytes")
        assert backend.get("x.dna") == b"hello-bytes"
        assert backend.get("missing.dna") is None
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_engine_sync_over_http(tmp_path):
    httpd, base = _start_object_server()
    try:
        a = _engine(tmp_path / "a")
        a.remember("We use Postgres for billing.", scope="project:billing")
        a.push(base, passphrase=PW, name="team.dna")
        a.close()

        b = _engine(tmp_path / "b")
        b.pull(base, passphrase=PW, name="team.dna")
        contents = " ".join(m.content.lower() for m in b.list_memories())
        assert "postgres" in contents  # pulled over HTTP and merged
        b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_relay_auth_and_name_validation(tmp_path):
    import threading
    import urllib.error

    from helix_core.relay import build_relay
    from helix_core.sync import HttpBackend

    httpd = build_relay(tmp_path / "store", "127.0.0.1", 0, token="secret")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        auth = HttpBackend(base, headers={"Authorization": "Bearer secret"})
        auth.put("team.dna", b"ciphertext")
        assert auth.get("team.dna") == b"ciphertext"
        with pytest.raises(urllib.error.HTTPError):  # no token -> 401
            HttpBackend(base).put("x.dna", b"y")
        with pytest.raises(urllib.error.HTTPError):  # non-.dna name -> 400
            auth.put("evil.txt", b"y")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_relay_full_sync_cycle(tmp_path):
    import threading

    from helix_core.relay import build_relay

    httpd = build_relay(tmp_path / "store", "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        a = _engine(tmp_path / "a")
        a.remember("We use Postgres for billing.", scope="project:b")
        a.push(base, passphrase=PW, name="team.dna")
        a.close()
        b = _engine(tmp_path / "b")
        b.pull(base, passphrase=PW, name="team.dna")
        assert any("postgres" in m.content.lower() for m in b.list_memories())
        b.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_local_dir_backend_roundtrip(tmp_path):
    backend = LocalDirBackend(tmp_path / "store")
    backend.put("a.dna", b"hello")
    assert backend.get("a.dna") == b"hello"
    assert backend.get("missing.dna") is None
    assert "a.dna" in backend.list()
