"""Production boundary for the optional PyO3 hybrid retrieval extension."""

from __future__ import annotations

import hashlib
import importlib
import json
import math
from pathlib import Path
from types import ModuleType
from typing import Any

from app.knowledge.models import (
    IndexedChunk,
    IndexManifest,
    SearchHit,
    SearchRequest,
)
from app.knowledge.retrieval import (
    DimensionMismatchError,
    EmbeddingMismatchError,
    StaleIndexError,
)


class RustExtensionUnavailableError(ImportError):
    """The optional native wheel is not installed in this Python environment."""


class RustRetrieverContractError(RuntimeError):
    """The native module violated or rejected the shared retrieval contract."""


class RustHybridRetriever:
    """Map shared knowledge models to the panic-safe PyO3 retrieval module."""

    def __init__(
        self,
        index_root: str | Path,
        *,
        extension: ModuleType | Any | None = None,
    ) -> None:
        self._root = Path(index_root)
        self._extension = extension or _load_extension()
        self._manifest: IndexManifest | None = None
        self._index: Any | None = None
        self._chunks_by_native_id: dict[str, IndexedChunk] = {}

    def replace_index(
        self,
        manifest: IndexManifest,
        chunks: list[IndexedChunk],
    ) -> None:
        _validate_chunks(manifest, chunks)
        corpus_hash = _corpus_hash(manifest, chunks)
        try:
            native_manifest = self._extension.IndexManifest(
                1,
                manifest.index_version,
                corpus_hash,
                "fingerprint",
                manifest.embedding_fingerprint,
                manifest.dimensions,
                "l2",
            )
            chunks_by_native_id: dict[str, IndexedChunk] = {}
            native_chunks = []
            for chunk in chunks:
                native_id = _native_chunk_id(chunk)
                if native_id in chunks_by_native_id:
                    raise RustRetrieverContractError(
                        f"duplicate tenant/chunk identity: {chunk.tenant_id}/{chunk.chunk_id}"
                    )
                chunks_by_native_id[native_id] = chunk
                native_chunks.append(
                    self._extension.ChunkRecord(
                        native_id,
                        chunk.tenant_id,
                        chunk.text,
                        chunk.source_id,
                        list(chunk.embedding),
                    )
                )
            native_index = self._extension.HybridIndex.build(
                str(self._root),
                native_manifest,
                native_chunks,
            )
        except RustRetrieverContractError:
            raise
        except Exception as error:
            raise RustRetrieverContractError(
                f"native index replacement failed: {error}"
            ) from error

        self._manifest = manifest
        self._chunks_by_native_id = chunks_by_native_id
        self._index = native_index

    def search(self, request: SearchRequest) -> list[SearchHit]:
        manifest = self._manifest
        native_index = self._index
        if manifest is None or native_index is None:
            raise StaleIndexError("no active Rust index")
        if request.index_version != manifest.index_version:
            raise StaleIndexError("requested index version is not active")
        if request.embedding_fingerprint != manifest.embedding_fingerprint:
            raise EmbeddingMismatchError("embedding fingerprint mismatch")
        if len(request.query_embedding) != manifest.dimensions:
            raise DimensionMismatchError("query embedding dimension mismatch")

        try:
            native_hits = native_index.search(
                request.query_text,
                list(request.query_embedding),
                request.tenant_id,
                request.top_k,
            )
            return [self._to_search_hit(hit, request, manifest) for hit in native_hits]
        except (StaleIndexError, EmbeddingMismatchError, DimensionMismatchError):
            raise
        except Exception as error:
            raise RustRetrieverContractError(f"native search failed: {error}") from error

    def _to_search_hit(
        self,
        native_hit: Any,
        request: SearchRequest,
        manifest: IndexManifest,
    ) -> SearchHit:
        try:
            native_id = str(native_hit.chunk_id)
            chunk = self._chunks_by_native_id[native_id]
            if chunk.tenant_id != request.tenant_id:
                raise RustRetrieverContractError(
                    "native search returned a cross-tenant result"
                )
            dense_score = native_hit.dense_score
            lexical_score = native_hit.bm25_score
            return SearchHit(
                tenant_id=chunk.tenant_id,
                source_id=chunk.source_id,
                chunk_id=chunk.chunk_id,
                content_hash=chunk.content_hash,
                text=chunk.text,
                fusion_score=float(native_hit.rrf_score),
                dense_score=float(dense_score) if dense_score is not None else 0.0,
                lexical_score=(
                    float(lexical_score) if lexical_score is not None else 0.0
                ),
                dense_rank=native_hit.dense_rank,
                lexical_rank=native_hit.bm25_rank,
                index_version=manifest.index_version,
                embedding_fingerprint=manifest.embedding_fingerprint,
            )
        except RustRetrieverContractError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise RustRetrieverContractError(
                f"invalid native search hit: {error}"
            ) from error


def _load_extension() -> ModuleType:
    try:
        return importlib.import_module("adaptive_retrieval")
    except (ImportError, OSError) as error:
        command = (
            "cd native/adaptive_retrieval && "
            "uvx --from 'maturin>=1.14,<2' maturin develop --release --locked"
        )
        raise RustExtensionUnavailableError(
            f"adaptive_retrieval is unavailable; install it with: {command}"
        ) from error


def _validate_chunks(manifest: IndexManifest, chunks: list[IndexedChunk]) -> None:
    for chunk in chunks:
        if len(chunk.embedding) != manifest.dimensions:
            raise DimensionMismatchError("indexed embedding dimension mismatch")
        if not all(math.isfinite(value) for value in chunk.embedding):
            raise DimensionMismatchError("indexed embeddings must be finite")


def _native_chunk_id(chunk: IndexedChunk) -> str:
    return f"{len(chunk.tenant_id)}:{chunk.tenant_id}{chunk.chunk_id}"


def _corpus_hash(manifest: IndexManifest, chunks: list[IndexedChunk]) -> str:
    payload = {
        "index_version": manifest.index_version,
        "embedding_fingerprint": manifest.embedding_fingerprint,
        "dimensions": manifest.dimensions,
        "chunks": [
            {
                "tenant_id": chunk.tenant_id,
                "source_id": chunk.source_id,
                "chunk_id": chunk.chunk_id,
                "content_hash": chunk.content_hash,
                "text": chunk.text,
                "embedding": chunk.embedding,
            }
            for chunk in sorted(
                chunks,
                key=lambda value: (
                    value.tenant_id,
                    value.chunk_id,
                    value.source_id,
                ),
            )
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
