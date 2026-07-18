"""Durable, transport-independent candidate promotion authority."""

from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdaptationRun, PromotionRecord, PromptVersion


class CandidateAuthorityError(Exception):
    """Expected candidate authority failure suitable for transport translation."""

    def __init__(self, detail: str, *, status_code: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


async def promote_candidate(
    db: AsyncSession,
    candidate_id: str,
) -> PromotionRecord:
    """Atomically activate an eligible candidate against its verified parent."""
    try:
        await _begin_atomic_write(db)
        record = await _get_candidate(db, candidate_id)
        if record.status != "ready" or record.decision_action != "promote":
            raise CandidateAuthorityError("Candidate is not eligible")

        parent, candidate = await _verified_prompt_pair(db, record)
        parent_update = await db.execute(
            update(PromptVersion)
            .where(PromptVersion.id == parent.id)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        if parent_update.rowcount != 1:
            raise CandidateAuthorityError("Active parent changed")

        await db.execute(
            update(PromptVersion)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        candidate_update = await db.execute(
            update(PromptVersion)
            .where(PromptVersion.id == candidate.id)
            .where(PromptVersion.parent_id == parent.id)
            .where(PromptVersion.is_active == False)  # noqa: E712
            .values(is_active=True)
        )
        if candidate_update.rowcount != 1:
            raise CandidateAuthorityError("Candidate is not eligible")

        status_update = await db.execute(
            update(PromotionRecord)
            .where(PromotionRecord.id == record.id)
            .where(PromotionRecord.status == "ready")
            .values(status="promoted", promoted_at=datetime.now(timezone.utc))
        )
        if status_update.rowcount != 1:
            raise CandidateAuthorityError("Candidate state changed")

        await db.execute(
            update(AdaptationRun)
            .where(AdaptationRun.id == record.adaptation_run_id)
            .values(accepted=True)
        )
        await db.commit()
        return await _get_candidate(db, candidate_id)
    except CandidateAuthorityError:
        await db.rollback()
        raise


async def rollback_candidate(
    db: AsyncSession,
    candidate_id: str,
) -> PromotionRecord:
    """Atomically restore the verified parent of a promoted candidate."""
    try:
        await _begin_atomic_write(db)
        record = await _get_candidate(db, candidate_id)
        if record.status != "promoted":
            raise CandidateAuthorityError("Candidate is not promoted")

        parent, candidate = await _verified_prompt_pair(db, record)
        candidate_update = await db.execute(
            update(PromptVersion)
            .where(PromptVersion.id == candidate.id)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        if candidate_update.rowcount != 1:
            raise CandidateAuthorityError("Promoted candidate is not active")

        await db.execute(
            update(PromptVersion)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .values(is_active=False)
        )
        parent_update = await db.execute(
            update(PromptVersion)
            .where(PromptVersion.id == parent.id)
            .where(PromptVersion.is_active == False)  # noqa: E712
            .values(is_active=True)
        )
        if parent_update.rowcount != 1:
            raise CandidateAuthorityError("Parent cannot be restored")

        status_update = await db.execute(
            update(PromotionRecord)
            .where(PromotionRecord.id == record.id)
            .where(PromotionRecord.status == "promoted")
            .values(status="rolled_back", rolled_back_at=datetime.now(timezone.utc))
        )
        if status_update.rowcount != 1:
            raise CandidateAuthorityError("Candidate state changed")

        await db.execute(
            update(AdaptationRun)
            .where(AdaptationRun.id == record.adaptation_run_id)
            .values(accepted=False)
        )
        await db.commit()
        return await _get_candidate(db, candidate_id)
    except CandidateAuthorityError:
        await db.rollback()
        raise


async def _get_candidate(
    db: AsyncSession,
    candidate_id: str,
) -> PromotionRecord:
    record = (
        await db.execute(
            select(PromotionRecord).where(PromotionRecord.id == candidate_id)
        )
    ).scalar_one_or_none()
    if record is None:
        raise CandidateAuthorityError("Candidate not found", status_code=404)
    return record


async def _begin_atomic_write(db: AsyncSession) -> None:
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        await db.execute(text("BEGIN IMMEDIATE"))


async def _verified_prompt_pair(
    db: AsyncSession,
    record: PromotionRecord,
) -> tuple[PromptVersion, PromptVersion]:
    prompts = (
        await db.execute(
            select(PromptVersion).where(
                PromptVersion.id.in_(
                    [record.parent_prompt_id, record.candidate_prompt_id]
                )
            )
        )
    ).scalars().all()
    by_id = {prompt.id: prompt for prompt in prompts}
    parent = by_id.get(record.parent_prompt_id)
    candidate = by_id.get(record.candidate_prompt_id)
    if parent is None or candidate is None:
        raise CandidateAuthorityError("Candidate lineage is incomplete")
    if candidate.parent_id != parent.id:
        raise CandidateAuthorityError("Candidate parent mismatch")
    if sha256(parent.content.encode()).hexdigest() != record.parent_hash:
        raise CandidateAuthorityError("Parent hash mismatch")
    if sha256(candidate.content.encode()).hexdigest() != record.candidate_hash:
        raise CandidateAuthorityError("Candidate hash mismatch")
    return parent, candidate
