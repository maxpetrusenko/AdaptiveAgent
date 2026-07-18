"""Provider protocols for replaceable embedding and native retrieval implementations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.knowledge.models import (
    EmbeddingIdentity,
    IndexedChunk,
    IndexManifest,
    SearchHit,
    SearchRequest,
)


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class NativeRetriever(Protocol):
    def replace_index(
        self,
        manifest: IndexManifest,
        chunks: list[IndexedChunk],
    ) -> None: ...

    def search(self, request: SearchRequest) -> list[SearchHit]: ...
