"""Optional, end-to-end-encrypted team/multi-device sync (Phase 7, ADR-022/030).

Sync moves the **already-encrypted `.dna`** to a shared location — so the backend (a folder, a
cloud-synced directory, later an object store or relay) only ever sees ciphertext. The default
backend is bring-your-own-storage: a directory (e.g. a Dropbox/Drive/NFS-synced folder). Pull
reuses the Phase 4 merge, so two people's memories combine with conflict-aware dedup.
"""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn, Protocol, runtime_checkable


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


class S3Backend:
    """Object-store backend (S3/R2). Interface placeholder — wired in a later release."""

    def __init__(self, uri: str) -> None:
        self.uri = uri

    def _todo(self) -> NoReturn:
        raise NotImplementedError(
            "S3/R2 sync backend is not implemented yet; use a bring-your-own directory "
            "(e.g. a Dropbox/Drive-synced folder) for now."
        )

    def put(self, name: str, data: bytes) -> None:
        self._todo()

    def get(self, name: str) -> bytes | None:
        self._todo()

    def list(self) -> list[str]:
        self._todo()


def backend_from_uri(uri: str) -> SyncBackend:
    """`s3://…` -> S3Backend (stub); anything else (optionally `dir:`-prefixed) -> a directory."""
    if uri.startswith("s3://"):
        return S3Backend(uri)
    if uri.startswith("dir:"):
        uri = uri[4:]
    return LocalDirBackend(uri)
