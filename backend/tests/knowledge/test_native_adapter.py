import threading

import pytest

from app.knowledge.models import SearchRequest
from app.knowledge.native import AsyncNativeRetrieverAdapter


class RecordingNativeRetriever:
    def __init__(self) -> None:
        self.thread_ids: list[int] = []

    def replace_index(self, manifest, chunks) -> None:
        self.thread_ids.append(threading.get_ident())

    def search(self, request):
        self.thread_ids.append(threading.get_ident())
        return []


@pytest.mark.asyncio
async def test_native_adapter_offloads_blocking_search_from_event_loop_thread():
    native = RecordingNativeRetriever()
    adapter = AsyncNativeRetrieverAdapter(native, max_concurrency=2)
    event_loop_thread = threading.get_ident()

    result = await adapter.search(
        SearchRequest(
            tenant_id="tenant-a",
            index_version="index-v1",
            embedding_fingerprint="embedding-v1",
            query_text="database",
            query_embedding=(1.0, 0.0),
            top_k=3,
        )
    )

    assert result == []
    assert native.thread_ids
    assert native.thread_ids[0] != event_loop_thread
