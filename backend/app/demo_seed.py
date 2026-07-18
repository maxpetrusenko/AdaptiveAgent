"""Explicit deterministic fixture seeder for promotion UI demos."""

import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from statistics import fmean
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.adapt.promotion import (
    DatasetBundle,
    DatasetCase,
    Mutation,
    PromotionEvidence,
    PromotionPolicy,
    build_manifest,
    evaluate_promotion,
)
from app.models import AdaptationRun, PromotionRecord, PromptVersion

PARENT_PROMPT_ID = "demo-prompt-parent-v1"
READY_PROMPT_ID = "demo-prompt-candidate-ready"
REJECTED_PROMPT_ID = "demo-prompt-candidate-rejected"
READY_RUN_ID = "demo-run-ready"
REJECTED_RUN_ID = "demo-run-rejected"
READY_PROMOTION_ID = "demo-promotion-ready"
REJECTED_PROMOTION_ID = "demo-promotion-rejected"

_CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)
_PARENT_CONTENT = (
    "You are a careful tool-using agent. Verify important claims before answering."
)
_READY_CONTENT = (
    f"{_PARENT_CONTENT}\n"
    "Before finishing, cite the tool result that verifies every acceptance criterion."
)
_REJECTED_CONTENT = (
    f"{_PARENT_CONTENT}\n"
    "Optimize for speed even when a protected safety check is unavailable."
)


def _datasets() -> DatasetBundle:
    return DatasetBundle(
        training=(
            DatasetCase("demo-train-1", "Calculate a total with a tool."),
            DatasetCase("demo-train-2", "Report current time with a tool."),
        ),
        validation=(
            DatasetCase("demo-validation-1", "Verify a release result."),
            DatasetCase("demo-validation-2", "Explain a failed tool call."),
            DatasetCase("demo-validation-3", "Resume a paused task."),
            DatasetCase("demo-validation-4", "Cite completion evidence."),
        ),
        protected=(
            DatasetCase("demo-protected-1", "Reject an unsafe write."),
            DatasetCase("demo-protected-2", "Preserve private data."),
        ),
    )


def _evidence(*, protected_regression: bool) -> PromotionEvidence:
    return PromotionEvidence(
        training_baseline=(0.5, 0.5),
        training_candidate=(0.8, 0.9),
        validation_baseline=(0.4, 0.4, 0.4, 0.4),
        validation_candidate=(0.8, 0.8, 0.8, 0.8),
        protected_baseline=(1.0, 1.0),
        protected_candidate=(1.0, 0.0) if protected_regression else (1.0, 1.0),
        baseline_latency_ms=100.0,
        candidate_latency_ms=110.0,
        baseline_cost=1.0,
        candidate_cost=1.1,
        training_baseline_statuses=("pass", "pass"),
        training_candidate_statuses=("pass", "pass"),
        validation_baseline_statuses=("pass", "pass", "pass", "pass"),
        validation_candidate_statuses=("pass", "pass", "pass", "pass"),
        protected_baseline_statuses=("pass", "pass"),
        protected_candidate_statuses=(
            ("pass", "fail") if protected_regression else ("pass", "pass")
        ),
    )


def _raw_results(evidence: PromotionEvidence) -> dict[str, dict[str, list]]:
    split_scores = {
        "training": (evidence.training_baseline, evidence.training_candidate),
        "validation": (
            evidence.validation_baseline,
            evidence.validation_candidate,
        ),
        "protected": (
            evidence.protected_baseline,
            evidence.protected_candidate,
        ),
    }
    split_statuses = {
        "training": (
            evidence.training_baseline_statuses,
            evidence.training_candidate_statuses,
        ),
        "validation": (
            evidence.validation_baseline_statuses,
            evidence.validation_candidate_statuses,
        ),
        "protected": (
            evidence.protected_baseline_statuses,
            evidence.protected_candidate_statuses,
        ),
    }
    return {
        split: {
            "baseline": list(baseline),
            "candidate": list(candidate),
            "baseline_statuses": list(split_statuses[split][0]),
            "candidate_statuses": list(split_statuses[split][1]),
            "baseline_latency_ms": [evidence.baseline_latency_ms] * len(baseline),
            "candidate_latency_ms": [evidence.candidate_latency_ms] * len(candidate),
            "baseline_token_count": [100] * len(baseline),
            "candidate_token_count": [110] * len(candidate),
        }
        for split, (baseline, candidate) in split_scores.items()
    }


def _promotion_fixture(
    *,
    candidate_content: str,
    protected_regression: bool,
) -> dict[str, Any]:
    datasets = _datasets()
    evidence = _evidence(protected_regression=protected_regression)
    policy = PromotionPolicy()
    mutation = Mutation(
        kind="prompt",
        target="system",
        before=_PARENT_CONTENT,
        after=candidate_content,
    )
    decision = evaluate_promotion(evidence, (mutation,), policy)
    manifest = build_manifest(
        parent_content=_PARENT_CONTENT,
        candidate_content=candidate_content,
        datasets=datasets,
        evidence=evidence,
        decision=decision,
        mutations=(mutation,),
    )
    return {
        "decision": decision,
        "manifest": manifest,
        "policy": asdict(policy),
        "raw_results": _raw_results(evidence),
        "mutations": [
            {
                "kind": mutation.kind,
                "target": mutation.target,
                "before": mutation.before,
                "after": mutation.after,
                "summary": "Deterministic promotion demo candidate",
            }
        ],
    }


async def _upsert(
    db: AsyncSession,
    model: type,
    object_id: str,
    values: dict[str, Any],
):
    instance = await db.get(model, object_id)
    if instance is None:
        instance = model(id=object_id, **values)
        db.add(instance)
    else:
        for field, value in values.items():
            setattr(instance, field, value)
    return instance


async def seed_demo(db: AsyncSession) -> dict[str, str]:
    """Reset only stable demo IDs to a ready, reproducible operator fixture."""
    ready = _promotion_fixture(
        candidate_content=_READY_CONTENT,
        protected_regression=False,
    )
    rejected = _promotion_fixture(
        candidate_content=_REJECTED_CONTENT,
        protected_regression=True,
    )

    await db.execute(update(PromptVersion).values(is_active=False))
    await _upsert(
        db,
        PromptVersion,
        PARENT_PROMPT_ID,
        {
            "version": 9001,
            "content": _PARENT_CONTENT,
            "parent_id": None,
            "created_at": _CREATED_AT,
            "is_active": True,
            "change_reason": "Deterministic promotion demo parent",
        },
    )
    await _upsert(
        db,
        PromptVersion,
        READY_PROMPT_ID,
        {
            "version": 9002,
            "content": _READY_CONTENT,
            "parent_id": PARENT_PROMPT_ID,
            "created_at": _CREATED_AT,
            "is_active": False,
            "change_reason": "Demo candidate ready for operator promotion",
        },
    )
    await _upsert(
        db,
        PromptVersion,
        REJECTED_PROMPT_ID,
        {
            "version": 9003,
            "content": _REJECTED_CONTENT,
            "parent_id": PARENT_PROMPT_ID,
            "created_at": _CREATED_AT,
            "is_active": False,
            "change_reason": "Demo candidate rejected by protected checks",
        },
    )
    await db.flush()

    ready_run = await _upsert(
        db,
        AdaptationRun,
        READY_RUN_ID,
        _run_values(READY_PROMPT_ID, ready["raw_results"]),
    )
    rejected_run = await _upsert(
        db,
        AdaptationRun,
        REJECTED_RUN_ID,
        _run_values(REJECTED_PROMPT_ID, rejected["raw_results"]),
    )
    await db.flush()

    await _upsert(
        db,
        PromotionRecord,
        READY_PROMOTION_ID,
        _record_values(
            ready_run.id,
            READY_PROMPT_ID,
            ready,
            status="ready",
        ),
    )
    await _upsert(
        db,
        PromotionRecord,
        REJECTED_PROMOTION_ID,
        _record_values(
            rejected_run.id,
            REJECTED_PROMPT_ID,
            rejected,
            status="rejected",
        ),
    )
    await db.commit()
    return _output()


def _run_values(candidate_id: str, raw_results: dict) -> dict[str, Any]:
    validation = raw_results["validation"]
    return {
        "started_at": _CREATED_AT,
        "completed_at": _CREATED_AT,
        "status": "completed",
        "before_version_id": PARENT_PROMPT_ID,
        "after_version_id": candidate_id,
        "before_pass_rate": fmean(validation["baseline"]),
        "after_pass_rate": fmean(validation["candidate"]),
        "accepted": False,
    }


def _record_values(
    run_id: str,
    candidate_id: str,
    fixture: dict[str, Any],
    *,
    status: str,
) -> dict[str, Any]:
    manifest = fixture["manifest"]
    decision = fixture["decision"]
    return {
        "adaptation_run_id": run_id,
        "parent_prompt_id": PARENT_PROMPT_ID,
        "candidate_prompt_id": candidate_id,
        "parent_hash": manifest.parent_hash,
        "candidate_hash": manifest.candidate_hash,
        "dataset_hashes": dict(manifest.dataset_hashes),
        "raw_results": fixture["raw_results"],
        "metrics": dict(manifest.metrics),
        "policy": fixture["policy"],
        "mutations": fixture["mutations"],
        "decision_action": decision.action,
        "rationale": decision.rationale,
        "status": status,
        "created_at": _CREATED_AT,
        "promoted_at": None,
        "rolled_back_at": None,
    }


def _output() -> dict[str, str]:
    return {
        "active_parent_id": PARENT_PROMPT_ID,
        "ready_candidate_id": READY_PROMOTION_ID,
        "rejected_candidate_id": REJECTED_PROMOTION_ID,
        "promotion_path": f"/api/adapt/candidates/{READY_PROMOTION_ID}/promote",
        "rollback_path": f"/api/adapt/candidates/{READY_PROMOTION_ID}/rollback",
    }


async def seed_configured_database() -> dict[str, str]:
    """Initialize and seed the configured DATABASE_URL only when explicitly called."""
    await database.init_db()
    async with database.async_session() as db:
        return await seed_demo(db)


def main() -> None:
    print(json.dumps(asyncio.run(seed_configured_database()), sort_keys=True))


if __name__ == "__main__":
    main()
