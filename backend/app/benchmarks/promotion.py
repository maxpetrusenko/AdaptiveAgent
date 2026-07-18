"""Benchmark adapter for the durable candidate-promotion authority."""

from __future__ import annotations

from sqlalchemy import select

from app.adapt.authority import promote_candidate as promote_with_authority
from app.models import PromotionRecord


async def candidate_for_run(db, adaptation_run_id: str) -> PromotionRecord:
    record = (
        await db.execute(
            select(PromotionRecord).where(
                PromotionRecord.adaptation_run_id == adaptation_run_id
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise RuntimeError(f"No candidate persisted for adaptation run {adaptation_run_id}")
    return record


async def promote_candidate(db, record: PromotionRecord) -> bool:
    """Promote through the same authority as the API, only when eligible."""
    if record.status != "ready" or record.decision_action != "promote":
        return False

    # The API authority opens an immediate SQLite transaction. End benchmark reads first.
    await db.commit()
    await promote_with_authority(db, record.id)
    await db.refresh(record)
    return record.status == "promoted"


def candidate_report(record: PromotionRecord, *, promoted: bool) -> dict[str, object]:
    return {
        "id": record.id,
        "prompt_version_id": record.candidate_prompt_id,
        "status": record.status,
        "decision": record.decision_action,
        "rationale": record.rationale,
        "parent_hash": record.parent_hash,
        "candidate_hash": record.candidate_hash,
        "dataset_hashes": record.dataset_hashes,
        "evaluated": True,
        "promoted": promoted,
    }
