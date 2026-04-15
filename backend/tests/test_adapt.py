import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_list_adaptation_runs_empty(client):
    response = await client.get("/api/adapt/runs")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_prompt_versions(client):
    response = await client.get("/api/adapt/prompts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_nonexistent_adaptation(client):
    response = await client.get("/api/adapt/runs/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_prompt_versions_with_data(client):
    """Seed a prompt version and verify it appears in the list."""
    from app.database import async_session
    from app.models import PromptVersion

    async with async_session() as db:
        pv = PromptVersion(
            version=1,
            content="Test prompt",
            is_active=True,
            change_reason="test seed",
        )
        db.add(pv)
        await db.commit()

    response = await client.get("/api/adapt/prompts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["version"] == 1
    assert data[0]["content"] == "Test prompt"
    assert data[0]["is_active"] is True


@pytest.mark.asyncio
async def test_adaptation_run_detail_with_data(client):
    """Create an adaptation run manually and verify the detail endpoint."""
    from app.database import async_session
    from app.models import AdaptationRun, PromptVersion

    async with async_session() as db:
        pv = PromptVersion(
            version=1,
            content="Test prompt",
            is_active=True,
            change_reason="test seed",
        )
        db.add(pv)
        await db.commit()
        await db.refresh(pv)

        run = AdaptationRun(
            status="completed",
            before_version_id=pv.id,
            before_pass_rate=0.5,
            after_pass_rate=0.7,
            accepted=True,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    response = await client.get(f"/api/adapt/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run"]["status"] == "completed"
    assert data["run"]["accepted"] is True
    assert data["before_prompt"]["content"] == "Test prompt"


@pytest.mark.asyncio
async def test_run_adaptation_loop_accepts_improved_prompt(monkeypatch):
    from app.adapt.loop import create_adaptation_run, run_adaptation_loop
    from app.database import async_session
    from app.models import EvalCase, EvalResult, EvalRun, PromptVersion

    call_count = {"value": 0}

    async def fake_run_eval_suite(
        db,
        eval_run_id=None,
        case_ids=None,
        consistency_repeats=2,
    ):
        call_count["value"] += 1
        is_before = call_count["value"] == 1
        prompt = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()

        run = EvalRun(
            id=eval_run_id,
            prompt_version_id=prompt.id,
            status="completed",
            total=2,
            passed=1 if is_before else 2,
            failed=1 if is_before else 0,
            pass_rate=0.5 if is_before else 1.0,
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
            existing.passed = run.passed
            existing.failed = run.failed
            existing.pass_rate = run.pass_rate
            run = existing

        db.add(
            EvalResult(
                eval_run_id=run.id,
                eval_case_id="protected-case",
                status="pass",
                actual_output="ok",
                score=1.0,
                error=None,
                latency_ms=1,
            )
        )
        db.add(
            EvalResult(
                eval_run_id=run.id,
                eval_case_id="normal-case",
                status="fail" if is_before else "pass",
                actual_output="ok",
                score=0.4 if is_before else 1.0,
                error="bad answer" if is_before else None,
                latency_ms=1,
            )
        )
        await db.commit()
        return run

    async def fake_generate_improved_prompt(db, current_prompt, eval_run_id):
        return current_prompt + "\nBe more accurate."

    monkeypatch.setattr("app.adapt.loop.run_eval_suite", fake_run_eval_suite)
    monkeypatch.setattr(
        "app.adapt.loop.generate_improved_prompt", fake_generate_improved_prompt
    )

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
                id="protected-case",
                name="Protected",
                input="hi",
                expected_output="hello",
                tags=["benchmark", "protected"],
                source="manual",
            )
        )
        db.add(
            EvalCase(
                id="normal-case",
                name="Normal",
                input="calc",
                expected_output="4",
                tags=["benchmark"],
                source="manual",
            )
        )
        await db.commit()

        run = await create_adaptation_run(db)
        run = await run_adaptation_loop(db, run.id)

        active_prompt = (
            await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
        ).scalar_one()

    assert run.accepted is True
    assert run.after_pass_rate == 1.0
    assert active_prompt.version == 2


@pytest.mark.asyncio
async def test_run_adaptation_loop_rejects_regression(monkeypatch):
    from app.adapt.loop import create_adaptation_run, run_adaptation_loop
    from app.database import async_session
    from app.models import EvalCase, EvalResult, EvalRun, PromptVersion

    call_count = {"value": 0}

    async def fake_run_eval_suite(
        db,
        eval_run_id=None,
        case_ids=None,
        consistency_repeats=2,
    ):
        call_count["value"] += 1
        is_before = call_count["value"] == 1
        prompt = (
            await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
        ).scalar_one()

        pass_rate = 1.0 if is_before else 0.5
        passed = 2 if is_before else 1
        failed = 0 if is_before else 1

        run = EvalRun(
            id=eval_run_id,
            prompt_version_id=prompt.id,
            status="completed",
            total=2,
            passed=passed,
            failed=failed,
            pass_rate=pass_rate,
        )
        if not eval_run_id:
            db.add(run)
            await db.commit()
            await db.refresh(run)
        else:
            existing = (
                await db.execute(select(EvalRun).where(EvalRun.id == eval_run_id))
            ).scalar_one()
            existing.status = "completed"
            existing.passed = passed
            existing.failed = failed
            existing.pass_rate = pass_rate
            run = existing

        db.add(
            EvalResult(
                eval_run_id=run.id,
                eval_case_id="protected-case",
                status="pass" if is_before else "fail",
                actual_output="ok",
                score=1.0 if is_before else 0.2,
                error=None if is_before else "regression",
                latency_ms=1,
            )
        )
        db.add(
            EvalResult(
                eval_run_id=run.id,
                eval_case_id="normal-case",
                status="pass",
                actual_output="ok",
                score=1.0,
                error=None,
                latency_ms=1,
            )
        )
        await db.commit()
        return run

    async def fake_generate_improved_prompt(db, current_prompt, eval_run_id):
        return current_prompt + "\nPotentially worse."

    monkeypatch.setattr("app.adapt.loop.run_eval_suite", fake_run_eval_suite)
    monkeypatch.setattr(
        "app.adapt.loop.generate_improved_prompt", fake_generate_improved_prompt
    )

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
                id="protected-case",
                name="Protected",
                input="hi",
                expected_output="hello",
                tags=["benchmark", "protected"],
                source="manual",
            )
        )
        db.add(
            EvalCase(
                id="normal-case",
                name="Normal",
                input="calc",
                expected_output="4",
                tags=["benchmark"],
                source="manual",
            )
        )
        await db.commit()

        run = await create_adaptation_run(db)
        run = await run_adaptation_loop(db, run.id)

        active_prompt = (
            await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
        ).scalar_one()

    assert run.accepted is False
    assert run.after_pass_rate == 0.5
    assert active_prompt.version == 1
