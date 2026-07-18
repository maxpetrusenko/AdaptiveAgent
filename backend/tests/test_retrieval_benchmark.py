from __future__ import annotations

import pytest

from app.benchmarks.retrieval import RetrievalParityError, run_retrieval_benchmark
from app.benchmarks.retrieval_cli import build_fixture
from app.knowledge.models import IndexedChunk, IndexManifest, SearchRequest
from app.knowledge.retrieval import ExactHybridRetriever


def fixture_data():
    manifest = IndexManifest("index-v1", "embedding-v1", 2)
    chunks = [
        IndexedChunk(
            tenant_id="tenant-a",
            source_id="source-a",
            chunk_id="a",
            content_hash="hash-a",
            text="durable checkpoint",
            embedding=(1.0, 0.0),
        ),
        IndexedChunk(
            tenant_id="tenant-a",
            source_id="source-b",
            chunk_id="b",
            content_hash="hash-b",
            text="promotion authority",
            embedding=(0.8, 0.2),
        ),
    ]
    requests = [
        SearchRequest(
            tenant_id="tenant-a",
            index_version="index-v1",
            embedding_fingerprint="embedding-v1",
            query_text="checkpoint",
            query_embedding=(1.0, 0.0),
            top_k=2,
        )
    ]
    return manifest, chunks, requests


class ReversedRetriever(ExactHybridRetriever):
    def search(self, request):
        return list(reversed(super().search(request)))


def ticking_clock():
    values = iter(range(0, 1_000_000_000, 1_000_000))
    return lambda: next(values)


def test_benchmark_proves_parity_before_reporting_distribution_metadata():
    manifest, chunks, requests = fixture_data()
    report = run_retrieval_benchmark(
        rust_retriever=ExactHybridRetriever(),
        manifest=manifest,
        chunks=chunks,
        requests=requests,
        iterations=3,
        clock_ns=ticking_clock(),
        commit_sha="abc123",
        machine={"os": "fixture", "arch": "fixture", "python": "3.11"},
    )

    assert report["parity"] == {
        "passed": True,
        "queries": 1,
        "ranked_hits_compared": 2,
    }
    assert report["commit"] == "abc123"
    assert report["corpus"]["chunk_count"] == 2
    assert report["corpus"]["tenant_count"] == 1
    assert len(report["corpus"]["sha256"]) == 64
    for engine in ("python_oracle", "rust_native"):
        assert report[engine]["samples"] == 3
        assert report[engine]["p50_ms"] == pytest.approx(1.0)
        assert report[engine]["p95_ms"] == pytest.approx(1.0)
        assert report[engine]["p99_ms"] == pytest.approx(1.0)
        assert report[engine]["throughput_qps"] == pytest.approx(1000.0)
    assert report["comparison"] == {
        "p50_speedup": pytest.approx(1.0),
        "throughput_speedup": pytest.approx(1.0),
    }


def test_benchmark_excludes_configured_warmups_from_reported_samples():
    manifest, chunks, requests = fixture_data()
    report = run_retrieval_benchmark(
        rust_retriever=ExactHybridRetriever(),
        manifest=manifest,
        chunks=chunks,
        requests=requests,
        iterations=2,
        warmups=3,
        clock_ns=ticking_clock(),
    )

    assert report["methodology"]["warmups"] == 3
    assert report["methodology"]["timed_iterations"] == 2
    assert report["python_oracle"]["samples"] == 2
    assert report["rust_native"]["samples"] == 2


def test_benchmark_refuses_to_time_non_parity_implementations():
    manifest, chunks, requests = fixture_data()
    with pytest.raises(RetrievalParityError, match="ranked chunk ids differ"):
        run_retrieval_benchmark(
            rust_retriever=ReversedRetriever(),
            manifest=manifest,
            chunks=chunks,
            requests=requests,
            iterations=1,
        )


def test_benchmark_fixture_is_deterministic_and_tenant_scoped():
    first = build_fixture(chunk_count=100, dimensions=16, query_count=4, seed=7)
    second = build_fixture(chunk_count=100, dimensions=16, query_count=4, seed=7)

    assert first == second
    manifest, chunks, requests = first
    assert manifest.dimensions == 16
    assert len(chunks) == 100
    assert len(requests) == 4
    assert {chunk.tenant_id for chunk in chunks} == {"benchmark-tenant"}
    assert {request.tenant_id for request in requests} == {"benchmark-tenant"}
