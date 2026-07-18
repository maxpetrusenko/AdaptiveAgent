"""Reproducible CLI for the Python-versus-Rust retrieval benchmark."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from app.benchmarks.retrieval import run_retrieval_benchmark
from app.knowledge.models import IndexedChunk, IndexManifest, SearchRequest
from app.knowledge.rust import RustHybridRetriever


def build_fixture(
    *,
    chunk_count: int,
    dimensions: int,
    query_count: int,
    seed: int,
) -> tuple[IndexManifest, list[IndexedChunk], list[SearchRequest]]:
    if chunk_count <= 0 or dimensions < 2 or query_count <= 0:
        raise ValueError("chunks and queries must be positive; dimensions must be >= 2")
    fingerprint = f"benchmark-fixture-v1-{dimensions}d-seed-{seed}"
    manifest = IndexManifest("benchmark-index-v1", fingerprint, dimensions)
    chunks = [
        IndexedChunk(
            tenant_id="benchmark-tenant",
            source_id=f"source-{index:08d}",
            chunk_id=f"chunk-{index:08d}",
            content_hash=f"fixture-{seed}-{index:08d}",
            text=f"shared durable checkpoint evidence chunk-{index:08d}",
            embedding=_ranked_vector(index, chunk_count, dimensions),
        )
        for index in range(chunk_count)
    ]
    request = SearchRequest(
        tenant_id="benchmark-tenant",
        index_version=manifest.index_version,
        embedding_fingerprint=manifest.embedding_fingerprint,
        query_text="shared durable checkpoint evidence",
        query_embedding=(1.0, *([0.0] * (dimensions - 1))),
        top_k=10,
    )
    return manifest, chunks, [request for _ in range(query_count)]


def _ranked_vector(
    index: int,
    chunk_count: int,
    dimensions: int,
) -> tuple[float, ...]:
    primary = 1.0 - (0.45 * index / max(chunk_count, 1))
    secondary = (1.0 - primary * primary) ** 0.5
    return (primary, secondary, *([0.0] * (dimensions - 2)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark parity and latency for native hybrid retrieval."
    )
    parser.add_argument("--chunks", type=int, default=10_000)
    parser.add_argument("--dimensions", type=int, default=128)
    parser.add_argument("--queries", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260718)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    manifest, chunks, requests = build_fixture(
        chunk_count=args.chunks,
        dimensions=args.dimensions,
        query_count=args.queries,
        seed=args.seed,
    )
    with tempfile.TemporaryDirectory(prefix="adaptive-retrieval-bench-") as root:
        report = run_retrieval_benchmark(
            rust_retriever=RustHybridRetriever(root),
            manifest=manifest,
            chunks=chunks,
            requests=requests,
            iterations=args.iterations,
            warmups=args.warmups,
        )
    report["fixture"] = {
        "seed": args.seed,
        "query_count": args.queries,
        "query": "shared durable checkpoint evidence",
        "top_k": 10,
    }
    report["toolchain"] = {
        "rustc": _command_version(["rustc", "--version"]),
        "rayon_threads": os.environ.get("RAYON_NUM_THREADS", "automatic"),
        "native_build": "PyO3 ABI3 release wheel via uv/maturin",
    }
    report["source_state"] = {
        "head": _command_version(["git", "rev-parse", "HEAD"]),
        "dirty": bool(_command_version(["git", "status", "--porcelain"])),
    }
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded)
    else:
        print(encoded, end="")


def _command_version(command: list[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


if __name__ == "__main__":
    main()
