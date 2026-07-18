import pytest


@pytest.mark.asyncio
async def test_loopback_frontend_origin_is_allowed(client):
    response = await client.get(
        "/health",
        headers={"Origin": "http://127.0.0.1:3737"},
    )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "http://127.0.0.1:3737"
    )
