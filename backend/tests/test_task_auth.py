import inspect

import pytest
from httpx import ASGITransport, AsyncClient


def task_payload():
    return {
        "goal": "Prepare a verified release",
        "constraints": ["Do not skip tests"],
        "acceptance_criteria": [
            {"id": "tests-green", "description": "All tests pass"},
            {"id": "reviewed", "description": "The change is reviewed"},
        ],
        "steps": [
            {"title": "Implement the change"},
            {"title": "Verify the release"},
        ],
        "stall_threshold": 2,
        "action_budget": 6,
    }


async def remote_client():
    from app.main import app

    transport = ASGITransport(app=app, client=("203.0.113.10", 12345))
    return AsyncClient(transport=transport, base_url="http://example.test")


def test_adapt_and_tasks_share_public_operator_auth():
    from app.api import adapt, cases, evals, operator_auth, tasks

    assert callable(operator_auth.require_operator)
    assert "_require_operator" not in inspect.getsource(adapt)
    assert "require_operator" in inspect.getsource(adapt)
    assert "require_operator" in inspect.getsource(tasks)
    assert "require_operator" in inspect.getsource(cases)
    assert "require_operator" in inspect.getsource(evals)


@pytest.mark.asyncio
@pytest.mark.parametrize("operator_token", [None, "wrong"])
async def test_remote_eval_corpus_mutations_require_configured_token(
    monkeypatch,
    operator_token,
):
    from app.config import settings

    monkeypatch.setattr(settings, "operator_api_token", "task-secret")
    headers = (
        {"X-Operator-Token": operator_token}
        if operator_token is not None
        else {}
    )
    case_payload = {
        "name": "forged protected case",
        "input": "attacker controlled input",
        "expected_output": "attacker controlled output",
        "tags": ["protected", "validation"],
        "source": "manual",
    }

    async with await remote_client() as remote:
        create_case = await remote.post(
            "/api/cases",
            json=case_payload,
            headers=headers,
        )
        delete_case = await remote.delete(
            "/api/cases/missing",
            headers=headers,
        )
        trigger_eval = await remote.post(
            "/api/evals/run",
            headers=headers,
        )

    assert [
        create_case.status_code,
        delete_case.status_code,
        trigger_eval.status_code,
    ] == [401, 401, 401]


@pytest.mark.asyncio
async def test_remote_task_mutations_are_forbidden_without_configured_token(
    monkeypatch,
):
    from app.config import settings

    monkeypatch.setattr(settings, "operator_api_token", None)
    mutation_requests = [
        ("POST", "/api/tasks", task_payload()),
        ("POST", "/api/tasks/missing/advance", {"idempotency_key": "a", "progress": True}),
        (
            "POST",
            "/api/tasks/missing/replan",
            {
                "idempotency_key": "r",
                "reason": "new evidence",
                "steps": [{"title": "retry"}],
            },
        ),
        ("POST", "/api/tasks/missing/pause", None),
        ("POST", "/api/tasks/missing/resume", None),
        ("POST", "/api/tasks/missing/cancel", None),
    ]

    async with await remote_client() as remote:
        responses = [
            await remote.request(method, path, json=payload)
            for method, path, payload in mutation_requests
        ]
        open_reads = [
            await remote.get("/api/tasks"),
            await remote.get("/api/tasks/missing"),
            await remote.get("/api/tasks/missing/effects"),
            await remote.get("/api/adapt/candidates"),
        ]

    assert {response.status_code for response in responses} == {403}
    assert "loopback" in responses[0].json()["detail"].lower()
    assert [response.status_code for response in open_reads] == [200, 404, 404, 200]


@pytest.mark.asyncio
@pytest.mark.parametrize("operator_token", [None, "wrong"])
async def test_remote_task_mutations_require_configured_token(
    monkeypatch,
    operator_token,
):
    from app.config import settings

    monkeypatch.setattr(settings, "operator_api_token", "task-secret")
    headers = (
        {"X-Operator-Token": operator_token}
        if operator_token is not None
        else {}
    )

    async with await remote_client() as remote:
        responses = [
            await remote.post("/api/tasks", json=task_payload(), headers=headers),
            await remote.post(
                "/api/tasks/missing/advance",
                json={"idempotency_key": "a", "progress": True},
                headers=headers,
            ),
            await remote.post(
                "/api/tasks/missing/replan",
                json={
                    "idempotency_key": "r",
                    "reason": "new evidence",
                    "steps": [{"title": "retry"}],
                },
                headers=headers,
            ),
            await remote.post("/api/tasks/missing/pause", headers=headers),
            await remote.post("/api/tasks/missing/resume", headers=headers),
            await remote.post("/api/tasks/missing/cancel", headers=headers),
        ]

    assert {response.status_code for response in responses} == {401}


@pytest.mark.asyncio
async def test_remote_task_mutations_succeed_with_configured_token(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "operator_api_token", "task-secret")
    headers = {"X-Operator-Token": "task-secret"}

    async with await remote_client() as remote:
        created = await remote.post("/api/tasks", json=task_payload(), headers=headers)
        task_id = created.json()["id"]
        advanced = await remote.post(
            f"/api/tasks/{task_id}/advance",
            json={"idempotency_key": "advance-auth", "progress": True},
            headers=headers,
        )
        replanned = await remote.post(
            f"/api/tasks/{task_id}/replan",
            json={
                "idempotency_key": "replan-auth",
                "reason": "verified alternative",
                "steps": [{"title": "Finish safely"}],
            },
            headers=headers,
        )
        paused = await remote.post(f"/api/tasks/{task_id}/pause", headers=headers)
        resumed = await remote.post(f"/api/tasks/{task_id}/resume", headers=headers)
        cancelled = await remote.post(f"/api/tasks/{task_id}/cancel", headers=headers)

    assert [
        created.status_code,
        advanced.status_code,
        replanned.status_code,
        paused.status_code,
        resumed.status_code,
        cancelled.status_code,
    ] == [201, 200, 200, 200, 200, 200]


@pytest.mark.asyncio
async def test_loopback_task_mutation_succeeds_without_configured_token(
    client,
    monkeypatch,
):
    from app.config import settings

    monkeypatch.setattr(settings, "operator_api_token", None)

    response = await client.post("/api/tasks", json=task_payload())

    assert response.status_code == 201
