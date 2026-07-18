"""Deterministic Python oracle for the native hybrid retrieval contract."""

from __future__ import annotations

import math
import re
from collections import Counter

from app.knowledge.models import (
    IndexedChunk,
    IndexManifest,
    SearchHit,
    SearchRequest,
)

TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)
RRF_CONSTANT = 60


class RetrievalContractError(ValueError):
    pass


class StaleIndexError(RetrievalContractError):
    pass


class EmbeddingMismatchError(RetrievalContractError):
    pass


class DimensionMismatchError(RetrievalContractError):
    pass


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise DimensionMismatchError("embedding dimension mismatch")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


class ExactHybridRetriever:
    """In-memory exact implementation used as the native correctness oracle."""

    def __init__(self) -> None:
        self._manifest: IndexManifest | None = None
        self._chunks: tuple[IndexedChunk, ...] = ()

    def replace_index(
        self,
        manifest: IndexManifest,
        chunks: list[IndexedChunk],
    ) -> None:
        if any(len(chunk.embedding) != manifest.dimensions for chunk in chunks):
            raise DimensionMismatchError("indexed embedding dimension mismatch")
        self._manifest = manifest
        self._chunks = tuple(chunks)

    def search(self, request: SearchRequest) -> list[SearchHit]:
        manifest = self._manifest
        if manifest is None:
            raise StaleIndexError("no active index")
        if request.index_version != manifest.index_version:
            raise StaleIndexError("requested index version is not active")
        if request.embedding_fingerprint != manifest.embedding_fingerprint:
            raise EmbeddingMismatchError("embedding fingerprint mismatch")
        if len(request.query_embedding) != manifest.dimensions:
            raise DimensionMismatchError("query embedding dimension mismatch")

        chunks = [chunk for chunk in self._chunks if chunk.tenant_id == request.tenant_id]
        if not chunks:
            return []

        dense_scores = {
            chunk.chunk_id: cosine_similarity(request.query_embedding, chunk.embedding)
            for chunk in chunks
        }
        lexical_scores = self._bm25_scores(request.query_text, chunks)
        dense_ranks = self._positive_ranks(dense_scores)
        lexical_ranks = self._positive_ranks(lexical_scores)

        candidates = set(dense_ranks) | set(lexical_ranks)
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        hits: list[SearchHit] = []
        for chunk_id in candidates:
            dense_rank = dense_ranks.get(chunk_id)
            lexical_rank = lexical_ranks.get(chunk_id)
            fusion_score = sum(
                1.0 / (RRF_CONSTANT + rank)
                for rank in (dense_rank, lexical_rank)
                if rank is not None
            )
            chunk = chunk_by_id[chunk_id]
            hits.append(
                SearchHit(
                    tenant_id=chunk.tenant_id,
                    source_id=chunk.source_id,
                    chunk_id=chunk.chunk_id,
                    content_hash=chunk.content_hash,
                    text=chunk.text,
                    fusion_score=fusion_score,
                    dense_score=dense_scores[chunk_id],
                    lexical_score=lexical_scores[chunk_id],
                    dense_rank=dense_rank,
                    lexical_rank=lexical_rank,
                    index_version=manifest.index_version,
                    embedding_fingerprint=manifest.embedding_fingerprint,
                )
            )
        hits.sort(key=lambda hit: (-hit.fusion_score, hit.chunk_id))
        return hits[: request.top_k]

    @staticmethod
    def _positive_ranks(scores: dict[str, float]) -> dict[str, int]:
        ordered = sorted(
            ((chunk_id, score) for chunk_id, score in scores.items() if score > 0),
            key=lambda item: (-item[1], item[0]),
        )
        return {chunk_id: rank for rank, (chunk_id, _score) in enumerate(ordered, 1)}

    @staticmethod
    def _bm25_scores(query: str, chunks: list[IndexedChunk]) -> dict[str, float]:
        query_terms = set(_tokens(query))
        document_tokens = {chunk.chunk_id: _tokens(chunk.text) for chunk in chunks}
        if not query_terms:
            return {chunk.chunk_id: 0.0 for chunk in chunks}
        document_count = len(chunks)
        average_length = (
            sum(len(tokens) for tokens in document_tokens.values()) / document_count
        )
        document_frequency = {
            term: sum(term in tokens for tokens in document_tokens.values())
            for term in query_terms
        }
        k1 = 1.5
        b = 0.75
        scores: dict[str, float] = {}
        for chunk_id, tokens in document_tokens.items():
            counts = Counter(tokens)
            score = 0.0
            for term in query_terms:
                frequency = counts[term]
                if frequency == 0:
                    continue
                idf = math.log(
                    1 + (document_count - document_frequency[term] + 0.5)
                    / (document_frequency[term] + 0.5)
                )
                length_ratio = len(tokens) / average_length if average_length else 0.0
                score += idf * (
                    frequency * (k1 + 1)
                    / (frequency + k1 * (1 - b + b * length_ratio))
                )
            scores[chunk_id] = score
        return scores
