"""Deterministic test and OpenAI-compatible production embedding adapters."""

from __future__ import annotations

import math
import re
from hashlib import sha256
from typing import Any

import httpx

from app.knowledge.lineage import normalize_text
from app.knowledge.models import EmbeddingIdentity

TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)


class DeterministicTestEmbedder:
    """Feature-hash embedder for deterministic tests, never production semantics."""

    def __init__(self, *, dimensions: int = 32, revision: str = "fixture-v1") -> None:
        self._identity = EmbeddingIdentity(
            provider="deterministic-test",
            model="feature-hash",
            dimensions=dimensions,
            revision=revision,
        )

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        tokens = TOKEN_PATTERN.findall(normalize_text(text).lower())
        if not tokens:
            tokens = [normalize_text(text) or "<empty>"]
        vector = [0.0] * self.identity.dimensions
        for token in tokens:
            digest = sha256(token.encode()).digest()
            index = int.from_bytes(digest[:8], "big") % self.identity.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            fallback = sha256(normalize_text(text).encode()).digest()
            vector[int.from_bytes(fallback[:8], "big") % self.identity.dimensions] = 1.0
            norm = 1.0
        return [value / norm for value in vector]


class OpenAICompatibleEmbeddingProvider:
    """Adapter for providers implementing the OpenAI embeddings HTTP contract."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        revision: str = "unspecified",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not api_key.strip():
            raise ValueError("embedding base URL and API key are required")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._client = client
        self._identity = EmbeddingIdentity(
            provider="openai-compatible",
            model=model,
            dimensions=dimensions,
            revision=revision,
        )

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.identity.model,
            "input": texts,
            "dimensions": self.identity.dimensions,
        }
        if self._client is not None:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                headers=self._headers(),
                json=payload,
                timeout=self._timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._base_url}/embeddings",
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout,
                )
        response.raise_for_status()
        return self._parse_vectors(response.json(), expected_count=len(texts))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _parse_vectors(self, payload: dict[str, Any], *, expected_count: int) -> list[list[float]]:
        items = payload.get("data")
        if not isinstance(items, list) or len(items) != expected_count:
            raise ValueError("embedding response count mismatch")
        ordered: list[list[float] | None] = [None] * expected_count
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                raise ValueError("embedding response index is invalid")
            index = item["index"]
            raw_vector = item.get("embedding")
            if (
                index < 0
                or index >= expected_count
                or ordered[index] is not None
                or not isinstance(raw_vector, list)
                or len(raw_vector) != self.identity.dimensions
            ):
                raise ValueError("embedding response dimension or index mismatch")
            vector = [float(value) for value in raw_vector]
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("embedding response contains a non-finite value")
            ordered[index] = vector
        if any(vector is None for vector in ordered):
            raise ValueError("embedding response is incomplete")
        return [vector for vector in ordered if vector is not None]
