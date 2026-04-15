"""Eval CRUD + run endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.eval.runner import run_eval_suite
from app.models import EvalCase, EvalResult, EvalRun, PromptVersion

router = APIRouter(prefix="/api/evals", tags=["evals"])


class EvalRunResponse(BaseModel):
    id: str
    prompt_version_id: str
    started_at: str
    completed_at: str | None = None
    status: str
    pass_rate: float | None = None
    total: int
    passed: int
    failed: int

    class Config:
        from_attributes = True


class EvalResultResponse(BaseModel):
    id: str
    eval_run_id: str
    eval_case_id: str
    status: str
    actual_output: str
    score: float | None = None
    error: str | None = None
    latency_ms: int

    class Config:
        from_attributes = True


def _run_to_response(r: EvalRun) -> EvalRunResponse:
    return EvalRunResponse(
        id=r.id,
        prompt_version_id=r.prompt_version_id,
        started_at=r.started_at.isoformat(),
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        status=r.status,
        pass_rate=r.pass_rate,
        total=r.total,
        passed=r.passed,
        failed=r.failed,
    )


def _result_to_response(r: EvalResult) -> EvalResultResponse:
    return EvalResultResponse(
        id=r.id,
        eval_run_id=r.eval_run_id,
        eval_case_id=r.eval_case_id,
        status=r.status,
        actual_output=r.actual_output,
        score=r.score,
        error=r.error,
        latency_ms=r.latency_ms,
    )


@router.get("/runs", response_model=list[EvalRunResponse])
async def list_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EvalRun).order_by(EvalRun.started_at.desc()))
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return _run_to_response(run)


@router.get("/runs/{run_id}/results", response_model=list[EvalResultResponse])
async def get_run_results(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EvalResult).where(EvalResult.eval_run_id == run_id).order_by(EvalResult.id)
    )
    results = result.scalars().all()
    return [_result_to_response(r) for r in results]


async def _run_eval_in_background(run_id: str):
    """Background task to run eval suite."""
    async with async_session() as db:
        try:
            await run_eval_suite(db, eval_run_id=run_id)
        except Exception:
            # Mark run as failed
            result = await db.execute(select(EvalRun).where(EvalRun.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()


@router.post("/run", response_model=EvalRunResponse)
async def trigger_eval_run(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new eval run. Returns immediately, runs in background."""
    # Get active prompt
    result = await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
    active_prompt = result.scalar_one_or_none()
    if not active_prompt:
        raise HTTPException(status_code=400, detail="No active prompt version")

    # Count cases
    cases_result = await db.execute(select(EvalCase))
    cases = cases_result.scalars().all()
    if not cases:
        raise HTTPException(status_code=400, detail="No eval cases found")

    # Create the run record
    eval_run = EvalRun(
        prompt_version_id=active_prompt.id,
        status="running",
        total=len(cases),
    )
    db.add(eval_run)
    await db.commit()
    await db.refresh(eval_run)

    # Run in background using the already-created run ID
    background_tasks.add_task(_run_eval_in_background, eval_run.id)

    return _run_to_response(eval_run)
