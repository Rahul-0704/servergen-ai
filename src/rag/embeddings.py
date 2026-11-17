"""
ServerGen AI — Local Vector Embedding Engine.

Provides embedding generation via local Ollama or an autonomous local deterministic
fallback vectorizer. Includes cosine similarity ranking and dimension validation.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from abc import ABC, abstractmethod

import httpx

from src.core.config import get_settings

logger = logging.getLogger("servergen.rag.embeddings")


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two float vectors [-1.0, 1.0]."""
    if len(v1) != len(v2) or not v1:
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


class BaseEmbeddingProvider(ABC):
    """Abstract vector embedding generator interface."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the active embedding model."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensions of generated vectors."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate a single vector embedding."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of texts."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check provider connectivity and model availability."""


class LocalDeterministicEmbeddingProvider(BaseEmbeddingProvider):
    """
    Autonomous deterministic semantic hashing vectorizer.
    Guarantees consistent, normalized vectors of exact target dimension (e.g. 768)
    without requiring external model downloads or internet access.
    """

    def __init__(self, dimensions: int = 768) -> None:
        self._dimensions = dimensions
        self._model_name = "local-deterministic-hash"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _generate(self, text: str) -> list[float]:
        """Compute an L2-normalized vector using sliding character n-grams and hashing."""
        words = text.lower().split()
        vec = [0.0] * self._dimensions
        if not words:
            return vec

        for word in words:
            # Word level hash
            h1 = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            idx1 = h1 % self._dimensions
            vec[idx1] += 1.0

            # Character 3-gram hashes
            for i in range(max(1, len(word) - 2)):
                gram = word[i : i + 3]
                h_gram = int(hashlib.sha256(gram.encode("utf-8")).hexdigest(), 16)
                idx_g = h_gram % self._dimensions
                vec[idx_g] += 0.5

        # L2 normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [round(x / norm, 6) for x in vec]
        return vec

    async def embed_text(self, text: str) -> list[float]:
        return self._generate(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._generate(t) for t in texts]

    async def is_available(self) -> bool:
        return True


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """
    Ollama-backed local embedding provider.
    Connects to Ollama /api/embeddings or /api/embed. Falls back gracefully
    to LocalDeterministicEmbeddingProvider if Ollama or the model is missing.
    """

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.RAG_EMBEDDING_MODEL
        self._base_url = base_url or settings.OLLAMA_BASE_URL
        self._dimensions = dimensions or settings.RAG_EMBEDDING_DIMENSIONS
        self._fallback = LocalDeterministicEmbeddingProvider(dimensions=self._dimensions)
        self._is_online: bool | None = None
        self._last_checked: float = 0.0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def is_available(self) -> bool:
        """Check if Ollama is reachable and has the requested embedding model."""
        now = time.monotonic()
        if self._is_online is not None and (now - self._last_checked < 10.0):
            return self._is_online

        self._last_checked = now
        try:
            timeout = httpx.Timeout(2.0, connect=0.5)
            async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
                resp = await client.get("/api/tags")
                if resp.status_code == 200:
                    models = [m.get("name", "") for m in resp.json().get("models", [])]
                    self._is_online = any(self._model_name in m for m in models)
                    return self._is_online
        except Exception as exc:
            logger.debug("Ollama is_available probe failed: %s", exc)
        self._is_online = False
        return False

    async def embed_text(self, text: str) -> list[float]:
        """Request embedding from Ollama or fallback immediately to deterministic vectorizer."""
        if not await self.is_available():
            return await self._fallback.embed_text(text)

        try:
            timeout = httpx.Timeout(15.0, connect=1.0)
            async with httpx.AsyncClient(base_url=self._base_url, timeout=timeout) as client:
                resp = await client.post(
                    "/api/embeddings",
                    json={"model": self._model_name, "prompt": text},
                )
                if resp.status_code == 200:
                    vec = resp.json().get("embedding", [])
                    if isinstance(vec, list) and len(vec) > 0:
                        return [float(x) for x in vec]
        except Exception as exc:
            logger.debug("Ollama embedding call failed (%s); switching to local vectorizer", exc)
            self._is_online = False

        return await self._fallback.embed_text(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embedding generation with fallback."""
        if not await self.is_available():
            return await self._fallback.embed_batch(texts)

        results: list[list[float]] = []
        for text in texts:
            vec = await self.embed_text(text)
            results.append(vec)
        return results


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Return default configured embedding provider."""
    return OllamaEmbeddingProvider()
