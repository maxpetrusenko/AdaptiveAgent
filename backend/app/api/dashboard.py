"""Dashboard metrics endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AdaptationRun, EvalCase, EvalResult, EvalRun

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class MetricsResponse(BaseModel):
    pass_rate: float | None = None
    hallucination_rate: float | None = None
    avg_cost: float | None = None
    total_eval_cases: int = 0
    total_eval_runs: int = 0
    total_adaptations: int = 0
    consistency_score: float | None = None
    recent_runs: list[dict] = []


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(db: AsyncSession = Depends(get_db)):
    # Count totals
    cases_count = await db.execute(select(func.count(EvalCase.id)))
    total_cases = cases_count.scalar() or 0

    runs_count = await db.execute(select(func.count(EvalRun.id)))
    total_runs = runs_count.scalar() or 0

    adapt_count = await db.execute(select(func.count(AdaptationRun.id)))
    total_adaptations = adapt_count.scalar() or 0

    # Get latest completed eval run for pass rate
    latest_run_result = await db.execute(
        select(EvalRun)
        .where(EvalRun.status == "completed")
        .order_by(EvalRun.completed_at.desc())
        .limit(1)
    )
    latest_run = latest_run_result.scalar_one_or_none()
    pass_rate = latest_run.pass_rate if latest_run else None

    # Calculate hallucination rate from latest run
    hallucination_rate = None
    if latest_run:
        results_result = await db.execute(
            select(EvalResult).where(EvalResult.eval_run_id == latest_run.id)
        )
        results = results_result.scalars().all()
        if results:
            halluc_count = sum(
                1 for r in results
                if r.error and "hallucination" in (r.error or "").lower()
            )
            hallucination_rate = halluc_count / len(results)

    # Get recent runs for chart
    recent_result = await db.execute(
        select(EvalRun)
        .where(EvalRun.status == "completed")
        .order_by(EvalRun.started_at.desc())
        .limit(20)
    )
    recent_runs = [
        {
            "date": r.started_at.isoformat(),
            "pass_rate": r.pass_rate,
            "total": r.total,
            "passed": r.passed,
            "failed": r.failed,
        }
        for r in reversed(list(recent_result.scalars().all()))
    ]

    # Average latency as proxy for cost
    avg_cost = None
    if latest_run:
        avg_result = await db.execute(
            select(func.avg(EvalResult.latency_ms))
            .where(EvalResult.eval_run_id == latest_run.id)
        )
        avg_latency = avg_result.scalar()
        if avg_latency:
            avg_cost = round(avg_latency / 1000 * 0.003, 4)  # rough cost estimate

    return MetricsResponse(
        pass_rate=pass_rate,
        hallucination_rate=hallucination_rate,
        avg_cost=avg_cost,
        total_eval_cases=total_cases,
        total_eval_runs=total_runs,
        total_adaptations=total_adaptations,
        consistency_score=None,  # TODO: implement
        recent_runs=recent_runs,
    )
