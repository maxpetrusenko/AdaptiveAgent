"""Golden-suite retrieval metrics with exact, inspectable definitions."""

from __future__ import annotations

from app.knowledge.models import GoldenQuery, RetrievalMetrics
from app.knowledge.service import KnowledgeRetrievalService, NoEvidenceError


async def evaluate_golden_retrieval(
    service: KnowledgeRetrievalService,
    queries: list[GoldenQuery],
    *,
    top_k: int,
) -> RetrievalMetrics:
    if not queries:
        raise ValueError("golden retrieval suite must not be empty")

    recalls: list[float] = []
    hits: list[float] = []
    reciprocal_ranks: list[float] = []
    for query in queries:
        try:
            results = await service.search(
                tenant_id=query.tenant_id,
                query_text=query.query_text,
                top_k=top_k,
            )
        except NoEvidenceError:
            results = []
        returned_ids = [result.chunk_id for result in results]
        relevant = set(query.relevant_chunk_ids)
        matched = relevant.intersection(returned_ids)
        recalls.append(len(matched) / len(relevant))
        hits.append(1.0 if matched else 0.0)
        first_relevant_rank = next(
            (
                rank
                for rank, chunk_id in enumerate(returned_ids, 1)
                if chunk_id in relevant
            ),
            None,
        )
        reciprocal_ranks.append(
            1.0 / first_relevant_rank if first_relevant_rank is not None else 0.0
        )

    count = len(queries)
    return RetrievalMetrics(
        query_count=count,
        recall_at_k=sum(recalls) / count,
        hit_rate=sum(hits) / count,
        mean_reciprocal_rank=sum(reciprocal_ranks) / count,
    )
