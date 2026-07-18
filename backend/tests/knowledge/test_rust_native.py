from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from app.knowledge.models import IndexedChunk, IndexManifest, SearchRequest
from app.knowledge.retrieval import (
    DimensionMismatchError,
    EmbeddingMismatchError,
    StaleIndexError,
)
from app.knowledge.rust import (
    RustExtensionUnavailableError,
    RustHybridRetriever,
    RustRetrieverContractError,
)


class FakeManifest:
    def __init__(
        self,
        schema_version,
        version,
        corpus_hash,
        embedding_provider,
        embedding_model,
        dimensions,
        normalization="l2",
    ):
        self.schema_version = schema_version
        self.version = version
        self.corpus_hash = corpus_hash
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.dimensions = dimensions
        self.normalization = normalization


class FakeChunk:
    def __init__(self, chunk_id, tenant_id, text, source_uri, vector):
        self.chunk_id = chunk_id
        self.tenant_id = tenant_id
        self.text = text
        self.source_uri = source_uri
        self.vector = vector


class FakeNativeIndex:
    def __init__(self, chunks):
        self.chunks = chunks
        self.raise_on_search = False

    def search(self, query_text, query_vector, tenant_id, limit):
        if self.raise_on_search:
            raise ValueError("native contract broke")
        chunk = next(chunk for chunk in self.chunks if chunk.tenant_id == tenant_id)
        return [
            SimpleNamespace(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                source_uri=chunk.source_uri,
                dense_score=0.95,
                dense_rank=1,
                bm25_score=1.25,
                bm25_rank=1,
                rrf_score=2 / 61,
            )
        ][:limit]


class FakeHybridIndex:
    last_build = None

    @classmethod
    def build(cls, root, manifest, chunks):
        cls.last_build = (root, manifest, chunks)
        return FakeNativeIndex(chunks)


FAKE_EXTENSION = SimpleNamespace(
    IndexManifest=FakeManifest,
    ChunkRecord=FakeChunk,
    HybridIndex=FakeHybridIndex,
)


def manifest() -> IndexManifest:
    return IndexManifest(
        index_version="index-v1",
        embedding_fingerprint="embedding-v1",
        dimensions=2,
    )


def chunk() -> IndexedChunk:
    return IndexedChunk(
        tenant_id="tenant-a",
        source_id="source-a",
        chunk_id="chunk-a",
        content_hash="hash-a",
        text="durable checkpoint",
        embedding=(1.0, 0.0),
    )


def request(**overrides) -> SearchRequest:
    values = {
        "tenant_id": "tenant-a",
        "index_version": "index-v1",
        "embedding_fingerprint": "embedding-v1",
        "query_text": "checkpoint",
        "query_embedding": (1.0, 0.0),
        "top_k": 5,
    }
    values.update(overrides)
    return SearchRequest(**values)


def test_rust_wrapper_maps_contract_and_preserves_native_proof(tmp_path):
    retriever = RustHybridRetriever(tmp_path, extension=FAKE_EXTENSION)
    retriever.replace_index(manifest(), [chunk()])

    _root, native_manifest, native_chunks = FakeHybridIndex.last_build
    assert native_manifest.version == "index-v1"
    assert native_manifest.embedding_model == "embedding-v1"
    assert native_manifest.dimensions == 2
    assert len(native_manifest.corpus_hash) == 64
    assert native_chunks[0].tenant_id == "tenant-a"
    assert native_chunks[0].chunk_id.endswith("chunk-a")

    hits = retriever.search(request())
    assert len(hits) == 1
    assert hits[0].tenant_id == "tenant-a"
    assert hits[0].source_id == "source-a"
    assert hits[0].content_hash == "hash-a"
    assert hits[0].dense_score == pytest.approx(0.95)
    assert hits[0].lexical_score == pytest.approx(1.25)
    assert hits[0].dense_rank == 1
    assert hits[0].lexical_rank == 1


def test_rust_wrapper_fails_closed_on_state_and_native_contract_errors(tmp_path):
    retriever = RustHybridRetriever(tmp_path, extension=FAKE_EXTENSION)
    retriever.replace_index(manifest(), [chunk()])

    with pytest.raises(StaleIndexError):
        retriever.search(request(index_version="stale"))
    with pytest.raises(EmbeddingMismatchError):
        retriever.search(request(embedding_fingerprint="other"))
    with pytest.raises(DimensionMismatchError):
        retriever.search(request(query_embedding=(1.0,)))

    retriever._index.raise_on_search = True
    with pytest.raises(RustRetrieverContractError, match="native contract broke"):
        retriever.search(request())


def test_rust_wrapper_has_typed_missing_extension_error(monkeypatch, tmp_path):
    def missing(_name):
        raise ModuleNotFoundError("adaptive_retrieval")

    monkeypatch.setattr(importlib, "import_module", missing)
    with pytest.raises(RustExtensionUnavailableError, match="maturin develop"):
        RustHybridRetriever(tmp_path)


def test_installed_abi3_extension_round_trip(tmp_path):
    extension = pytest.importorskip(
        "adaptive_retrieval",
        reason=(
            "install with: cd native/adaptive_retrieval && "
            "uvx --from 'maturin>=1.14,<2' maturin develop --release --locked"
        ),
    )
    retriever = RustHybridRetriever(tmp_path, extension=extension)
    retriever.replace_index(manifest(), [chunk()])

    hits = retriever.search(request())

    assert [hit.chunk_id for hit in hits] == ["chunk-a"]
    assert hits[0].tenant_id == "tenant-a"
    assert hits[0].dense_rank == 1
    assert hits[0].lexical_rank == 1


def test_installed_extension_accepts_empty_active_generation(tmp_path):
    extension = pytest.importorskip("adaptive_retrieval")
    retriever = RustHybridRetriever(tmp_path, extension=extension)
    empty_manifest = IndexManifest(
        index_version="empty-v1",
        embedding_fingerprint="fixture:empty",
        dimensions=2,
    )

    retriever.replace_index(empty_manifest, [])
    hits = retriever.search(
        SearchRequest(
            tenant_id="tenant-a",
            index_version=empty_manifest.index_version,
            embedding_fingerprint=empty_manifest.embedding_fingerprint,
            query_text="anything",
            query_embedding=(1.0, 0.0),
            top_k=5,
        )
    )

    assert hits == []
