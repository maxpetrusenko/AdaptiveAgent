import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_list_runs_empty(client):
    response = await client.get("/api/evals/runs")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_cases_empty(client):
    response = await client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_case(client):
    response = await client.post(
        "/api/cases",
        json={
            "name": "Test Case",
            "input": "Hello",
            "expected_output": "Hi",
            "tags": ["test"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Case"
    assert data["input"] == "Hello"
    assert data["expected_output"] == "Hi"
    assert data["tags"] == ["test"]
    assert data["source"] == "manual"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_case_defaults(client):
    response = await client.post(
        "/api/cases",
        json={
            "name": "Minimal Case",
            "input": "test input",
            "expected_output": "test output",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tags"] == []
    assert data["source"] == "manual"


@pytest.mark.asyncio
async def test_delete_case(client):
    # Create
    res = await client.post(
        "/api/cases",
        json={
            "name": "To Delete",
            "input": "test",
            "expected_output": "test",
        },
    )
    assert res.status_code == 200
    case_id = res.json()["id"]

    # Delete
    del_res = await client.delete(f"/api/cases/{case_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Verify it's gone
    list_res = await client.get("/api/cases")
    ids = [c["id"] for c in list_res.json()]
    assert case_id not in ids


@pytest.mark.asyncio
async def test_delete_case_not_found(client):
    response = await client.delete("/api/cases/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    response = await client.get("/api/evals/runs/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_run_no_prompt(client):
    """Trigger run should fail if no active prompt version exists."""
    response = await client.post("/api/evals/run")
    assert response.status_code == 400
    assert "prompt" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trigger_run_no_cases(client):
    """Trigger run should fail if there are no eval cases."""
    # Seed a prompt version so that check passes
    from app.database import async_session
    from app.models import PromptVersion

    async with async_session() as db:
        pv = PromptVersion(
            version=1,
            content="You are a helpful assistant.",
            is_active=True,
            change_reason="test",
        )
        db.add(pv)
        await db.commit()

    response = await client.post("/api/evals/run")
    assert response.status_code == 400
    assert "cases" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_hallucination_failure_zeroes_final_score_and_persists_usage(monkeypatch):
    from app.database import async_session
    from app.eval.runner import run_eval_suite
    from app.models import EvalCase, EvalResult, PromptVersion

    async def fake_run_agent(*args, **kwargs):
        return {
            "content": "apparently correct",
            "tool_results": None,
            "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
        }

    async def fake_hallucination(*args, **kwargs):
        return {
            "has_hallucination": True,
            "confidence": 1.0,
            "details": "unsupported claim",
        }

    monkeypatch.setattr("app.eval.runner.run_agent", fake_run_agent)
    monkeypatch.setattr(
        "app.eval.runner.check_deterministic",
        lambda *args: {"pass": True, "score": 1.0, "reason": "match"},
    )
    monkeypatch.setattr("app.eval.runner.check_hallucination", fake_hallucination)

    async with async_session() as db:
        prompt = PromptVersion(version=1, content="prompt", is_active=True)
        case = EvalCase(
            name="hallucination",
            input="question",
            expected_output="apparently correct",
            tags=["protected"],
        )
        db.add_all([prompt, case])
        await db.commit()
        run = await run_eval_suite(
            db,
            case_ids=[case.id],
            consistency_repeats=0,
            prompt_version_id=prompt.id,
        )
        result = (
            await db.execute(
                select(EvalResult).where(EvalResult.eval_run_id == run.id)
            )
        ).scalar_one()

    assert result.status == "fail"
    assert result.score == 0.0
    assert result.token_count == 10


@pytest.mark.asyncio
async def test_malformed_hallucination_judge_response_fails_eval(monkeypatch):
    from app.database import async_session
    from app.eval.runner import run_eval_suite
    from app.models import EvalCase, EvalResult, PromptVersion

    class BadJudge:
        async def ainvoke(self, messages):
            return type("Response", (), {"content": "not json"})()

    async def fake_run_agent(*args, **kwargs):
        return {
            "content": "exact answer",
            "tool_results": None,
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }

    monkeypatch.setattr("app.eval.runner.run_agent", fake_run_agent)
    monkeypatch.setattr("app.eval.checks._get_judge_model", BadJudge)

    async with async_session() as db:
        prompt = PromptVersion(version=1, content="prompt", is_active=True)
        case = EvalCase(
            name="protected exact answer",
            input="question",
            expected_output="exact answer",
            tags=["protected"],
        )
        db.add_all([prompt, case])
        await db.commit()
        run = await run_eval_suite(
            db,
            case_ids=[case.id],
            consistency_repeats=0,
            prompt_version_id=prompt.id,
        )
        result = (
            await db.execute(
                select(EvalResult).where(EvalResult.eval_run_id == run.id)
            )
        ).scalar_one()

    assert result.status == "fail"
    assert result.score == 0.0
    assert "parse" in result.error.lower()


@pytest.mark.asyncio
async def test_malformed_consistency_judge_response_fails_eval(monkeypatch):
    from app.database import async_session
    from app.eval.runner import run_eval_suite
    from app.models import EvalCase, EvalResult, PromptVersion

    class BadJudge:
        async def ainvoke(self, messages):
            return type("Response", (), {"content": "not json"})()

    async def fake_run_agent(*args, **kwargs):
        return {
            "content": "4",
            "tool_results": None,
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        }

    async def grounded(*args, **kwargs):
        return {
            "has_hallucination": False,
            "confidence": 1.0,
            "details": "grounded",
        }

    monkeypatch.setattr("app.eval.runner.run_agent", fake_run_agent)
    monkeypatch.setattr("app.eval.runner.check_hallucination", grounded)
    monkeypatch.setattr("app.eval.checks._get_judge_model", BadJudge)

    async with async_session() as db:
        prompt = PromptVersion(version=1, content="prompt", is_active=True)
        case = EvalCase(
            name="reasoning consistency",
            input="2 + 2",
            expected_output="4",
            tags=["reasoning", "validation"],
        )
        db.add_all([prompt, case])
        await db.commit()
        run = await run_eval_suite(
            db,
            case_ids=[case.id],
            consistency_repeats=1,
            prompt_version_id=prompt.id,
        )
        result = (
            await db.execute(
                select(EvalResult).where(EvalResult.eval_run_id == run.id)
            )
        ).scalar_one()

    assert result.status == "fail"
    assert result.score == 0.0
    assert "inconsistent" in result.error.lower()
    assert result.token_count == 12
