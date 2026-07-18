import pytest

from app.knowledge.embeddings import DeterministicTestEmbedder
from app.knowledge.metrics import evaluate_golden_retrieval
from app.knowledge.models import GoldenQuery, IndexedChunk, IndexManifest
from app.knowledge.native import AsyncNativeRetrieverAdapter
from app.knowledge.retrieval import ExactHybridRetriever
from app.knowledge.service import KnowledgeRetrievalService, NoEvidenceError


@pytest.mark.asyncio
async def test_golden_retrieval_reports_recall_and_reciprocal_rank():
    embedder = DeterministicTestEmbedder(dimensions=32)
    texts = [
        "Database migration requires a backup and rollback plan.",
        "Operator promotion requires sealed validation evidence.",
        "Citrus trees need regular watering.",
    ]
    vectors = await embedder.embed(texts)
    chunks = [
        IndexedChunk(
            tenant_id="tenant-a",
            source_id=f"source-{index}",
            chunk_id=f"chunk-{index}",
            content_hash=f"hash-{index}",
            text=text,
            embedding=tuple(vectors[index]),
        )
        for index, text in enumerate(texts)
    ]
    native = ExactHybridRetriever()
    native.replace_index(
        IndexManifest(
            index_version="index-v1",
            embedding_fingerprint=embedder.identity.fingerprint,
            dimensions=embedder.identity.dimensions,
        ),
        chunks,
    )
    service = KnowledgeRetrievalService(
        embedder=embedder,
        retriever=AsyncNativeRetrieverAdapter(native),
        index_version="index-v1",
    )

    metrics = await evaluate_golden_retrieval(
        service,
        [
            GoldenQuery(
                query_id="migration",
                tenant_id="tenant-a",
                query_text="database migration backup",
                relevant_chunk_ids=("chunk-0",),
            ),
            GoldenQuery(
                query_id="promotion",
                tenant_id="tenant-a",
                query_text="operator promotion validation evidence",
                relevant_chunk_ids=("chunk-1",),
            ),
        ],
        top_k=3,
    )

    assert metrics.query_count == 2
    assert metrics.recall_at_k == pytest.approx(1.0)
    assert metrics.hit_rate == pytest.approx(1.0)
    assert metrics.mean_reciprocal_rank == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_search_service_fails_closed_when_tenant_has_no_evidence():
    embedder = DeterministicTestEmbedder(dimensions=8)
    native = ExactHybridRetriever()
    native.replace_index(
        IndexManifest(
            index_version="index-v1",
            embedding_fingerprint=embedder.identity.fingerprint,
            dimensions=embedder.identity.dimensions,
        ),
        [],
    )
    service = KnowledgeRetrievalService(
        embedder=embedder,
        retriever=AsyncNativeRetrieverAdapter(native),
        index_version="index-v1",
    )

    with pytest.raises(NoEvidenceError):
        await service.search(
            tenant_id="tenant-a",
            query_text="database migration",
            top_k=3,
        )
