import inspect

import pytest
from sqlalchemy import select


def test_promotion_record_model_is_available():
    from app import models

    assert hasattr(models, "PromotionRecord")


def test_benchmark_uses_public_adaptation_authority():
    from app.adapt import authority
    from app.benchmarks import promotion

    assert callable(authority.promote_candidate)
    assert callable(authority.rollback_candidate)
    assert "app.api.adapt" not in inspect.getsource(promotion)


@pytest.mark.asyncio
async def test_default_seed_suite_has_nonempty_governed_splits():
    from app.database import async_session
    from app.models import EvalCase
    from app.seed import seed_eval_cases

    async with async_session() as db:
        await seed_eval_cases(db)
        cases = (await db.execute(select(EvalCase))).scalars().all()

    split_counts = {"training": 0, "validation": 0, "protected": 0}
    for case in cases:
        assigned = set(case.tags) & set(split_counts)
        assert len(assigned) == 1
        split_counts[assigned.pop()] += 1

    assert split_counts["training"] >= 1
    assert split_counts["validation"] >= 2
    assert split_counts["protected"] >= 1


@pytest.mark.asyncio
async def test_adaptation_selects_latest_parent_from_legacy_multiple_active_rows():
    from app.adapt.loop import create_adaptation_run
    from app.database import async_session
    from app.models import PromptVersion

    async with async_session() as db:
        db.add_all(
            [
                PromptVersion(version=1, content="old", is_active=True),
                PromptVersion(version=2, content="latest", is_active=True),
            ]
        )
        await db.commit()

        run = await create_adaptation_run(db)

    assert run.before_version_id == await _prompt_id_for_version(2)


async def _prompt_id_for_version(version: int) -> str:
    from app.database import async_session
    from app.models import PromptVersion

    async with async_session() as db:
        return (
            await db.execute(
                select(PromptVersion.id).where(PromptVersion.version == version)
            )
        ).scalar_one()
