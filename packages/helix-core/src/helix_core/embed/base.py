"""Embedder interface + vector helpers (ADR-006/ADR-017).

The default embedder is LOCAL and dependency-free (see hashing.py) so the $0/offline core runs
on a bare Python with no model download. fastembed (bge-small) is an optional accelerator
(local.py). The embedding space (provider/model/dim) is pinned per strand; a mismatch on
import triggers a tracked re-embed, never a silent mix.
"""

from __future__ import annotations

import array
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into L2-normalized vectors."""
        ...


# --- vector helpers (pure stdlib; vectors are stored as float32 bytes) ---


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    inv = 1.0 / norm
    return [v * inv for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Inputs are expected normalized, so this is a dot product."""
    return sum(x * y for x, y in zip(a, b))


def to_bytes(vec: list[float]) -> bytes:
    return array.array("f", vec).tobytes()


def from_bytes(data: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(data)
    return list(a)
