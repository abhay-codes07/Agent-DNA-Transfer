"""Embeddings. Local by default ($0); the dependency-free hashing embedder is the floor.

`get_embedder(config)` policy:
- provider "hashing"            -> HashingEmbedder (always available, offline, deterministic)
- provider "local"/"fastembed" -> try fastembed bge-small; fall back to HashingEmbedder if
  fastembed isn't installed (so a fresh machine still works at $0, offline).
"""

from __future__ import annotations

from .base import Embedder, cosine, from_bytes, normalize, to_bytes
from .hashing import HashingEmbedder

__all__ = [
    "Embedder",
    "HashingEmbedder",
    "get_embedder",
    "cosine",
    "normalize",
    "to_bytes",
    "from_bytes",
]


def get_embedder(config=None) -> Embedder:  # noqa: ANN001
    """Pick an embedder from config, degrading gracefully to the offline floor."""
    provider = getattr(config, "embeddings_provider", "local") if config else "local"
    if provider in ("local", "fastembed"):
        try:
            from .local import LocalEmbedder

            model = getattr(config, "local_embed_model", "BAAI/bge-small-en-v1.5")
            return LocalEmbedder(model)
        except Exception:
            # fastembed missing or model download failed -> stay $0 and offline.
            return HashingEmbedder()
    return HashingEmbedder()
