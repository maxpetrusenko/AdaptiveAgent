"""High-level semantic retrieval service with fail-closed no-hit behavior."""

from __future__ import annotations

from app.knowledge.models import SearchHit, SearchRequest
from app.knowledge.native import AsyncNativeRetrieverAdapter
from app.knowledge.protocols import EmbeddingProvider


class NoEvidenceError(LookupError):
    pass


class KnowledgeRetrievalService:
    def __init__(
        self,
        *,
        embedder: EmbeddingProvider,
        retriever: AsyncNativeRetrieverAdapter,
        index_version: str,
    ) -> None:
        if not index_version.strip():
            raise ValueError("index_version is required")
        self._embedder = embedder
        self._retriever = retriever
        self._index_version = index_version

    async def search(
        self,
        *,
        tenant_id: str,
        query_text: str,
        top_k: int = 5,
    ) -> list[SearchHit]:
        if not tenant_id.strip() or not query_text.strip():
            raise ValueError("tenant_id and query_text are required")
        vectors = await self._embedder.embed([query_text])
        if len(vectors) != 1:
            raise ValueError("embedding provider returned an invalid query batch")
        identity = self._embedder.identity
        if len(vectors[0]) != identity.dimensions:
            raise ValueError("embedding provider returned the wrong dimension")
        hits = await self._retriever.search(
            SearchRequest(
                tenant_id=tenant_id,
                index_version=self._index_version,
                embedding_fingerprint=identity.fingerprint,
                query_text=query_text,
                query_embedding=tuple(vectors[0]),
                top_k=top_k,
            )
        )
        if not hits:
            raise NoEvidenceError("no evidence matched the query")
        return hits
