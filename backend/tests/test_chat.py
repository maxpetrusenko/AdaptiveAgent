import pytest


@pytest.mark.asyncio
async def test_create_session(client):
    response = await client.post(
        "/api/chat/sessions",
        json={"title": "Test Session"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Session"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_sessions(client):
    # Create a session first
    await client.post("/api/chat/sessions", json={"title": "Test"})

    response = await client.get("/api/chat/sessions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_messages_empty(client):
    # Create session
    res = await client.post("/api/chat/sessions", json={"title": "Test"})
    session_id = res.json()["id"]

    response = await client.get(f"/api/chat/sessions/{session_id}/messages")
    assert response.status_code == 200
    assert response.json() == []
