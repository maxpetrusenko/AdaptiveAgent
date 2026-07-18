import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.tasks.schemas import AdvanceCommand, TaskCreate
from app.tasks.store import (
    advance_task,
)
from app.tasks.store import (
    create_task as create_stored_task,
)
from app.tasks.store import (
    get_task as get_stored_task,
)
from app.tasks.store import (
    list_effects as list_stored_effects,
)


def task_payload(**overrides):
    payload = {
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
    payload.update(overrides)
    return payload


async def create_task(client, **overrides):
    response = await client.post("/api/tasks", json=task_payload(**overrides))
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_list_and_get_task(client):
    created = await create_task(client)

    listed = await client.get("/api/tasks")
    detail = await client.get(f"/api/tasks/{created['id']}")

    assert listed.status_code == 200
    assert [task["id"] for task in listed.json()] == [created["id"]]
    assert detail.status_code == 200
    assert detail.json()["goal"] == "Prepare a verified release"
    assert detail.json()["status"] == "active"
    assert detail.json()["plan_version"] == 1
    assert [step["status"] for step in detail.json()["steps"]] == [
        "active",
        "pending",
    ]


@pytest.mark.asyncio
async def test_advance_records_evidence_and_moves_to_next_step(client):
    task = await create_task(client)

    response = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={
            "idempotency_key": "advance-1",
            "progress": True,
            "evidence": [
                {
                    "criterion_id": "tests-green",
                    "summary": "pytest passed",
                    "artifact_ref": "trace://pytest-1",
                }
            ],
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["current_step_index"] == 1
    assert updated["steps"][0]["status"] == "completed"
    assert updated["steps"][1]["status"] == "active"
    assert updated["acceptance_criteria"][0]["evidence"][0]["summary"] == "pytest passed"
    assert updated["actions_used"] == 1
    assert updated["checkpoint"] == {
        "sequence": 2,
        "operation": "advance",
        "idempotency_key": "advance-1",
        "updated_at": updated["updated_at"],
    }


@pytest.mark.asyncio
async def test_advance_is_idempotent_and_journals_one_effect(client):
    task = await create_task(client)
    command = {
        "idempotency_key": "same-effect",
        "progress": True,
        "evidence": [
            {
                "criterion_id": "tests-green",
                "summary": "pytest passed",
                "artifact_ref": "trace://pytest-1",
            }
        ],
    }

    first = await client.post(f"/api/tasks/{task['id']}/advance", json=command)
    second = await client.post(f"/api/tasks/{task['id']}/advance", json=command)
    journal = await client.get(f"/api/tasks/{task['id']}/effects")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["actions_used"] == 1
    assert len(second.json()["acceptance_criteria"][0]["evidence"]) == 1
    assert journal.status_code == 200
    assert [entry["idempotency_key"] for entry in journal.json()] == ["same-effect"]


@pytest.mark.asyncio
async def test_no_progress_at_stall_threshold_replans_once(client):
    task = await create_task(client, stall_threshold=2)

    first = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "stall-1", "progress": False, "evidence": []},
    )
    second = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "stall-2", "progress": False, "evidence": []},
    )

    assert first.json()["stall_count"] == 1
    assert first.json()["plan_version"] == 1
    assert second.json()["stall_count"] == 0
    assert second.json()["plan_version"] == 1
    assert second.json()["status"] == "replan_required"
    assert second.json()["replan_reason"] == "stall_threshold_reached"
    blocked = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "stall-3", "progress": False, "evidence": []},
    )
    assert blocked.status_code == 409
    assert (await client.get(f"/api/tasks/{task['id']}")).json()["plan_version"] == 1
    replanned = await client.post(
        f"/api/tasks/{task['id']}/replan",
        json={
            "idempotency_key": "stall-replan",
            "reason": "Use the fallback verification path",
            "steps": [{"title": "Run fallback verification"}],
        },
    )
    assert replanned.status_code == 200
    assert replanned.json()["status"] == "active"
    assert replanned.json()["plan_version"] == 2


@pytest.mark.asyncio
async def test_explicit_replan_preserves_completed_steps_and_replaces_pending_suffix(client):
    task = await create_task(client)
    await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "step-1", "progress": True, "evidence": []},
    )

    response = await client.post(
        f"/api/tasks/{task['id']}/replan",
        json={
            "idempotency_key": "replan-1",
            "reason": "Verification environment changed",
            "steps": [
                {"title": "Repair the environment"},
                {"title": "Verify the release again"},
            ],
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["plan_version"] == 2
    assert [step["title"] for step in updated["steps"]] == [
        "Implement the change",
        "Repair the environment",
        "Verify the release again",
    ]
    assert [step["status"] for step in updated["steps"]] == [
        "completed",
        "active",
        "pending",
    ]
    assert updated["replan_reason"] == "Verification environment changed"
    assert updated["checkpoint"]["operation"] == "replan"
    assert updated["checkpoint"]["idempotency_key"] == "replan-1"


@pytest.mark.asyncio
async def test_action_budget_exhaustion_escalates_instead_of_looping(client):
    task = await create_task(client, action_budget=1)

    response = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "budget-1", "progress": True, "evidence": []},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "escalated"
    assert response.json()["escalation_reason"] == "action_budget_exhausted"
    blocked = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "budget-2", "progress": True, "evidence": []},
    )
    assert blocked.status_code == 409


@pytest.mark.asyncio
async def test_replan_consumes_action_budget_and_can_escalate(client):
    task = await create_task(client, action_budget=1)

    response = await client.post(
        f"/api/tasks/{task['id']}/replan",
        json={
            "idempotency_key": "budgeted-replan",
            "reason": "The original plan is blocked",
            "steps": [{"title": "Use a safer plan"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["plan_version"] == 2
    assert response.json()["actions_used"] == 1
    assert response.json()["status"] == "escalated"
    assert response.json()["escalation_reason"] == "action_budget_exhausted"


@pytest.mark.asyncio
async def test_idempotency_key_reuse_with_different_payload_conflicts(client):
    task = await create_task(client)
    first = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "stable-key", "progress": False, "evidence": []},
    )
    mismatch = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "stable-key", "progress": True, "evidence": []},
    )

    assert first.status_code == 200
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"] == "Idempotency key reused with different payload"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"goal": "   "},
        {
            "acceptance_criteria": [
                {"id": "duplicate", "description": "First"},
                {"id": "duplicate", "description": "Second"},
            ]
        },
        {
            "acceptance_criteria": [
                {"id": "   ", "description": "No identifier"},
            ]
        },
        {
            "acceptance_criteria": [
                {"id": "criterion", "description": "   "},
            ]
        },
        {"steps": [{"title": "   "}]},
    ],
)
async def test_task_creation_rejects_ambiguous_or_blank_ledger_text(client, overrides):
    response = await client.post("/api/tasks", json=task_payload(**overrides))

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pause_resume_and_cancel_enforce_task_lifecycle(client):
    task = await create_task(client)

    paused = await client.post(f"/api/tasks/{task['id']}/pause")
    blocked = await client.post(
        f"/api/tasks/{task['id']}/advance",
        json={"idempotency_key": "paused", "progress": True, "evidence": []},
    )
    resumed = await client.post(f"/api/tasks/{task['id']}/resume")
    cancelled = await client.post(f"/api/tasks/{task['id']}/cancel")
    cannot_resume = await client.post(f"/api/tasks/{task['id']}/resume")

    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["checkpoint"]["operation"] == "pause"
    assert blocked.status_code == 409
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert resumed.json()["checkpoint"]["sequence"] == 3
    assert resumed.json()["checkpoint"]["operation"] == "resume"
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["checkpoint"]["sequence"] == 4
    assert cancelled.json()["checkpoint"]["operation"] == "cancel"
    assert cannot_resume.status_code == 409


@pytest.mark.asyncio
async def test_task_commands_return_not_found_for_unknown_task(client):
    response = await client.post("/api/tasks/missing/pause")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def stored_task_command() -> TaskCreate:
    return TaskCreate.model_validate(
        {
            "goal": "Survive a worker restart",
            "acceptance_criteria": [
                {"id": "verified", "description": "The result is verified"}
            ],
            "steps": [
                {"title": "Perform the effect"},
                {"title": "Complete the task"},
                {"title": "Archive the result"},
            ],
            "stall_threshold": 2,
            "action_budget": 10,
        }
    )


def file_session_factory(database_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


@pytest.mark.asyncio
async def test_task_survives_restart_and_replayed_effect_is_skipped(tmp_path):
    database_path = tmp_path / "restart.db"
    first_engine, first_factory = file_session_factory(database_path)
    async with first_factory() as db:
        task = await create_stored_task(db, stored_task_command())
        first_result = await advance_task(
            db,
            task["id"],
            AdvanceCommand(
                idempotency_key="durable-effect",
                progress=True,
                evidence=[
                    {
                        "criterion_id": "verified",
                        "summary": "effect verified",
                        "artifact_ref": "trace://durable-effect",
                    }
                ],
            ),
        )
    await first_engine.dispose()

    restarted_engine, restarted_factory = file_session_factory(database_path)
    async with restarted_factory() as db:
        restored = await get_stored_task(db, task["id"])
        replayed = await advance_task(
            db,
            task["id"],
            AdvanceCommand(
                idempotency_key="durable-effect",
                progress=True,
                evidence=[
                    {
                        "criterion_id": "verified",
                        "summary": "effect verified",
                        "artifact_ref": "trace://durable-effect",
                    }
                ],
            ),
        )
        effects = await list_stored_effects(db, task["id"])
    await restarted_engine.dispose()

    assert restored["steps"][0]["status"] == "completed"
    assert restored["current_step_index"] == 1
    assert restored["acceptance_criteria"][0]["evidence"][0]["artifact_ref"] == (
        "trace://durable-effect"
    )
    assert replayed == first_result
    assert replayed["current_step_index"] == 1
    assert replayed["actions_used"] == 1
    assert replayed["checkpoint"]["sequence"] == 2
    assert len(effects) == 1


async def force_same_revision_reads(monkeypatch, task_id: str):
    import app.tasks.store as store

    original_fetch = store._fetch_task
    reads = 0
    both_read = asyncio.Event()

    async def synchronized_fetch(db, fetched_task_id):
        nonlocal reads
        task = await original_fetch(db, fetched_task_id)
        if fetched_task_id == task_id and reads < 2:
            reads += 1
            if reads == 2:
                both_read.set()
            await asyncio.wait_for(both_read.wait(), timeout=2)
        return task

    monkeypatch.setattr(store, "_fetch_task", synchronized_fetch)


@pytest.mark.asyncio
async def test_parallel_same_idempotency_key_records_one_effect(
    tmp_path,
    monkeypatch,
):
    engine, factory = file_session_factory(tmp_path / "same-key.db")
    async with factory() as db:
        task = await create_stored_task(db, stored_task_command())
    await force_same_revision_reads(monkeypatch, task["id"])
    command = AdvanceCommand(
        idempotency_key="one-effect",
        progress=True,
        evidence=[],
    )

    async def run_advance():
        async with factory() as db:
            return await advance_task(db, task["id"], command)

    first, second = await asyncio.gather(run_advance(), run_advance())
    async with factory() as db:
        restored = await get_stored_task(db, task["id"])
        effects = await list_stored_effects(db, task["id"])
    await engine.dispose()

    assert first == second
    assert restored["current_step_index"] == 1
    assert restored["actions_used"] == 1
    assert len(effects) == 1


@pytest.mark.asyncio
async def test_parallel_different_advances_preserve_both_updates(
    tmp_path,
    monkeypatch,
):
    engine, factory = file_session_factory(tmp_path / "different-keys.db")
    async with factory() as db:
        task = await create_stored_task(db, stored_task_command())
    await force_same_revision_reads(monkeypatch, task["id"])

    async def run_advance(idempotency_key):
        async with factory() as db:
            return await advance_task(
                db,
                task["id"],
                AdvanceCommand(
                    idempotency_key=idempotency_key,
                    progress=True,
                    evidence=[],
                ),
            )

    await asyncio.gather(run_advance("effect-a"), run_advance("effect-b"))
    async with factory() as db:
        restored = await get_stored_task(db, task["id"])
        effects = await list_stored_effects(db, task["id"])
    await engine.dispose()

    assert [step["status"] for step in restored["steps"]] == [
        "completed",
        "completed",
        "active",
    ]
    assert restored["current_step_index"] == 2
    assert restored["actions_used"] == 2
    assert restored["checkpoint"]["sequence"] == 3
    assert {effect["idempotency_key"] for effect in effects} == {
        "effect-a",
        "effect-b",
    }
