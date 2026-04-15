import pytest


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
