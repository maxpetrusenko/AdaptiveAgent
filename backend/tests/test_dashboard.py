import pytest


@pytest.mark.asyncio
async def test_dashboard_metrics(client):
    response = await client.get("/api/dashboard/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "pass_rate" in data
    assert "total_eval_cases" in data
    assert "total_eval_runs" in data
    assert "total_adaptations" in data


@pytest.mark.asyncio
async def test_dashboard_metrics_computes_consistency_score(client):
    from app.database import async_session
    from app.models import EvalCase, EvalResult, EvalRun, PromptVersion

    async with async_session() as db:
        prompt = PromptVersion(
            version=1,
            content="Prompt",
            is_active=True,
            change_reason="seed",
        )
        db.add(prompt)
        await db.commit()
        await db.refresh(prompt)

        case = EvalCase(
            name="Reasoning",
            input="why",
            expected_output="because",
            tags=["benchmark", "reasoning", "protected"],
            source="manual",
        )
        db.add(case)
        await db.commit()
        await db.refresh(case)

        run = EvalRun(
            prompt_version_id=prompt.id,
            status="completed",
            total=2,
            passed=1,
            failed=1,
            pass_rate=0.5,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        db.add(
            EvalResult(
                eval_run_id=run.id,
                eval_case_id=case.id,
                status="pass",
                actual_output="because",
                score=1.0,
                error=None,
                latency_ms=5,
            )
        )
        db.add(
            EvalResult(
                eval_run_id=run.id,
                eval_case_id=case.id,
                status="fail",
                actual_output="maybe",
                score=0.2,
                error="Inconsistent across runs: changed answer",
                latency_ms=7,
            )
        )
        await db.commit()

    response = await client.get("/api/dashboard/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["consistency_score"] == 0.5
