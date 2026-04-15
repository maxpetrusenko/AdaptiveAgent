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
