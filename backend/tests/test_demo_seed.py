import importlib.util
from hashlib import sha256

import pytest
from sqlalchemy import select


def test_demo_seed_module_is_available():
    assert importlib.util.find_spec("app.demo_seed") is not None


@pytest.mark.asyncio
async def test_demo_seed_is_idempotent_and_internally_consistent():
    from app.database import async_session
    from app.demo_seed import (
        PARENT_PROMPT_ID,
        READY_PROMOTION_ID,
        READY_PROMPT_ID,
        REJECTED_PROMOTION_ID,
        REJECTED_PROMPT_ID,
        seed_configured_database,
    )
    from app.models import AdaptationRun, PromotionRecord, PromptVersion

    first = await seed_configured_database()
    second = await seed_configured_database()

    assert second == first
    assert first == {
        "active_parent_id": PARENT_PROMPT_ID,
        "ready_candidate_id": READY_PROMOTION_ID,
        "rejected_candidate_id": REJECTED_PROMOTION_ID,
        "promotion_path": f"/api/adapt/candidates/{READY_PROMOTION_ID}/promote",
        "rollback_path": f"/api/adapt/candidates/{READY_PROMOTION_ID}/rollback",
    }

    async with async_session() as db:
        prompts = (
            await db.execute(
                select(PromptVersion).where(
                    PromptVersion.id.in_(
                        [
                            PARENT_PROMPT_ID,
                            READY_PROMPT_ID,
                            REJECTED_PROMPT_ID,
                        ]
                    )
                )
            )
        ).scalars().all()
        records = (
            await db.execute(
                select(PromotionRecord).where(
                    PromotionRecord.id.in_(
                        [READY_PROMOTION_ID, REJECTED_PROMOTION_ID]
                    )
                )
            )
        ).scalars().all()
        runs = (await db.execute(select(AdaptationRun))).scalars().all()

    assert len(prompts) == 3
    assert [prompt.id for prompt in prompts if prompt.is_active] == [PARENT_PROMPT_ID]
    by_record_id = {record.id: record for record in records}
    assert set(by_record_id) == {READY_PROMOTION_ID, REJECTED_PROMOTION_ID}
    assert by_record_id[READY_PROMOTION_ID].status == "ready"
    assert by_record_id[READY_PROMOTION_ID].decision_action == "promote"
    assert by_record_id[REJECTED_PROMOTION_ID].status == "rejected"
    assert by_record_id[REJECTED_PROMOTION_ID].decision_action == "reject"
    assert len([run for run in runs if run.id.startswith("demo-run-")]) == 2

    prompts_by_id = {prompt.id: prompt for prompt in prompts}
    for record in records:
        parent = prompts_by_id[record.parent_prompt_id]
        candidate = prompts_by_id[record.candidate_prompt_id]
        assert record.parent_hash == sha256(parent.content.encode()).hexdigest()
        assert record.candidate_hash == sha256(candidate.content.encode()).hexdigest()
        assert set(record.dataset_hashes) == {"training", "validation", "protected"}
        assert set(record.raw_results) == {"training", "validation", "protected"}
        assert set(record.metrics) == {
            "validation_quality_delta",
            "lower_confidence_bound",
            "latency_ratio",
            "cost_ratio",
        }
        assert record.policy["min_validation_delta"] == 0.05
        assert record.mutations[0]["after"] == candidate.content


@pytest.mark.asyncio
async def test_demo_seed_supports_real_list_promote_and_rollback_api(client):
    from app.database import async_session
    from app.demo_seed import (
        PARENT_PROMPT_ID,
        READY_PROMOTION_ID,
        seed_configured_database,
    )
    from app.models import PromptVersion

    await seed_configured_database()

    listed = await client.get("/api/adapt/candidates")
    assert listed.status_code == 200
    by_id = {candidate["id"]: candidate for candidate in listed.json()}
    assert by_id[READY_PROMOTION_ID]["status"] == "ready"
    assert by_id[READY_PROMOTION_ID]["results"]["validation"] == {
        "baseline": 0.4,
        "candidate": 0.8,
    }

    promoted = await client.post(
        f"/api/adapt/candidates/{READY_PROMOTION_ID}/promote"
    )
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "promoted"

    rolled_back = await client.post(
        f"/api/adapt/candidates/{READY_PROMOTION_ID}/rollback"
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"

    async with async_session() as db:
        active = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
    assert active.id == PARENT_PROMPT_ID
