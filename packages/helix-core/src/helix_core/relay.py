"""Thin sync relay (Phase 7): a tiny HTTP object store for encrypted `.dna` strands.

The server side of `sync.HttpBackend`. Run it on a box your team can reach; members
`helix push`/`pull` through it. It only ever stores **ciphertext** (the `.dna` is encrypted
before upload), so the relay never sees plaintext. Stdlib only; optional bearer-token auth.
Only `*.dna` names are accepted and path traversal is rejected.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_NAME = re.compile(r"^[A-Za-z0-9._-]+\.dna$")


def _make_handler(root: Path, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        def _auth_ok(self) -> bool:
            return token is None or self.headers.get("Authorization") == f"Bearer {token}"

        def _status(self, code: int, body: bytes = b"") -> None:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _name(self) -> str | None:
            name = self.path.lstrip("/")
            return name if _NAME.match(name) else None

        def do_PUT(self) -> None:
            if not self._auth_ok():
                return self._status(401)
            name = self._name()
            if name is None:
                return self._status(400)
            length = int(self.headers.get("Content-Length", 0) or 0)
            (root / name).write_bytes(self.rfile.read(length))
            self._status(200)

        def do_GET(self) -> None:
            if not self._auth_ok():
                return self._status(401)
            if self.path in ("/", "/index"):  # list available strands
                names = sorted(p.name for p in root.glob("*.dna"))
                return self._status(200, json.dumps({"strands": names}).encode("utf-8"))
            name = self._name()
            if name is None:
                return self._status(400)
            path = root / name
            if not path.exists():
                return self._status(404)
            self._status(200, path.read_bytes())

        def log_message(self, *args) -> None:  # quiet
            pass

    return Handler


def build_relay(root, host: str = "127.0.0.1", port: int = 8788, token: str | None = None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return HTTPServer((host, port), _make_handler(root, token))


def serve_relay(root, host: str = "127.0.0.1", port: int = 8788, token: str | None = None) -> None:
    httpd = build_relay(root, host, port, token)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
