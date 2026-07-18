import math

import pytest

from app.knowledge.models import IndexedChunk, IndexManifest, SearchRequest
from app.knowledge.retrieval import (
    DimensionMismatchError,
    EmbeddingMismatchError,
    ExactHybridRetriever,
    StaleIndexError,
    cosine_similarity,
)


def chunk(
    chunk_id: str,
    *,
    tenant_id: str,
    text: str,
    embedding: tuple[float, ...],
) -> IndexedChunk:
    return IndexedChunk(
        tenant_id=tenant_id,
        source_id=f"source-{chunk_id}",
        chunk_id=chunk_id,
        content_hash=f"hash-{chunk_id}",
        text=text,
        embedding=embedding,
    )


def manifest() -> IndexManifest:
    return IndexManifest(
        index_version="index-v1",
        embedding_fingerprint="embedding-v1",
        dimensions=2,
    )


def request(*, tenant_id: str = "tenant-a") -> SearchRequest:
    return SearchRequest(
        tenant_id=tenant_id,
        index_version="index-v1",
        embedding_fingerprint="embedding-v1",
        query_text="database migration",
        query_embedding=(1.0, 0.0),
        top_k=3,
    )


def test_exact_hybrid_search_filters_tenant_before_scoring_and_is_deterministic():
    retriever = ExactHybridRetriever()
    retriever.replace_index(
        manifest(),
        [
            chunk(
                "dense-and-lexical",
                tenant_id="tenant-a",
                text="database migration guide",
                embedding=(1.0, 0.0),
            ),
            chunk(
                "dense-only",
                tenant_id="tenant-a",
                text="deployment checklist",
                embedding=(0.99, 0.01),
            ),
            chunk(
                "cross-tenant",
                tenant_id="tenant-b",
                text="database migration secret",
                embedding=(1.0, 0.0),
            ),
        ],
    )

    first = retriever.search(request())
    second = retriever.search(request())

    assert [hit.chunk_id for hit in first] == ["dense-and-lexical", "dense-only"]
    assert first == second
    assert all(hit.tenant_id == "tenant-a" for hit in first)
    assert first[0].dense_rank == 1
    assert first[0].lexical_rank == 1
    assert first[0].fusion_score > first[1].fusion_score


def test_exact_dense_score_matches_brute_force_cosine_oracle():
    expected = (1 * 3 + 2 * 4) / (math.sqrt(5) * 5)
    assert cosine_similarity((1.0, 2.0), (3.0, 4.0)) == pytest.approx(expected)


def test_reference_retriever_rejects_stale_model_and_dimension_drift():
    retriever = ExactHybridRetriever()
    retriever.replace_index(
        manifest(),
        [chunk("one", tenant_id="tenant-a", text="database", embedding=(1.0, 0.0))],
    )

    with pytest.raises(StaleIndexError):
        retriever.search(
            SearchRequest(**{**request().__dict__, "index_version": "index-v0"})
        )
    with pytest.raises(EmbeddingMismatchError):
        retriever.search(
            SearchRequest(
                **{**request().__dict__, "embedding_fingerprint": "embedding-v2"}
            )
        )
    with pytest.raises(DimensionMismatchError):
        retriever.search(
            SearchRequest(**{**request().__dict__, "query_embedding": (1.0,)})
        )
