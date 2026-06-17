"""HashingEmbedder — the dependency-free, deterministic, offline default.

Uses the hashing trick over word tokens + character n-grams, accumulated into a fixed-dim
vector with signed buckets, then L2-normalized. No model download, no network, fully
deterministic (so tests are hermetic). Quality is lexical/character-level — good enough for
recalling short personal/project facts at $0. fastembed (bge-small) is the optional upgrade.
"""

from __future__ import annotations

import hashlib
import re

from .base import normalize

_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def model(self) -> str:
        return f"helix-hashing-v1-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for feat in _features(text):
            digest = hashlib.blake2s(feat.encode("utf-8"), digest_size=8).digest()
            h = int.from_bytes(digest, "big")
            idx = h % self._dim
            sign = 1.0 if (h >> 33) & 1 else -1.0
            # word features carry more signal than character n-grams
            weight = 2.0 if feat.startswith("w:") else 1.0
            vec[idx] += sign * weight
        return normalize(vec)


def _features(text: str):
    t = text.lower()
    words = _WORD.findall(t)
    for w in words:
        yield "w:" + w  # weighted word token
    padded = f" {t} "
    for n in (3, 4):
        for i in range(len(padded) - n + 1):
            yield padded[i : i + n]  # char n-gram
