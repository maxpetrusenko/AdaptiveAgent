"""Typed contracts shared by knowledge providers and retrievers."""

from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.lineage import embedding_fingerprint


@dataclass(frozen=True)
class EmbeddingIdentity:
    provider: str
    model: str
    dimensions: int
    revision: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("embedding provider and model are required")
        if self.dimensions <= 0:
            raise ValueError("embedding dimensions must be positive")

    @property
    def fingerprint(self) -> str:
        return embedding_fingerprint(
            provider=self.provider,
            model=self.model,
            dimensions=self.dimensions,
            revision=self.revision,
        )


@dataclass(frozen=True)
class IndexManifest:
    index_version: str
    embedding_fingerprint: str
    dimensions: int

    def __post_init__(self) -> None:
        if not self.index_version.strip() or not self.embedding_fingerprint.strip():
            raise ValueError("index version and embedding fingerprint are required")
        if self.dimensions <= 0:
            raise ValueError("index dimensions must be positive")


@dataclass(frozen=True)
class IndexedChunk:
    tenant_id: str
    source_id: str
    chunk_id: str
    content_hash: str
    text: str
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class SearchRequest:
    tenant_id: str
    index_version: str
    embedding_fingerprint: str
    query_text: str
    query_embedding: tuple[float, ...]
    top_k: int = 5

    def __post_init__(self) -> None:
        if self.top_k <= 0 or self.top_k > 100:
            raise ValueError("top_k must be between 1 and 100")


@dataclass(frozen=True)
class SearchHit:
    tenant_id: str
    source_id: str
    chunk_id: str
    content_hash: str
    text: str
    fusion_score: float
    dense_score: float
    lexical_score: float
    dense_rank: int | None
    lexical_rank: int | None
    index_version: str
    embedding_fingerprint: str


@dataclass(frozen=True)
class GroundedClaim:
    text: str
    citation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("claim text is required")


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    claims: tuple[GroundedClaim, ...]


@dataclass(frozen=True)
class GroundingVerdict:
    grounded: bool
    reasons: tuple[str, ...]
    validated_citations: tuple[str, ...]


@dataclass(frozen=True)
class GoldenQuery:
    query_id: str
    tenant_id: str
    query_text: str
    relevant_chunk_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.query_id.strip() or not self.query_text.strip():
            raise ValueError("golden query id and text are required")
        if not self.relevant_chunk_ids:
            raise ValueError("golden query requires at least one relevant chunk")


@dataclass(frozen=True)
class RetrievalMetrics:
    query_count: int
    recall_at_k: float
    hit_rate: float
    mean_reciprocal_rank: float
