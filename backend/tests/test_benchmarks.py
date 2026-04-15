import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_benchmark_report_smoke(monkeypatch):
    from app.benchmarks.run import run_benchmark
    from app.database import async_session
    from app.models import EvalCase, EvalRun, PromptVersion

    async def fake_ensure_seed_state():
        async with async_session() as db:
            db.add(
                PromptVersion(
                    version=1,
                    content="Base prompt",
                    is_active=True,
                    change_reason="seed",
                )
            )
            db.add(
                EvalCase(
                    name="Case",
                    input="hi",
                    expected_output="hello",
                    tags=["benchmark", "protected"],
                    source="manual",
                )
            )
            await db.commit()

    async def fake_run_eval_suite(db, eval_run_id=None):
        prompt = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        run = EvalRun(
            id=eval_run_id,
            prompt_version_id=prompt.id,
            status="completed",
            total=1,
            passed=1,
            failed=0,
            pass_rate=1.0,
        )
        if not eval_run_id:
            db.add(run)
            await db.commit()
            await db.refresh(run)
        else:
            existing = (
                await db.execute(
                    __import__("sqlalchemy").select(EvalRun).where(EvalRun.id == eval_run_id)
                )
            ).scalar_one()
            existing.status = "completed"
            existing.passed = 1
            existing.failed = 0
            existing.pass_rate = 1.0
            run = existing
            await db.commit()
        return run

    async def fake_create_adaptation_run(db):
        from app.models import AdaptationRun

        run = AdaptationRun(
            status="running",
            before_version_id="before",
            before_pass_rate=1.0,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    async def fake_run_adaptation_loop(db, run_id):
        from app.models import AdaptationRun

        prompt = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        prompt.is_active = False
        db.add(
            PromptVersion(
                version=2,
                content="Improved",
                is_active=True,
                parent_id=prompt.id,
                change_reason="benchmark",
            )
        )
        run = (
            await db.execute(
                select(AdaptationRun).where(AdaptationRun.id == run_id)
            )
        ).scalar_one()
        run.accepted = True
        run.status = "completed"
        run.after_pass_rate = 1.0
        await db.commit()
        return run

    async def fake_summarize_run(db, run):
        from app.benchmarks.run import RunSummary

        return RunSummary(
            run_id=run.id,
            prompt_version_id=run.prompt_version_id,
            pass_rate=run.pass_rate or 0.0,
            passed=run.passed,
            failed=run.failed,
            hallucination_failures=0,
            protected_failures=0,
            tag_pass_rates={"benchmark": 1.0, "protected": 1.0},
        )

    monkeypatch.setattr("app.benchmarks.run.ensure_seed_state", fake_ensure_seed_state)
    monkeypatch.setattr("app.benchmarks.run.run_eval_suite", fake_run_eval_suite)
    monkeypatch.setattr(
        "app.benchmarks.run.create_adaptation_run", fake_create_adaptation_run
    )
    monkeypatch.setattr(
        "app.benchmarks.run.run_adaptation_loop", fake_run_adaptation_loop
    )
    monkeypatch.setattr("app.benchmarks.run._summarize_run", fake_summarize_run)

    report = await run_benchmark(repeats=2)

    assert report["baseline"]["mean_pass_rate"] == 1.0
    assert report["post_adaptation"]["mean_pass_rate"] == 1.0
    assert report["adaptation"]["accepted"] is True
    assert report["delta"]["active_prompt_changed"] is True
