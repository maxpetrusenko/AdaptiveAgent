"""Adaptation endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapt.loop import create_adaptation_run, run_adaptation_loop
from app.database import async_session, get_db
from app.models import AdaptationRun, PromptVersion

router = APIRouter(prefix="/api/adapt", tags=["adapt"])


class AdaptRunResponse(BaseModel):
    id: str
    started_at: str
    completed_at: str | None = None
    status: str
    before_version_id: str
    after_version_id: str | None = None
    before_pass_rate: float
    after_pass_rate: float | None = None
    accepted: bool

    model_config = {"from_attributes": True}


class PromptVersionResponse(BaseModel):
    id: str
    version: int
    content: str
    parent_id: str | None = None
    created_at: str
    is_active: bool
    change_reason: str | None = None

    model_config = {"from_attributes": True}


class AdaptDetailResponse(BaseModel):
    run: AdaptRunResponse
    before_prompt: PromptVersionResponse
    after_prompt: PromptVersionResponse | None = None


def _adapt_run_to_response(r: AdaptationRun) -> AdaptRunResponse:
    return AdaptRunResponse(
        id=r.id,
        started_at=r.started_at.isoformat(),
        completed_at=r.completed_at.isoformat() if r.completed_at else None,
        status=r.status,
        before_version_id=r.before_version_id,
        after_version_id=r.after_version_id,
        before_pass_rate=r.before_pass_rate,
        after_pass_rate=r.after_pass_rate,
        accepted=r.accepted,
    )


def _prompt_version_to_response(v: PromptVersion) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=v.id,
        version=v.version,
        content=v.content,
        parent_id=v.parent_id,
        created_at=v.created_at.isoformat(),
        is_active=v.is_active,
        change_reason=v.change_reason,
    )


@router.get("/runs", response_model=list[AdaptRunResponse])
async def list_adaptation_runs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AdaptationRun).order_by(AdaptationRun.started_at.desc())
    )
    runs = result.scalars().all()
    return [_adapt_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=AdaptDetailResponse)
async def get_adaptation_detail(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AdaptationRun).where(AdaptationRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Adaptation run not found")

    # Get before prompt
    before_result = await db.execute(
        select(PromptVersion).where(PromptVersion.id == run.before_version_id)
    )
    before_prompt = before_result.scalar_one_or_none()
    if not before_prompt:
        raise HTTPException(status_code=404, detail="Before prompt not found")

    # Get after prompt
    after_prompt = None
    if run.after_version_id:
        after_result = await db.execute(
            select(PromptVersion).where(PromptVersion.id == run.after_version_id)
        )
        after_prompt = after_result.scalar_one_or_none()

    return AdaptDetailResponse(
        run=_adapt_run_to_response(run),
        before_prompt=_prompt_version_to_response(before_prompt),
        after_prompt=_prompt_version_to_response(after_prompt) if after_prompt else None,
    )


async def _run_adaptation_in_background(run_id: str):
    """Background task for adaptation loop."""
    async with async_session() as db:
        try:
            await run_adaptation_loop(db, run_id)
        except Exception:
            # Already handled in the loop, but catch any unhandled errors
            result = await db.execute(
                select(AdaptationRun).where(AdaptationRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run and run.status == "running":
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()


@router.post("/improve", response_model=AdaptRunResponse)
async def trigger_improvement(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the self-improving adaptation loop."""
    adapt_run = await create_adaptation_run(db)

    background_tasks.add_task(_run_adaptation_in_background, adapt_run.id)

    return _adapt_run_to_response(adapt_run)


@router.get("/prompts", response_model=list[PromptVersionResponse])
async def list_prompt_versions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PromptVersion).order_by(PromptVersion.version.desc())
    )
    versions = result.scalars().all()
    return [_prompt_version_to_response(v) for v in versions]
