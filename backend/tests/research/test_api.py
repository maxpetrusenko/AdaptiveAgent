from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.research.adapters import DeterministicResearchAdapters
from app.research.api import build_research_router
from app.research.persistence import SqliteResearchRepository


def make_app(
    database_path,
    *,
    adapters: DeterministicResearchAdapters | None = None,
    live_adapters=None,
    proof_mode: bool = False,
    guard_calls: list[str] | None = None,
) -> tuple[FastAPI, DeterministicResearchAdapters]:
    app = FastAPI()
    adapters = adapters or DeterministicResearchAdapters()

    def operator_guard() -> None:
        if guard_calls is not None:
            guard_calls.append("called")

    app.include_router(
        build_research_router(
            repository=SqliteResearchRepository(database_path),
            adapters=adapters,
            live_adapters=live_adapters,
            operator_guard=operator_guard,
            proof_mode=proof_mode,
        )
    )
    return app, adapters


async def request_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


@pytest.mark.asyncio
async def test_create_detail_and_operator_guard_are_tenant_scoped(tmp_path) -> None:
    guard_calls: list[str] = []
    app, _ = make_app(tmp_path / "research.db", guard_calls=guard_calls)

    async with await request_client(app) as client:
        first = await client.post(
            "/api/research/tenant-a/runs",
            json={"run_id": "same-run", "goal": "Tenant A goal"},
        )
        second = await client.post(
            "/api/research/tenant-b/runs",
            json={"run_id": "same-run", "goal": "Tenant B goal"},
        )
        detail_a = await client.get("/api/research/tenant-a/runs/same-run")
        detail_b = await client.get("/api/research/tenant-b/runs/same-run")

    assert first.status_code == second.status_code == 201
    assert detail_a.json()["goal"] == "Tenant A goal"
    assert detail_b.json()["goal"] == "Tenant B goal"
    assert len(guard_calls) == 4


@pytest.mark.asyncio
async def test_proof_crash_reuses_retrieval_effect_after_repository_restart(
    tmp_path,
) -> None:
    database_path = tmp_path / "research.db"
    first_app, first_adapters = make_app(database_path, proof_mode=True)

    async with await request_client(first_app) as client:
        created = await client.post(
            "/api/research/tenant-a/runs",
            json={"run_id": "run-1", "goal": "Explain the evidence"},
        )
        crashed = await client.post(
            "/api/research/tenant-a/runs/run-1/run",
            json={
                "worker_id": "worker-1",
                "inject_crash_after": "retrieve",
            },
        )

    assert created.status_code == 201
    assert crashed.status_code == 503
    assert crashed.json()["detail"]["step"] == "retrieve"
    assert first_adapters.retriever.calls == 1

    second_app, second_adapters = make_app(database_path, proof_mode=True)
    async with await request_client(second_app) as client:
        resumed = await client.post(
            "/api/research/tenant-a/runs/run-1/run",
            json={"worker_id": "worker-2"},
        )
        detail = await client.get("/api/research/tenant-a/runs/run-1")

    restarted_repository = SqliteResearchRepository(database_path).for_tenant(
        "tenant-a"
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert detail.json()["status"] == "completed"
    assert second_adapters.retriever.calls == 0
    assert restarted_repository.count_effects(step="retrieve") == 1


@pytest.mark.asyncio
async def test_crash_injection_is_forbidden_outside_proof_mode(tmp_path) -> None:
    app, adapters = make_app(tmp_path / "research.db", proof_mode=False)

    async with await request_client(app) as client:
        await client.post(
            "/api/research/tenant-a/runs",
            json={"run_id": "run-1", "goal": "Explain the evidence"},
        )
        response = await client.post(
            "/api/research/tenant-a/runs/run-1/run",
            json={
                "worker_id": "worker-1",
                "inject_crash_after": "retrieve",
            },
        )

    assert response.status_code == 403
    assert adapters.planner.calls == adapters.retriever.calls == 0


@pytest.mark.asyncio
async def test_replan_endpoint_preserves_completed_prefix(tmp_path) -> None:
    adapters = DeterministicResearchAdapters(verification_passed=False)
    app, _ = make_app(tmp_path / "research.db", adapters=adapters)

    async with await request_client(app) as client:
        await client.post(
            "/api/research/tenant-a/runs",
            json={
                "run_id": "run-1",
                "goal": "Explain the evidence",
                "action_budget": 8,
            },
        )
        blocked = await client.post(
            "/api/research/tenant-a/runs/run-1/run",
            json={"worker_id": "worker-1"},
        )
        replanned = await client.post(
            "/api/research/tenant-a/runs/run-1/replan",
            json={"worker_id": "worker-2"},
        )

    assert blocked.json()["status"] == "replan_required"
    assert replanned.status_code == 200
    assert replanned.json()["status"] == "active"
    assert replanned.json()["steps"][:3] == blocked.json()["steps"][:3]
    assert replanned.json()["steps"][3]["attempt"] == 2


@pytest.mark.asyncio
async def test_live_mode_returns_typed_503_without_live_adapters(tmp_path) -> None:
    app, _ = make_app(tmp_path / "research.db")

    async with await request_client(app) as client:
        await client.post(
            "/api/research/tenant-a/runs",
            json={
                "run_id": "run-live",
                "goal": "Explain live evidence",
                "mode": "live",
            },
        )
        unavailable = await client.post(
            "/api/research/tenant-a/runs/run-live/run",
            json={"worker_id": "worker-1"},
        )
        detail = await client.get("/api/research/tenant-a/runs/run-live")

    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "live_research_unavailable"
    assert detail.json()["cursor"] == 0


class RecordingLiveAdapters:
    def __init__(self):
        self.tenant_ids: list[str] = []
        self.services = DeterministicResearchAdapters()

    def for_tenant(self, tenant_id: str):
        self.tenant_ids.append(tenant_id)
        return self.services


@pytest.mark.asyncio
async def test_live_mode_selects_tenant_bound_live_adapters(tmp_path) -> None:
    live = RecordingLiveAdapters()
    app, deterministic = make_app(
        tmp_path / "research.db",
        live_adapters=live,
    )

    async with await request_client(app) as client:
        await client.post(
            "/api/research/tenant-a/runs",
            json={
                "run_id": "run-live",
                "goal": "Explain live evidence",
                "mode": "live",
            },
        )
        response = await client.post(
            "/api/research/tenant-a/runs/run-live/run",
            json={"worker_id": "worker-1"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert live.tenant_ids == ["tenant-a"]
    assert deterministic.retriever.calls == 0
    assert live.services.retriever.calls == 1


@pytest.mark.asyncio
async def test_resume_rejects_mode_that_differs_from_persisted_run(tmp_path) -> None:
    live = RecordingLiveAdapters()
    app, deterministic = make_app(
        tmp_path / "research.db",
        live_adapters=live,
    )

    async with await request_client(app) as client:
        created = await client.post(
            "/api/research/tenant-a/runs",
            json={
                "run_id": "run-live",
                "goal": "Explain live evidence",
                "mode": "live",
            },
        )
        mismatched = await client.post(
            "/api/research/tenant-a/runs/run-live/run",
            json={"worker_id": "worker-1", "mode": "deterministic"},
        )
        detail = await client.get("/api/research/tenant-a/runs/run-live")

    assert created.status_code == 201
    assert mismatched.status_code == 409
    assert mismatched.json()["detail"]["code"] == "research_mode_mismatch"
    assert detail.json()["execution_mode"] == "live"
    assert detail.json()["cursor"] == 0
    assert deterministic.planner.calls == 0
    assert live.tenant_ids == []
