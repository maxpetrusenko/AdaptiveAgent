"""Failure storage and retrieval."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalCase, EvalResult


async def get_recent_failures(
    db: AsyncSession,
    limit: int = 20,
) -> list[dict]:
    """Get recent eval failures for analysis."""
    result = await db.execute(
        select(EvalResult, EvalCase)
        .join(EvalCase, EvalResult.eval_case_id == EvalCase.id)
        .where(EvalResult.status.in_(["fail", "error"]))
        .order_by(EvalResult.id.desc())
        .limit(limit)
    )

    failures = []
    for eval_result, eval_case in result.all():
        failures.append(
            {
                "case_name": eval_case.name,
                "input": eval_case.input,
                "expected": eval_case.expected_output,
                "actual": eval_result.actual_output,
                "error": eval_result.error,
                "score": eval_result.score,
            }
        )

    return failures
