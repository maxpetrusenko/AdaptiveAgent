"""Correctness-first benchmark harness for Python and Rust hybrid retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import time
from collections.abc import Callable
from typing import Any

from app.knowledge.models import IndexedChunk, IndexManifest, SearchRequest
from app.knowledge.protocols import NativeRetriever
from app.knowledge.retrieval import ExactHybridRetriever


class RetrievalParityError(AssertionError):
    """Timing is invalid until the candidate agrees with the correctness oracle."""


def run_retrieval_benchmark(
    *,
    rust_retriever: NativeRetriever,
    manifest: IndexManifest,
    chunks: list[IndexedChunk],
    requests: list[SearchRequest],
    iterations: int = 100,
    warmups: int = 5,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    commit_sha: str | None = None,
    machine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if warmups < 0:
        raise ValueError("warmups must not be negative")
    if not requests:
        raise ValueError("at least one search request is required")

    oracle = ExactHybridRetriever()
    oracle.replace_index(manifest, chunks)
    rust_retriever.replace_index(manifest, chunks)
    parity = _assert_parity(oracle, rust_retriever, requests)

    _warm_up(oracle, requests, warmups)
    _warm_up(rust_retriever, requests, warmups)
    oracle_timings = _measure(oracle, requests, iterations, clock_ns)
    rust_timings = _measure(rust_retriever, requests, iterations, clock_ns)
    return {
        "schema_version": 1,
        "machine": machine or _machine_metadata(),
        "commit": commit_sha or _git_commit(),
        "corpus": _corpus_metadata(manifest, chunks),
        "parity": parity,
        "methodology": {
            "warmups": warmups,
            "timed_iterations": iterations,
            "clock": "time.perf_counter_ns",
            "order": "python_oracle_then_rust_native",
        },
        "python_oracle": oracle_timings,
        "rust_native": rust_timings,
        "comparison": {
            "p50_speedup": _ratio(
                oracle_timings["p50_ms"],
                rust_timings["p50_ms"],
            ),
            "throughput_speedup": _ratio(
                rust_timings["throughput_qps"],
                oracle_timings["throughput_qps"],
            ),
        },
    }


def _warm_up(
    retriever: NativeRetriever,
    requests: list[SearchRequest],
    iterations: int,
) -> None:
    for _ in range(iterations):
        for request in requests:
            retriever.search(request)


def _ratio(numerator: float | int, denominator: float | int) -> float:
    if denominator == 0:
        return float("inf")
    return float(numerator / denominator)


def _assert_parity(
    oracle: NativeRetriever,
    candidate: NativeRetriever,
    requests: list[SearchRequest],
) -> dict[str, Any]:
    compared = 0
    for request in requests:
        expected = oracle.search(request)
        actual = candidate.search(request)
        expected_ids = [hit.chunk_id for hit in expected]
        actual_ids = [hit.chunk_id for hit in actual]
        if actual_ids != expected_ids:
            raise RetrievalParityError(
                f"ranked chunk ids differ: expected {expected_ids}, received {actual_ids}"
            )
        for expected_hit, actual_hit in zip(expected, actual, strict=True):
            if (
                expected_hit.dense_rank != actual_hit.dense_rank
                or expected_hit.lexical_rank != actual_hit.lexical_rank
            ):
                raise RetrievalParityError(
                    f"per-leg ranks differ for chunk {expected_hit.chunk_id}"
                )
            if not math.isclose(
                expected_hit.dense_score,
                actual_hit.dense_score,
                rel_tol=1e-5,
                abs_tol=1e-6,
            ):
                raise RetrievalParityError(
                    f"dense score differs for chunk {expected_hit.chunk_id}"
                )
        compared += len(expected)
    return {
        "passed": True,
        "queries": len(requests),
        "ranked_hits_compared": compared,
    }


def _measure(
    retriever: NativeRetriever,
    requests: list[SearchRequest],
    iterations: int,
    clock_ns: Callable[[], int],
) -> dict[str, float | int]:
    durations_ms: list[float] = []
    for _ in range(iterations):
        for request in requests:
            started = clock_ns()
            retriever.search(request)
            elapsed = clock_ns() - started
            if elapsed < 0:
                raise ValueError("benchmark clock moved backwards")
            durations_ms.append(elapsed / 1_000_000)
    total_seconds = sum(durations_ms) / 1_000
    throughput = len(durations_ms) / total_seconds if total_seconds else float("inf")
    return {
        "samples": len(durations_ms),
        "p50_ms": _percentile(durations_ms, 0.50),
        "p95_ms": _percentile(durations_ms, 0.95),
        "p99_ms": _percentile(durations_ms, 0.99),
        "throughput_qps": throughput,
    }


def _percentile(samples: list[float], quantile: float) -> float:
    ordered = sorted(samples)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def _machine_metadata() -> dict[str, Any]:
    return {
        "os": platform.platform(),
        "arch": platform.machine(),
        "processor": platform.processor() or "unknown",
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _corpus_metadata(
    manifest: IndexManifest,
    chunks: list[IndexedChunk],
) -> dict[str, Any]:
    payload = [
        {
            "tenant_id": chunk.tenant_id,
            "source_id": chunk.source_id,
            "chunk_id": chunk.chunk_id,
            "content_hash": chunk.content_hash,
        }
        for chunk in sorted(
            chunks,
            key=lambda value: (value.tenant_id, value.chunk_id, value.source_id),
        )
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return {
        "index_version": manifest.index_version,
        "embedding_fingerprint": manifest.embedding_fingerprint,
        "dimensions": manifest.dimensions,
        "chunk_count": len(chunks),
        "tenant_count": len({chunk.tenant_id for chunk in chunks}),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }
