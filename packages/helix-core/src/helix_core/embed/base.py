"""Embedder interface (ADR-006).

Default is LOCAL (fastembed bge-small) — the highest-volume call must be free. Cloud
embeddings are opt-in. The embedding space (provider/model/dim) is pinned per strand; a
mismatch on import triggers a tracked re-embed, never a silent mix.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into normalized vectors."""
        ...


class LocalEmbedder:
    """fastembed BAAI/bge-small-en-v1.5 (384-dim, CPU, $0). Implemented in Phase 1."""

    _model = "BAAI/bge-small-en-v1.5"
    _dim = 384

    @property
    def model(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("Phase 1: load fastembed model lazily; cache on disk")
