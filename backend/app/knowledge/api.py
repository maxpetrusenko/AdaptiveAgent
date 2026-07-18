"""Injectable FastAPI contracts for knowledge ingest, search, delete, and health."""

from __future__ import annotations

import asyncio
import math
import weakref
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.knowledge.lineage import (
    normalize_text,
    stable_chunk_id,
    stable_content_hash,
    stable_source_id,
)
from app.knowledge.models import IndexedChunk, SearchHit
from app.knowledge.native import AsyncNativeRetrieverAdapter
from app.knowledge.persistence import (
    GenerationSnapshot,
    IndexMutationResult,
    KnowledgeRepository,
)
from app.knowledge.protocols import EmbeddingProvider
from app.knowledge.retrieval import RetrievalContractError
from app.knowledge.service import KnowledgeRetrievalService, NoEvidenceError


class _RetrieverMutationState:
    def __init__(self) -> None:
        self.access_lock = asyncio.Lock()
        self.loaded_generation_id: str | None = None


_retriever_mutations: weakref.WeakKeyDictionary[
    AsyncNativeRetrieverAdapter,
    _RetrieverMutationState,
] = weakref.WeakKeyDictionary()


class KnowledgeIndexManager:
    """Coordinates canonical snapshots, embedding, native build, and activation."""

    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        embedder: EmbeddingProvider,
        retriever: AsyncNativeRetrieverAdapter,
        chunk_size_chars: int = 1000,
        max_source_chars: int = 100_000,
    ) -> None:
        if chunk_size_chars <= 0 or max_source_chars <= 0:
            raise ValueError("knowledge text bounds must be positive")
        self._repository = repository
        self._embedder = embedder
        self._retriever = retriever
        self._retriever_mutation = _retriever_mutations.setdefault(
            retriever,
            _RetrieverMutationState(),
        )
        self._chunk_size_chars = chunk_size_chars
        self._max_source_chars = max_source_chars

    async def ingest(
        self,
        *,
        tenant_id: str,
        external_id: str,
        text: str,
    ) -> IndexMutationResult:
        normalized = normalize_text(text)
        if not normalized:
            raise ValueError("source text is required")
        if len(normalized) > self._max_source_chars:
            raise ValueError("source text exceeds configured bound")
        source_id = stable_source_id(tenant_id=tenant_id, external_id=external_id)
        texts = self._chunk_text(normalized)
        vectors = await self._embedder.embed(texts)
        if len(vectors) != len(texts):
            raise ValueError("embedding provider returned an invalid batch")
        identity = self._embedder.identity
        if any(
            len(vector) != identity.dimensions
            or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ValueError("embedding provider returned an invalid dimension or value")
        chunks = [
            IndexedChunk(
                tenant_id=tenant_id,
                source_id=source_id,
                chunk_id=stable_chunk_id(source_id, ordinal=index, text=chunk_text),
                content_hash=stable_content_hash(chunk_text),
                text=chunk_text,
                embedding=tuple(vectors[index]),
            )
            for index, chunk_text in enumerate(texts)
        ]
        result, snapshot = await self._repository.prepare_ingest(
            tenant_id=tenant_id,
            external_id=external_id,
            source_content_hash=stable_content_hash(normalized),
            embedding_fingerprint=identity.fingerprint,
            dimensions=identity.dimensions,
            chunks=chunks,
        )
        await self._build_and_activate(snapshot)
        return result

    async def delete_source(
        self,
        *,
        tenant_id: str,
        external_id: str,
    ) -> IndexMutationResult:
        result, snapshot = await self._repository.prepare_delete(
            tenant_id=tenant_id,
            external_id=external_id,
        )
        await self._build_and_activate(snapshot)
        return result

    async def recover_building(self) -> list[str]:
        recovered: list[str] = []
        identity = self._embedder.identity
        for snapshot in await self._repository.list_building():
            if (
                snapshot.manifest.embedding_fingerprint != identity.fingerprint
                or snapshot.manifest.dimensions != identity.dimensions
            ):
                continue
            await self._build_and_activate(snapshot)
            recovered.append(snapshot.generation_id)
        return recovered

    async def load_active(self) -> str | None:
        async with self._retriever_mutation.access_lock:
            snapshot = await self._repository.get_active_snapshot()
            if snapshot is None:
                return None
            await self._replace_index(snapshot)
            return snapshot.generation_id

    async def search(
        self,
        *,
        tenant_id: str,
        query_text: str,
        top_k: int = 5,
    ) -> list[SearchHit]:
        async with self._retriever_mutation.access_lock:
            snapshot = await self._repository.get_active_snapshot()
            if snapshot is None:
                raise NoEvidenceError("knowledge index is empty")
            service = KnowledgeRetrievalService(
                embedder=self._embedder,
                retriever=self._retriever,
                index_version=snapshot.manifest.index_version,
            )
            return await service.search(
                tenant_id=tenant_id,
                query_text=query_text,
                top_k=top_k,
            )

    async def _build_and_activate(self, snapshot: GenerationSnapshot) -> None:
        async with self._retriever_mutation.access_lock:
            await self._replace_index(snapshot)
            if snapshot.status == "building":
                await self._repository.activate(snapshot.generation_id)
            active = await self._repository.get_active_snapshot()
            if (
                active is not None
                and self._retriever_mutation.loaded_generation_id
                != active.generation_id
            ):
                await self._replace_index(active)

    async def _replace_index(self, snapshot: GenerationSnapshot) -> None:
        await self._retriever.replace_index(snapshot.manifest, list(snapshot.chunks))
        self._retriever_mutation.loaded_generation_id = snapshot.generation_id

    def _chunk_text(self, text: str) -> list[str]:
        return [
            text[start : start + self._chunk_size_chars].strip()
            for start in range(0, len(text), self._chunk_size_chars)
            if text[start : start + self._chunk_size_chars].strip()
        ]


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=200)
    external_id: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)


class DeleteSourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=200)
    external_id: str = Field(min_length=1, max_length=500)


class IndexMutationResponse(BaseModel):
    generation_id: str
    source_id: str
    index_version: str
    changed: bool
    chunk_count: int


class SearchRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=100)


class SearchHitResponse(BaseModel):
    tenant_id: str
    source_id: str
    chunk_id: str
    citation_id: str
    content_hash: str
    text: str
    fusion_score: float
    dense_score: float
    lexical_score: float
    dense_rank: int | None
    lexical_rank: int | None
    index_version: str
    embedding_fingerprint: str


class SearchResponse(BaseModel):
    hits: list[SearchHitResponse]


class IndexHealthResponse(BaseModel):
    status: str
    active_generation_id: str | None
    active_index_version: str | None
    building_count: int
    chunk_count: int


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, NoEvidenceError):
        return HTTPException(
            status_code=404,
            detail={"code": "no_evidence", "message": str(error)},
        )
    if isinstance(error, RetrievalContractError):
        return HTTPException(
            status_code=409,
            detail={"code": "index_contract_error", "message": str(error)},
        )
    if isinstance(error, (ValueError, LookupError)):
        return HTTPException(
            status_code=422,
            detail={"code": "invalid_knowledge_request", "message": str(error)},
        )
    raise error


def create_knowledge_router(
    manager: KnowledgeIndexManager,
    repository: KnowledgeRepository,
    *,
    operator_guard: Callable[..., Any] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
    protected = [Depends(operator_guard)] if operator_guard is not None else []

    @router.post(
        "/ingest",
        response_model=IndexMutationResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=protected,
    )
    async def ingest(request: IngestRequest, response: Response):
        try:
            result = await manager.ingest(
                tenant_id=request.tenant_id,
                external_id=request.external_id,
                text=request.text,
            )
        except Exception as error:
            raise _http_error(error) from error
        if not result.changed:
            response.status_code = status.HTTP_200_OK
        return IndexMutationResponse(**result.__dict__)

    @router.delete(
        "/sources",
        response_model=IndexMutationResponse,
        dependencies=protected,
    )
    async def delete_source(request: DeleteSourceRequest):
        try:
            result = await manager.delete_source(
                tenant_id=request.tenant_id,
                external_id=request.external_id,
            )
        except Exception as error:
            raise _http_error(error) from error
        return IndexMutationResponse(**result.__dict__)

    @router.post(
        "/search",
        response_model=SearchResponse,
        dependencies=protected,
    )
    async def search(request: SearchRequestBody):
        try:
            hits = await manager.search(
                tenant_id=request.tenant_id,
                query_text=request.query,
                top_k=request.top_k,
            )
        except Exception as error:
            raise _http_error(error) from error
        return SearchResponse(
            hits=[
                SearchHitResponse(
                    tenant_id=hit.tenant_id,
                    source_id=hit.source_id,
                    chunk_id=hit.chunk_id,
                    citation_id=hit.chunk_id,
                    content_hash=hit.content_hash,
                    text=hit.text,
                    fusion_score=hit.fusion_score,
                    dense_score=hit.dense_score,
                    lexical_score=hit.lexical_score,
                    dense_rank=hit.dense_rank,
                    lexical_rank=hit.lexical_rank,
                    index_version=hit.index_version,
                    embedding_fingerprint=hit.embedding_fingerprint,
                )
                for hit in hits
            ]
        )

    @router.get("/index/health", response_model=IndexHealthResponse)
    async def index_health():
        health = await repository.health()
        return IndexHealthResponse(**health.__dict__)

    return router
