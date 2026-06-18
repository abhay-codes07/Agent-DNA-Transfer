"""Optional, end-to-end-encrypted team/multi-device sync (Phase 7, ADR-022/030).

Sync moves the **already-encrypted `.dna`** to a shared location — so the backend (a folder, a
cloud-synced directory, an HTTP object store, or S3/R2) only ever sees ciphertext. Pull reuses
the Phase 4 merge, so two people's memories combine with conflict-aware dedup.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse


@runtime_checkable
class SyncBackend(Protocol):
    def put(self, name: str, data: bytes) -> None: ...
    def get(self, name: str) -> bytes | None: ...
    def list(self) -> list[str]: ...


class LocalDirBackend:
    """Bring-your-own-storage: a directory. Pair with any file-syncing tool for real sync."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, name: str, data: bytes) -> None:
        tmp = self.root / (name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(self.root / name)  # atomic

    def get(self, name: str) -> bytes | None:
        path = self.root / name
        return path.read_bytes() if path.exists() else None

    def list(self) -> list[str]:
        return sorted(p.name for p in self.root.glob("*.dna"))


class HttpBackend:
    """REST object store: PUT/GET ``{base}/{name}``.

    Works with anything that speaks plain HTTP PUT/GET — a presigned-URL store, a WebDAV
    server, or a tiny relay. Listing isn't standardized over REST, so `list()` returns [].
    """

    def __init__(self, base_url: str, *, headers: dict[str, str] | None = None) -> None:
        self.base = base_url.rstrip("/")
        self.headers = headers or {}

    def put(self, name: str, data: bytes) -> None:
        req = urllib.request.Request(
            f"{self.base}/{name}", data=data, method="PUT", headers=self.headers
        )
        with urllib.request.urlopen(req) as resp:  # noqa: S310 (user-provided URL by design)
            resp.read()

    def get(self, name: str) -> bytes | None:
        req = urllib.request.Request(f"{self.base}/{name}", headers=self.headers)
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def list(self) -> list[str]:
        return []


class S3Backend:
    """S3 / Cloudflare R2 object store (``s3://bucket/prefix``). Requires boto3 + AWS/R2 creds."""

    def __init__(self, uri: str) -> None:
        parsed = urlparse(uri)
        self.bucket = parsed.netloc
        self.prefix = parsed.path.strip("/")

    def _client(self):  # noqa: ANN202
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - exercised only without boto3
            raise RuntimeError(
                "S3/R2 sync needs boto3 — `pip install boto3` and set your AWS_/R2 credentials "
                "(use a bring-your-own directory or an HTTP store if you'd rather not)."
            ) from exc
        return boto3.client("s3")

    def _key(self, name: str) -> str:
        return f"{self.prefix}/{name}" if self.prefix else name

    def put(self, name: str, data: bytes) -> None:
        self._client().put_object(Bucket=self.bucket, Key=self._key(name), Body=data)

    def get(self, name: str) -> bytes | None:
        client = self._client()
        try:
            return client.get_object(Bucket=self.bucket, Key=self._key(name))["Body"].read()
        except client.exceptions.NoSuchKey:
            return None

    def list(self) -> list[str]:
        client = self._client()
        resp = client.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        return [
            obj["Key"].rsplit("/", 1)[-1]
            for obj in resp.get("Contents", [])
            if obj["Key"].endswith(".dna")
        ]


def backend_from_uri(uri: str) -> SyncBackend:
    """Route a location to a backend.

    - ``s3://bucket/prefix``      -> S3/R2 (boto3)
    - ``http(s)://host/path``     -> HTTP object store
    - anything else (opt. ``dir:``) -> a local directory (bring-your-own-storage)
    """
    if uri.startswith("s3://"):
        return S3Backend(uri)
    if uri.startswith(("http://", "https://")):
        return HttpBackend(uri)
    if uri.startswith("dir:"):
        uri = uri[4:]
    return LocalDirBackend(uri)
