import pytest

from app.tasks.schemas import (
    AdvanceCommand,
    TaskCreate,
    TrustedVerificationResult,
)
from app.tasks.store import advance_verified_task, create_task


def _task_payload(*, steps: list[dict[str, str]] | None = None) -> dict:
    return {
        "goal": "Ship only with trusted proof",
        "acceptance_criteria": [
            {"id": "tests-green", "description": "All tests pass"},
        ],
        "steps": steps or [{"title": "Verify release"}],
    }


@pytest.mark.asyncio
async def test_public_advance_rejects_forged_verification_fields_and_preserves_task(client):
    created = (await client.post("/api/tasks", json=_task_payload())).json()

    response = await client.post(
        f"/api/tasks/{created['id']}/advance",
        json={
            "idempotency_key": "forged-proof",
            "progress": True,
            "evidence": [
                {
                    "criterion_id": "tests-green",
                    "summary": "Trust me",
                    "artifact_ref": "trace://forged",
                    "source": "ci",
                    "verifier": "pytest",
                    "status": "verified",
                }
            ],
        },
    )
    restored = (await client.get(f"/api/tasks/{created['id']}")).json()

    assert response.status_code == 422
    assert restored["status"] == "active"
    assert restored["actions_used"] == 0
    assert restored["acceptance_criteria"][0]["evidence"] == []


@pytest.mark.asyncio
async def test_public_artifact_and_digest_remain_unverified_and_cannot_complete(client):
    created = (
        await client.post(
            "/api/tasks",
            json=_task_payload(
                steps=[{"title": "Collect claim"}, {"title": "Complete release"}]
            ),
        )
    ).json()
    first = await client.post(
        f"/api/tasks/{created['id']}/advance",
        json={
            "idempotency_key": "public-claim",
            "progress": True,
            "evidence": [
                {
                    "criterion_id": "tests-green",
                    "summary": "Client says tests passed",
                    "artifact_ref": "trace://client",
                    "digest": "sha256:client-controlled",
                }
            ],
        },
    )
    completion = await client.post(
        f"/api/tasks/{created['id']}/advance",
        json={
            "idempotency_key": "cannot-complete",
            "progress": True,
            "evidence": [],
        },
    )
    restored = (await client.get(f"/api/tasks/{created['id']}")).json()

    evidence = first.json()["acceptance_criteria"][0]["evidence"][0]
    assert evidence["status"] == "unverified"
    assert evidence["source"] == "public_claim"
    assert evidence["verifier"] == "none"
    assert completion.status_code == 409
    assert restored["status"] == "active"


@pytest.mark.asyncio
async def test_summary_only_public_claim_cannot_complete(client):
    created = (await client.post("/api/tasks", json=_task_payload())).json()

    response = await client.post(
        f"/api/tasks/{created['id']}/advance",
        json={
            "idempotency_key": "summary-only",
            "progress": True,
            "evidence": [
                {
                    "criterion_id": "tests-green",
                    "summary": "I think tests pass",
                }
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["missing_criteria"] == ["tests-green"]


@pytest.mark.asyncio
async def test_internal_trusted_verification_can_complete():
    from app.database import async_session

    async with async_session() as db:
        task = await create_task(
            db,
            TaskCreate.model_validate(_task_payload()),
        )

        command = AdvanceCommand(
            idempotency_key="trusted-completion",
            progress=True,
            evidence=[],
        )
        result = TrustedVerificationResult(
            criterion_id="tests-green",
            summary="pytest passed",
            artifact_ref="trace://ci/run-42",
            source="ci",
            verifier="pytest",
        )
        completed = await advance_verified_task(
            db,
            task["id"],
            command,
            [result],
        )
        replayed = await advance_verified_task(db, task["id"], command, [result])

    evidence = completed["acceptance_criteria"][0]["evidence"][0]
    assert completed["status"] == "completed"
    assert replayed == completed
    assert len(completed["acceptance_criteria"][0]["evidence"]) == 1
    assert evidence["status"] == "verified"
    assert evidence["artifact_ref"] == "trace://ci/run-42"
    assert len(evidence["digest"]) == 64
