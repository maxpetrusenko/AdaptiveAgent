"""Integration tests for persisted, operator-authorized promotion."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def _seed_split_suite():
    from app.database import async_session
    from app.models import EvalCase, PromptVersion

    async with async_session() as db:
        parent = PromptVersion(
            version=1,
            content="parent prompt",
            is_active=True,
            change_reason="seed",
        )
        db.add(parent)
        cases = [
            EvalCase(
                id="train-1",
                name="Training one",
                input="training secret one",
                expected_output="train expected one",
                tags=["training"],
            ),
            EvalCase(
                id="train-2",
                name="Training two",
                input="training secret two",
                expected_output="train expected two",
                tags=["training"],
            ),
            EvalCase(
                id="validation-1",
                name="Validation one",
                input="sealed validation one",
                expected_output="validation expected one",
                tags=["validation"],
            ),
            EvalCase(
                id="validation-2",
                name="Validation two",
                input="sealed validation two",
                expected_output="validation expected two",
                tags=["validation"],
            ),
            EvalCase(
                id="protected-1",
                name="Protected one",
                input="protected safety secret",
                expected_output="protected expected",
                tags=["protected"],
            ),
        ]
        db.add_all(cases)
        await db.commit()
        await db.refresh(parent)
        return parent.id


def _install_model_free_loop(
    monkeypatch,
    *,
    protected_regression: bool = False,
    protected_status_regression: bool = False,
    candidate_token_ratio: float = 1.0,
):
    from app.models import EvalCase, EvalResult, EvalRun, PromptVersion

    observed = {
        "proposal_case_ids": [],
        "proposal_inputs": [],
        "eval_prompt_pairs": [],
        "candidate_number": 0,
    }

    async def fake_run_eval_suite(
        db,
        eval_run_id=None,
        case_ids=None,
        consistency_repeats=2,
        prompt_version_id=None,
    ):
        assert eval_run_id is None
        assert prompt_version_id is not None
        cases = (
            await db.execute(
                select(EvalCase)
                .where(EvalCase.id.in_(case_ids))
                .order_by(EvalCase.id)
            )
        ).scalars().all()
        prompt = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.id == prompt_version_id)
            )
        ).scalar_one()
        active = (
            await db.execute(
                select(PromptVersion)
                .where(PromptVersion.is_active == True)  # noqa: E712
                .order_by(PromptVersion.version.desc())
                .limit(1)
            )
        ).scalar_one()
        observed["eval_prompt_pairs"].append((prompt.id, active.id))

        is_candidate = prompt.parent_id is not None
        run = EvalRun(
            prompt_version_id=prompt.id,
            status="completed",
            total=len(cases),
        )
        db.add(run)
        await db.flush()

        passed = 0
        for case in cases:
            tags = case.tags if isinstance(case.tags, list) else []
            baseline_score = 1.0 if "protected" in tags else 0.5
            candidate_score = 0.8
            if "protected" in tags:
                candidate_score = 0.0 if protected_regression else 1.0
            score = candidate_score if is_candidate else baseline_score
            status = "pass" if score >= 0.5 else "fail"
            if is_candidate and "protected" in tags and protected_status_regression:
                status = "fail"
            token_count = int(100 * candidate_token_ratio) if is_candidate else 100
            passed += status == "pass"
            db.add(
                EvalResult(
                    eval_run_id=run.id,
                    eval_case_id=case.id,
                    status=status,
                    actual_output=f"{prompt.id}:{case.id}",
                    score=score,
                    latency_ms=10,
                    token_count=token_count,
                )
            )
        run.passed = passed
        run.failed = len(cases) - passed
        run.pass_rate = passed / len(cases)
        await db.commit()
        await db.refresh(run)
        return run

    async def fake_generate_improved_prompt(db, current_prompt, eval_run_id):
        rows = (
            await db.execute(
                select(EvalCase)
                .join(EvalResult, EvalResult.eval_case_id == EvalCase.id)
                .where(EvalResult.eval_run_id == eval_run_id)
                .order_by(EvalCase.id)
            )
        ).scalars().all()
        observed["proposal_case_ids"] = [case.id for case in rows]
        observed["proposal_inputs"] = [case.input for case in rows]
        observed["candidate_number"] += 1
        return f"{current_prompt}\nimproved {observed['candidate_number']}"

    monkeypatch.setattr("app.adapt.loop.run_eval_suite", fake_run_eval_suite)
    monkeypatch.setattr(
        "app.adapt.loop.generate_improved_prompt",
        fake_generate_improved_prompt,
    )
    return observed


async def _run_candidate(
    monkeypatch,
    *,
    protected_regression: bool = False,
    protected_status_regression: bool = False,
    candidate_token_ratio: float = 1.0,
):
    from app.adapt.loop import create_adaptation_run, run_adaptation_loop
    from app.database import async_session

    observed = _install_model_free_loop(
        monkeypatch,
        protected_regression=protected_regression,
        protected_status_regression=protected_status_regression,
        candidate_token_ratio=candidate_token_ratio,
    )
    async with async_session() as db:
        run = await create_adaptation_run(db)
        await run_adaptation_loop(db, run.id, consistency_repeats=0)
    return observed


@pytest.mark.asyncio
async def test_adaptation_persists_ready_candidate_without_preactivation(monkeypatch):
    from app.database import async_session
    from app.models import AdaptationRun, PromotionRecord, PromptVersion

    parent_id = await _seed_split_suite()
    observed = await _run_candidate(monkeypatch)

    async with async_session() as restarted_db:
        record = (await restarted_db.execute(select(PromotionRecord))).scalar_one()
        parent = (
            await restarted_db.execute(
                select(PromptVersion).where(PromptVersion.id == parent_id)
            )
        ).scalar_one()
        candidate = (
            await restarted_db.execute(
                select(PromptVersion).where(
                    PromptVersion.id == record.candidate_prompt_id
                )
            )
        ).scalar_one()
        adapt_run = (
            await restarted_db.execute(select(AdaptationRun))
        ).scalar_one()

    assert observed["proposal_case_ids"] == ["train-1", "train-2"]
    assert observed["proposal_inputs"] == [
        "training secret one",
        "training secret two",
    ]
    assert all(active_id == parent_id for _, active_id in observed["eval_prompt_pairs"])
    assert record.status == "ready"
    assert record.decision_action == "promote"
    assert record.parent_prompt_id == parent.id
    assert record.parent_hash
    assert record.candidate_hash
    assert set(record.dataset_hashes) == {"training", "validation", "protected"}
    assert set(record.raw_results) == {"training", "validation", "protected"}
    assert record.metrics["lower_confidence_bound"] >= 0.05
    assert record.policy["min_validation_delta"] == 0.05
    assert parent.is_active is True
    assert candidate.is_active is False
    assert adapt_run.accepted is False


@pytest.mark.asyncio
async def test_protected_regression_persists_rejected_inactive_candidate(monkeypatch):
    from app.database import async_session
    from app.models import PromotionRecord, PromptVersion

    parent_id = await _seed_split_suite()
    await _run_candidate(monkeypatch, protected_regression=True)

    async with async_session() as db:
        record = (await db.execute(select(PromotionRecord))).scalar_one()
        prompts = (await db.execute(select(PromptVersion))).scalars().all()

    assert record.status == "rejected"
    assert record.decision_action == "reject"
    assert "protected" in record.rationale.lower()
    assert [prompt.id for prompt in prompts if prompt.is_active] == [parent_id]


@pytest.mark.asyncio
async def test_protected_status_regression_rejects_validation_gain(monkeypatch):
    from app.database import async_session
    from app.models import PromotionRecord

    await _seed_split_suite()
    await _run_candidate(monkeypatch, protected_status_regression=True)

    async with async_session() as db:
        record = (await db.execute(select(PromotionRecord))).scalar_one()

    assert record.status == "rejected"
    assert "protected" in record.rationale.lower()
    assert "status" in record.rationale.lower()
    assert record.raw_results["protected"]["baseline_statuses"] == ["pass"]
    assert record.raw_results["protected"]["candidate_statuses"] == ["fail"]


@pytest.mark.asyncio
async def test_twenty_six_percent_token_increase_rejects_candidate(monkeypatch):
    from app.database import async_session
    from app.models import PromotionRecord

    await _seed_split_suite()
    await _run_candidate(monkeypatch, candidate_token_ratio=1.26)

    async with async_session() as db:
        record = (await db.execute(select(PromotionRecord))).scalar_one()

    assert record.status == "rejected"
    assert "cost" in record.rationale.lower()
    assert record.metrics["cost_ratio"] == pytest.approx(1.26)
    assert record.raw_results["validation"]["baseline_token_count"] == [100, 100]
    assert record.raw_results["validation"]["candidate_token_count"] == [126, 126]


@pytest.mark.asyncio
async def test_adaptation_requires_nonempty_sealed_splits(monkeypatch):
    from app.adapt.loop import create_adaptation_run, run_adaptation_loop
    from app.database import async_session
    from app.models import EvalCase

    await _seed_split_suite()
    _install_model_free_loop(monkeypatch)
    async with async_session() as db:
        validation_cases = (
            await db.execute(
                select(EvalCase).where(EvalCase.tags.contains("validation"))
            )
        ).scalars().all()
        for case in validation_cases:
            await db.delete(case)
        await db.commit()
        run = await create_adaptation_run(db)
        with pytest.raises(ValueError, match="validation"):
            await run_adaptation_loop(db, run.id, consistency_repeats=0)


@pytest.mark.asyncio
async def test_candidate_api_promotes_then_rolls_back_across_sessions(
    client,
    monkeypatch,
):
    from app.database import async_session
    from app.models import PromotionRecord, PromptVersion

    parent_id = await _seed_split_suite()
    await _run_candidate(monkeypatch)
    async with async_session() as first_session:
        record_id = (
            await first_session.execute(select(PromotionRecord.id))
        ).scalar_one()

    listed = await client.get("/api/adapt/candidates")
    assert listed.status_code == 200
    candidate = listed.json()[0]
    assert set(candidate) == {
        "id",
        "title",
        "status",
        "parent_hash",
        "candidate_hash",
        "rationale",
        "decision",
        "results",
        "lower_confidence_bound",
        "latency_ratio",
        "cost_ratio",
        "mutations",
    }
    assert candidate["status"] == "ready"

    promoted = await client.post(f"/api/adapt/candidates/{record_id}/promote")
    assert promoted.status_code == 200
    assert promoted.json()["status"] == "promoted"

    async with async_session() as restarted_session:
        active_after_promote = (
            await restarted_session.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        assert active_after_promote.id != parent_id

    rolled_back = await client.post(f"/api/adapt/candidates/{record_id}/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"

    async with async_session() as final_session:
        active_after_rollback = (
            await final_session.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        assert active_after_rollback.id == parent_id


@pytest.mark.asyncio
async def test_improve_api_creates_candidate_without_activation(client, monkeypatch):
    from app.database import async_session
    from app.models import PromptVersion

    parent_id = await _seed_split_suite()
    _install_model_free_loop(monkeypatch)

    response = await client.post("/api/adapt/improve")

    assert response.status_code == 200
    candidates = await client.get("/api/adapt/candidates")
    assert candidates.status_code == 200
    assert candidates.json()[0]["status"] == "ready"
    async with async_session() as restarted_db:
        active = (
            await restarted_db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
    assert active.id == parent_id


@pytest.mark.asyncio
async def test_mutations_require_configured_operator_token(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "operator_api_token", "secret-operator-token")

    missing = await client.post("/api/adapt/candidates/missing/promote")
    wrong = await client.post(
        "/api/adapt/candidates/missing/promote",
        headers={"X-Operator-Token": "wrong"},
    )
    authorized = await client.post(
        "/api/adapt/candidates/missing/promote",
        headers={"X-Operator-Token": "secret-operator-token"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert authorized.status_code == 404


@pytest.mark.asyncio
async def test_mutations_without_token_are_loopback_only(monkeypatch):
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "operator_api_token", None)
    transport = ASGITransport(app=app, client=("203.0.113.10", 12345))
    async with AsyncClient(transport=transport, base_url="http://example.test") as remote:
        mutation = await remote.post("/api/adapt/improve")
        read_only = await remote.get("/api/adapt/candidates")

    assert mutation.status_code == 403
    assert "loopback" in mutation.json()["detail"].lower()
    assert read_only.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_candidate_promotions_have_one_winner(client, monkeypatch):
    from app.database import async_session
    from app.models import PromotionRecord, PromptVersion

    parent_id = await _seed_split_suite()
    await _run_candidate(monkeypatch)
    await _run_candidate(monkeypatch)
    async with async_session() as db:
        record_ids = (
            await db.execute(
                select(PromotionRecord.id).order_by(PromotionRecord.created_at)
            )
        ).scalars().all()

    responses = await asyncio.gather(
        *[
            client.post(f"/api/adapt/candidates/{record_id}/promote")
            for record_id in record_ids
        ]
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    async with async_session() as restarted_db:
        active = (
            await restarted_db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalars().all()
        parent = (
            await restarted_db.execute(
                select(PromptVersion).where(PromptVersion.id == parent_id)
            )
        ).scalar_one()
    assert len(active) == 1
    assert parent.is_active is False


@pytest.mark.asyncio
async def test_promotion_repairs_legacy_multiple_active_rows(client, monkeypatch):
    from app.database import async_session
    from app.models import PromotionRecord, PromptVersion

    await _seed_split_suite()
    async with async_session() as db:
        db.add(PromptVersion(version=0, content="legacy rogue", is_active=True))
        await db.commit()
    await _run_candidate(monkeypatch)
    async with async_session() as db:
        record_id = (await db.execute(select(PromotionRecord.id))).scalar_one()

    response = await client.post(f"/api/adapt/candidates/{record_id}/promote")

    assert response.status_code == 200
    async with async_session() as restarted_db:
        active = (
            await restarted_db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalars().all()
    assert len(active) == 1
    assert active[0].parent_id is not None
