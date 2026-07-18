from hashlib import sha256

import pytest
from sqlalchemy import select


def _install_candidate_benchmark(monkeypatch, *, decision: str = "promote"):
    from app.database import async_session
    from app.models import (
        AdaptationRun,
        EvalCase,
        EvalRun,
        PromotionRecord,
        PromptVersion,
    )

    async def fake_ensure_seed_state():
        async with async_session() as db:
            db.add(
                PromptVersion(
                    version=1,
                    content="Base prompt",
                    is_active=True,
                    change_reason="seed",
                )
            )
            db.add(
                EvalCase(
                    name="Case",
                    input="hi",
                    expected_output="hello",
                    tags=["benchmark", "training"],
                    source="manual",
                )
            )
            await db.commit()

    async def fake_run_eval_suite(
        db,
        eval_run_id=None,
        case_ids=None,
        consistency_repeats=2,
        prompt_version_id=None,
    ):
        if prompt_version_id:
            prompt = await db.get(PromptVersion, prompt_version_id)
        else:
            prompt = (
                await db.execute(
                    select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
                )
            ).scalar_one()
        run = EvalRun(
            id=eval_run_id,
            prompt_version_id=prompt.id,
            status="completed",
            total=1,
            passed=1,
            failed=0,
            pass_rate=1.0,
        )
        if not eval_run_id:
            db.add(run)
            await db.commit()
            await db.refresh(run)
        else:
            existing = (
                await db.execute(
                    __import__("sqlalchemy").select(EvalRun).where(EvalRun.id == eval_run_id)
                )
            ).scalar_one()
            existing.status = "completed"
            existing.passed = 1
            existing.failed = 0
            existing.pass_rate = 1.0
            run = existing
            await db.commit()
        return run

    async def fake_create_adaptation_run(db):
        active = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        run = AdaptationRun(
            status="running",
            before_version_id=active.id,
            before_pass_rate=1.0,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    async def fake_run_adaptation_loop(
        db,
        run_id,
        case_ids=None,
        consistency_repeats=2,
    ):
        parent = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
        candidate = PromptVersion(
            version=2,
            content=f"Candidate {decision}",
            is_active=False,
            parent_id=parent.id,
            change_reason="benchmark candidate",
        )
        db.add(candidate)
        await db.flush()
        run = (
            await db.execute(
                select(AdaptationRun).where(AdaptationRun.id == run_id)
            )
        ).scalar_one()
        run.accepted = False
        run.status = "completed"
        run.after_version_id = candidate.id
        run.after_pass_rate = 1.0
        db.add(
            PromotionRecord(
                adaptation_run_id=run.id,
                parent_prompt_id=parent.id,
                candidate_prompt_id=candidate.id,
                parent_hash=sha256(parent.content.encode()).hexdigest(),
                candidate_hash=sha256(candidate.content.encode()).hexdigest(),
                dataset_hashes={
                    "training": "train-hash",
                    "validation": "validation-hash",
                    "protected": "protected-hash",
                },
                raw_results={
                    "training": {"baseline": [0.5], "candidate": [1.0]},
                    "validation": {"baseline": [0.5, 0.5], "candidate": [1.0, 1.0]},
                    "protected": {
                        "baseline": [1.0],
                        "candidate": [1.0 if decision == "promote" else 0.0],
                    },
                },
                metrics={
                    "validation_quality_delta": 0.5,
                    "lower_confidence_bound": 0.5,
                    "latency_ratio": 1.0,
                    "cost_ratio": 1.0,
                },
                policy={"min_validation_delta": 0.05},
                mutations=[
                    {
                        "kind": "prompt",
                        "target": "system",
                        "before": parent.content,
                        "after": candidate.content,
                        "summary": "Benchmark candidate",
                    }
                ],
                decision_action=decision,
                rationale=(
                    "Validated candidate"
                    if decision == "promote"
                    else "Protected regression"
                ),
                status="ready" if decision == "promote" else "rejected",
            )
        )
        await db.commit()
        return run

    async def fake_summarize_run(db, run):
        from app.benchmarks.run import RunSummary

        return RunSummary(
            run_id=run.id,
            prompt_version_id=run.prompt_version_id,
            pass_rate=run.pass_rate or 0.0,
            passed=run.passed,
            failed=run.failed,
            hallucination_failures=0,
            protected_failures=0,
            tag_pass_rates={"benchmark": 1.0, "protected": 1.0},
        )

    monkeypatch.setattr("app.benchmarks.run.ensure_seed_state", fake_ensure_seed_state)
    monkeypatch.setattr("app.benchmarks.run.async_session", async_session)
    monkeypatch.setattr("app.benchmarks.run.run_eval_suite", fake_run_eval_suite)
    monkeypatch.setattr(
        "app.benchmarks.run.create_adaptation_run", fake_create_adaptation_run
    )
    monkeypatch.setattr(
        "app.benchmarks.run.run_adaptation_loop", fake_run_adaptation_loop
    )
    monkeypatch.setattr("app.benchmarks.run._summarize_run", fake_summarize_run)


@pytest.mark.asyncio
async def test_benchmark_evaluates_candidate_without_changing_active_prompt(monkeypatch):
    from app.benchmarks.run import run_benchmark
    from app.database import async_session
    from app.models import PromptVersion

    _install_candidate_benchmark(monkeypatch)
    report = await run_benchmark(repeats=2)

    assert report["baseline"]["mean_pass_rate"] == 1.0
    assert report["post_adaptation"]["mean_pass_rate"] == 1.0
    assert report["adaptation"]["accepted"] is False
    assert report["candidate"]["status"] == "ready"
    assert report["candidate"]["decision"] == "promote"
    assert report["candidate"]["id"]
    assert report["candidate"]["parent_hash"]
    assert report["candidate"]["candidate_hash"]
    assert report["candidate"]["evaluated"] is True
    assert report["candidate"]["promoted"] is False
    assert report["delta"]["active_prompt_changed"] is False
    assert {
        run["prompt_version_id"] for run in report["post_adaptation"]["runs"]
    } == {report["candidate"]["prompt_version_id"]}
    async with async_session() as db:
        active = (
            await db.execute(
                select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
            )
        ).scalar_one()
    assert active.id == report["adaptation"]["before_version_id"]


@pytest.mark.asyncio
async def test_benchmark_explicitly_promotes_eligible_candidate(monkeypatch):
    from app.benchmarks.run import run_benchmark

    _install_candidate_benchmark(monkeypatch)
    report = await run_benchmark(repeats=1, promote_candidate=True)

    assert report["adaptation"]["accepted"] is True
    assert report["candidate"]["promoted"] is True
    assert report["candidate"]["status"] == "promoted"
    assert report["delta"]["active_prompt_changed"] is True
    assert report["final_prompt_version"] == 2


@pytest.mark.asyncio
async def test_benchmark_rejected_candidate_never_activates(monkeypatch):
    from app.benchmarks.run import run_benchmark

    _install_candidate_benchmark(monkeypatch, decision="reject")
    report = await run_benchmark(repeats=1, promote_candidate=True)

    assert report["adaptation"]["accepted"] is False
    assert report["candidate"]["decision"] == "reject"
    assert report["candidate"]["status"] == "rejected"
    assert report["candidate"]["promoted"] is False
    assert report["delta"]["active_prompt_changed"] is False


@pytest.mark.asyncio
async def test_benchmark_stress_baseline_rewrites_seed_prompt():
    from app.benchmarks.run import STRESS_BASELINES, _apply_stress_baseline
    from app.database import async_session
    from app.models import PromptVersion

    assert STRESS_BASELINES["tool-agnostic"] is not None

    async with async_session() as db:
        db.add(
            PromptVersion(
                version=1,
                content="Base prompt",
                is_active=True,
                change_reason="seed",
            )
        )
        await db.commit()

        await _apply_stress_baseline(db, "tool-agnostic")

        active_prompt = (
            await db.execute(select(PromptVersion).where(PromptVersion.is_active == True))  # noqa: E712
        ).scalar_one()

    assert "Never call any tools" in active_prompt.content
    assert active_prompt.change_reason == "Stress baseline: tool-agnostic"
