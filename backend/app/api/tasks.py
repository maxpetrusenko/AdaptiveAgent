from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.operator_auth import require_operator
from app.database import get_db
from app.tasks.evidence import InvalidEvidenceError
from app.tasks.schemas import (
    AdvanceCommand,
    EffectResponse,
    ReplanCommand,
    TaskCreate,
    TaskResponse,
)
from app.tasks.store import (
    ConcurrentMutationError,
    EvidenceRequiredError,
    IdempotencyConflictError,
    InvalidTaskTransitionError,
    TaskNotFoundError,
    advance_task,
    create_task,
    get_task,
    list_effects,
    list_tasks,
    replan_task,
    transition_task,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _translate_error(error: Exception) -> HTTPException:
    if isinstance(error, TaskNotFoundError):
        return HTTPException(status_code=404, detail="Task not found")
    if isinstance(error, EvidenceRequiredError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "evidence_required",
                "missing_criteria": error.missing_criteria,
            },
        )
    if isinstance(error, InvalidEvidenceError):
        return HTTPException(status_code=422, detail=str(error))
    if isinstance(error, IdempotencyConflictError):
        return HTTPException(
            status_code=409,
            detail="Idempotency key reused with different payload",
        )
    if isinstance(error, ConcurrentMutationError):
        return HTTPException(status_code=409, detail="Concurrent task update; retry")
    if isinstance(error, InvalidTaskTransitionError):
        return HTTPException(status_code=409, detail=str(error))
    raise error


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operator)],
)
async def create_task_endpoint(
    command: TaskCreate,
    db: AsyncSession = Depends(get_db),
):
    return await create_task(db, command)


@router.get("", response_model=list[TaskResponse])
async def list_tasks_endpoint(db: AsyncSession = Depends(get_db)):
    return await list_tasks(db)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task_endpoint(task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await get_task(db, task_id)
    except Exception as error:
        raise _translate_error(error) from error


@router.post(
    "/{task_id}/advance",
    response_model=TaskResponse,
    dependencies=[Depends(require_operator)],
)
async def advance_task_endpoint(
    task_id: str,
    command: AdvanceCommand,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await advance_task(db, task_id, command)
    except Exception as error:
        raise _translate_error(error) from error


@router.post(
    "/{task_id}/replan",
    response_model=TaskResponse,
    dependencies=[Depends(require_operator)],
)
async def replan_task_endpoint(
    task_id: str,
    command: ReplanCommand,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await replan_task(db, task_id, command)
    except Exception as error:
        raise _translate_error(error) from error


async def _transition(
    task_id: str,
    transition: str,
    db: AsyncSession,
):
    try:
        return await transition_task(db, task_id, transition)
    except Exception as error:
        raise _translate_error(error) from error


@router.post(
    "/{task_id}/pause",
    response_model=TaskResponse,
    dependencies=[Depends(require_operator)],
)
async def pause_task_endpoint(task_id: str, db: AsyncSession = Depends(get_db)):
    return await _transition(task_id, "pause", db)


@router.post(
    "/{task_id}/resume",
    response_model=TaskResponse,
    dependencies=[Depends(require_operator)],
)
async def resume_task_endpoint(task_id: str, db: AsyncSession = Depends(get_db)):
    return await _transition(task_id, "resume", db)


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    dependencies=[Depends(require_operator)],
)
async def cancel_task_endpoint(task_id: str, db: AsyncSession = Depends(get_db)):
    return await _transition(task_id, "cancel", db)


@router.get("/{task_id}/effects", response_model=list[EffectResponse])
async def list_effects_endpoint(task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await list_effects(db, task_id)
    except Exception as error:
        raise _translate_error(error) from error
