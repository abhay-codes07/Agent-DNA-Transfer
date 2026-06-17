"""LocalEmbedder — optional fastembed (bge-small) adapter (ADR-017).

Used when `fastembed` is installed and embeddings_provider is "local"/"fastembed". Lazily
imported so the core never hard-depends on it. If unavailable, the factory falls back to the
dependency-free HashingEmbedder — keeping the product usable and $0 on any machine.
"""

from __future__ import annotations

from .base import normalize


class LocalEmbedder:
    """bge-small-en-v1.5 (384-dim) via fastembed ONNX, on CPU, no API cost."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding  # lazy; raises ImportError if absent

        self._model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        self._dim = self._probe_dim()

    def _probe_dim(self) -> int:
        vec = next(iter(self._model.embed(["dimension probe"])))
        return len(list(vec))

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [normalize([float(x) for x in vec]) for vec in self._model.embed(texts)]
