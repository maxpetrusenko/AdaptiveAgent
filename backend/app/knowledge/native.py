"""Async boundary for synchronous native retrieval implementations."""

from __future__ import annotations

import asyncio

from app.knowledge.models import (
    IndexedChunk,
    IndexManifest,
    SearchHit,
    SearchRequest,
)
from app.knowledge.protocols import NativeRetriever


class AsyncNativeRetrieverAdapter:
    """Bound native CPU work and keep it off the application event loop."""

    def __init__(self, native: NativeRetriever, *, max_concurrency: int = 4) -> None:
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        self._native = native
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def replace_index(
        self,
        manifest: IndexManifest,
        chunks: list[IndexedChunk],
    ) -> None:
        async with self._semaphore:
            await asyncio.to_thread(self._native.replace_index, manifest, chunks)

    async def search(self, request: SearchRequest) -> list[SearchHit]:
        async with self._semaphore:
            return await asyncio.to_thread(self._native.search, request)
