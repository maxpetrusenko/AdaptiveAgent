import pytest


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
