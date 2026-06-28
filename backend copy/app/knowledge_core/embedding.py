"""The single shared embedding path (EMBED_MODEL / EMBED_DIM).

No torch / sentence-transformers in the venv: embeddings are produced by the Weaviate
``text2vec-transformers`` sidecar (model sentence-transformers/all-MiniLM-L6-v2, dim 384). The
app calls the sidecar's ``POST /vectors`` endpoint, which returns one 384-dim vector per text.
Weaviate itself uses the same module to vectorize documents/queries, so app-side and
Weaviate-side vectors are comparable (GDPR: local, in-VPC, no external embedding API).

This is the ONE embedding service across all modules (AC-4) — obtained via
``get_embedding_service()``; modules never build their own.
"""

from __future__ import annotations

from functools import lru_cache

import httpx

from app.config import get_settings
from app.contracts import EMBED_DIM, Vector


class EmbeddingError(RuntimeError):
    pass


class EmbeddingServiceImpl:
    """Concrete EmbeddingService (satisfies the EmbeddingService Protocol)."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = (base_url or get_settings().t2v_url).rstrip("/")
        self._timeout = timeout

    def embed(self, texts: list[str]) -> list[Vector]:
        """Return one EMBED_DIM-dimensional vector per input text.

        Calls the t2v sidecar once per text (its /vectors endpoint embeds a single string per
        call). Synchronous by design — the frozen Protocol is sync, and callers on the hot path
        push embedding off-thread / off-hot-path as needed.
        """
        if not texts:
            return []
        url = f"{self._base_url}/vectors"
        out: list[Vector] = []
        with httpx.Client(timeout=self._timeout) as client:
            for text in texts:
                resp = client.post(url, json={"text": text})
                resp.raise_for_status()
                data = resp.json()
                vec = data.get("vector")
                if not isinstance(vec, list):
                    raise EmbeddingError(f"t2v returned no vector for input: {data!r}")
                if len(vec) != EMBED_DIM:
                    raise EmbeddingError(
                        f"t2v returned dim {len(vec)}, expected {EMBED_DIM} (EMBED_MODEL mismatch)"
                    )
                out.append([float(x) for x in vec])
        return out


@lru_cache
def get_embedding_service() -> EmbeddingServiceImpl:
    """The single shared EmbeddingService accessor (AC-4 discipline)."""
    return EmbeddingServiceImpl()
