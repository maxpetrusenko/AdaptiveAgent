"""Test case CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.eval.schemas import EvalCaseCreate, EvalCaseResponse
from app.models import EvalCase

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _case_to_response(c: EvalCase) -> EvalCaseResponse:
    return EvalCaseResponse(
        id=c.id,
        name=c.name,
        input=c.input,
        expected_output=c.expected_output,
        tags=c.tags if isinstance(c.tags, list) else [],
        source=c.source,
        created_at=c.created_at.isoformat(),
    )


@router.get("", response_model=list[EvalCaseResponse])
async def list_cases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EvalCase).order_by(EvalCase.created_at.desc()))
    cases = result.scalars().all()
    return [_case_to_response(c) for c in cases]


@router.post("", response_model=EvalCaseResponse)
async def create_case(req: EvalCaseCreate, db: AsyncSession = Depends(get_db)):
    case = EvalCase(
        name=req.name,
        input=req.input,
        expected_output=req.expected_output,
        tags=req.tags,
        source=req.source,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return _case_to_response(case)


@router.delete("/{case_id}")
async def delete_case(case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EvalCase).where(EvalCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await db.delete(case)
    await db.commit()
    return {"status": "deleted"}
