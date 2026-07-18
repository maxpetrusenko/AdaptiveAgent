"""Verifier-gated prompt adaptation orchestration."""

from dataclasses import asdict
from datetime import datetime, timezone
from statistics import fmean

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapt.promotion import (
    DatasetBundle,
    DatasetCase,
    Mutation,
    PromotionEvidence,
    PromotionPolicy,
    build_manifest,
    evaluate_promotion,
)
from app.adapt.prompt_updater import create_prompt_version, generate_improved_prompt
from app.eval.runner import run_eval_suite
from app.models import (
    AdaptationRun,
    EvalCase,
    EvalResult,
    PromotionRecord,
    PromptVersion,
)

SPLIT_TAGS = frozenset({"training", "validation", "protected"})


async def run_adaptation_loop(
    db: AsyncSession,
    adaptation_run_id: str,
    case_ids: list[str] | None = None,
    consistency_repeats: int = 2,
) -> AdaptationRun:
    """Evaluate and persist a candidate without granting activation authority."""
    adapt_run = (
        await db.execute(
            select(AdaptationRun).where(AdaptationRun.id == adaptation_run_id)
        )
    ).scalar_one_or_none()
    if not adapt_run:
        raise ValueError(f"Adaptation run {adaptation_run_id} not found")

    try:
        current_prompt = (
            await db.execute(
                select(PromptVersion)
                .where(PromptVersion.is_active == True)  # noqa: E712
                .order_by(PromptVersion.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not current_prompt:
            raise ValueError("No active prompt version found")

        split_cases = await _load_split_cases(db, case_ids)
        datasets = _dataset_bundle(split_cases)
        policy = PromotionPolicy()

        baseline_training = await run_eval_suite(
            db,
            case_ids=_case_ids(split_cases["training"]),
            consistency_repeats=consistency_repeats,
            prompt_version_id=current_prompt.id,
        )
        improved_content = await generate_improved_prompt(
            db,
            current_prompt.content,
            baseline_training.id,
        )
        mutation = Mutation(
            kind="prompt",
            target="system",
            before=current_prompt.content,
            after=improved_content,
        )
        candidate = await create_prompt_version(
            db,
            content=improved_content,
            parent_id=current_prompt.id,
            change_reason=f"Candidate from adaptation run {adapt_run.id}",
            activate=False,
        )

        candidate_training = await run_eval_suite(
            db,
            case_ids=_case_ids(split_cases["training"]),
            consistency_repeats=consistency_repeats,
            prompt_version_id=candidate.id,
        )
        baseline_validation = await run_eval_suite(
            db,
            case_ids=_case_ids(split_cases["validation"]),
            consistency_repeats=consistency_repeats,
            prompt_version_id=current_prompt.id,
        )
        candidate_validation = await run_eval_suite(
            db,
            case_ids=_case_ids(split_cases["validation"]),
            consistency_repeats=consistency_repeats,
            prompt_version_id=candidate.id,
        )
        baseline_protected = await run_eval_suite(
            db,
            case_ids=_case_ids(split_cases["protected"]),
            consistency_repeats=consistency_repeats,
            prompt_version_id=current_prompt.id,
        )
        candidate_protected = await run_eval_suite(
            db,
            case_ids=_case_ids(split_cases["protected"]),
            consistency_repeats=consistency_repeats,
            prompt_version_id=candidate.id,
        )

        raw_results = {
            "training": await _paired_run_results(
                db, baseline_training.id, candidate_training.id
            ),
            "validation": await _paired_run_results(
                db, baseline_validation.id, candidate_validation.id
            ),
            "protected": await _paired_run_results(
                db, baseline_protected.id, candidate_protected.id
            ),
        }
        evidence = _promotion_evidence(raw_results)
        mutations = (mutation,)
        decision = evaluate_promotion(evidence, mutations, policy)
        manifest = build_manifest(
            parent_content=current_prompt.content,
            candidate_content=candidate.content,
            datasets=datasets,
            evidence=evidence,
            decision=decision,
            mutations=mutations,
        )

        record = PromotionRecord(
            adaptation_run_id=adapt_run.id,
            parent_prompt_id=current_prompt.id,
            candidate_prompt_id=candidate.id,
            parent_hash=manifest.parent_hash,
            candidate_hash=manifest.candidate_hash,
            dataset_hashes=dict(manifest.dataset_hashes),
            raw_results=raw_results,
            metrics=dict(manifest.metrics),
            policy=asdict(policy),
            mutations=[
                {
                    "kind": mutation.kind,
                    "target": mutation.target,
                    "before": mutation.before,
                    "after": mutation.after,
                    "summary": "System prompt candidate",
                }
            ],
            decision_action=decision.action,
            rationale=decision.rationale,
            status="ready" if decision.action == "promote" else "rejected",
        )
        db.add(record)

        adapt_run.before_version_id = current_prompt.id
        adapt_run.after_version_id = candidate.id
        adapt_run.before_pass_rate = _mean(raw_results["validation"]["baseline"])
        adapt_run.after_pass_rate = _mean(raw_results["validation"]["candidate"])
        adapt_run.accepted = False
        adapt_run.status = "completed"
        adapt_run.completed_at = datetime.now(timezone.utc)
        candidate.change_reason = (
            f"{candidate.change_reason} | "
            f"{record.status.title()}: {decision.rationale}"
        )
        await db.commit()
        await db.refresh(adapt_run)
        return adapt_run
    except Exception:
        adapt_run.status = "failed"
        adapt_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise


async def create_adaptation_run(db: AsyncSession) -> AdaptationRun:
    """Create an adaptation run bound to the currently active parent."""
    current_prompt = (
        await db.execute(
            select(PromptVersion)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .order_by(PromptVersion.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not current_prompt:
        raise ValueError("No active prompt version found")

    adapt_run = AdaptationRun(
        status="running",
        before_version_id=current_prompt.id,
        before_pass_rate=0.0,
    )
    db.add(adapt_run)
    await db.commit()
    await db.refresh(adapt_run)
    return adapt_run


async def _load_split_cases(
    db: AsyncSession,
    case_ids: list[str] | None,
) -> dict[str, list[EvalCase]]:
    query = select(EvalCase).order_by(EvalCase.id)
    if case_ids is not None:
        query = query.where(EvalCase.id.in_(case_ids))
    cases = (await db.execute(query)).scalars().all()
    splits: dict[str, list[EvalCase]] = {name: [] for name in SPLIT_TAGS}

    for case in cases:
        tags = set(case.tags) if isinstance(case.tags, list) else set()
        assigned = tags & SPLIT_TAGS
        if len(assigned) > 1:
            raise ValueError(
                f"Eval case {case.id} belongs to multiple governed splits"
            )
        if assigned:
            splits[assigned.pop()].append(case)

    if not splits["training"]:
        raise ValueError("training split must not be empty")
    if len(splits["validation"]) < 2:
        raise ValueError("validation split requires at least two cases")
    if not splits["protected"]:
        raise ValueError("protected split must not be empty")
    return splits


def _dataset_bundle(split_cases: dict[str, list[EvalCase]]) -> DatasetBundle:
    def references(name: str) -> tuple[DatasetCase, ...]:
        return tuple(
            DatasetCase(
                case_id=case.id,
                content=(
                    f"{case.name}\nINPUT:{case.input}\n"
                    f"EXPECTED:{case.expected_output}"
                ),
            )
            for case in split_cases[name]
        )

    return DatasetBundle(
        training=references("training"),
        validation=references("validation"),
        protected=references("protected"),
    )


def _case_ids(cases: list[EvalCase]) -> list[str]:
    return [case.id for case in cases]


async def _paired_run_results(
    db: AsyncSession,
    baseline_run_id: str,
    candidate_run_id: str,
) -> dict:
    baseline = await _run_results(db, baseline_run_id)
    candidate = await _run_results(db, candidate_run_id)
    if baseline["case_ids"] != candidate["case_ids"]:
        raise ValueError("Baseline and candidate eval results are not paired")
    return {
        "case_ids": baseline["case_ids"],
        "baseline": baseline["scores"],
        "candidate": candidate["scores"],
        "baseline_statuses": baseline["statuses"],
        "candidate_statuses": candidate["statuses"],
        "baseline_latency_ms": baseline["latency_ms"],
        "candidate_latency_ms": candidate["latency_ms"],
        "baseline_token_count": baseline["token_count"],
        "candidate_token_count": candidate["token_count"],
    }


async def _run_results(db: AsyncSession, run_id: str) -> dict:
    results = (
        await db.execute(
            select(EvalResult)
            .where(EvalResult.eval_run_id == run_id)
            .order_by(EvalResult.eval_case_id)
        )
    ).scalars().all()
    return {
        "case_ids": [result.eval_case_id for result in results],
        "scores": [
            float(result.score) if result.score is not None else 0.0
            for result in results
        ],
        "statuses": [result.status for result in results],
        "latency_ms": [float(result.latency_ms) for result in results],
        "token_count": [
            int(result.token_count) if result.token_count is not None else None
            for result in results
        ],
    }


def _promotion_evidence(raw_results: dict) -> PromotionEvidence:
    baseline_latency = [
        value
        for split in raw_results.values()
        for value in split["baseline_latency_ms"]
    ]
    candidate_latency = [
        value
        for split in raw_results.values()
        for value in split["candidate_latency_ms"]
    ]
    baseline_tokens = [
        value
        for split in raw_results.values()
        for value in split["baseline_token_count"]
    ]
    candidate_tokens = [
        value
        for split in raw_results.values()
        for value in split["candidate_token_count"]
    ]
    return PromotionEvidence(
        training_baseline=tuple(raw_results["training"]["baseline"]),
        training_candidate=tuple(raw_results["training"]["candidate"]),
        validation_baseline=tuple(raw_results["validation"]["baseline"]),
        validation_candidate=tuple(raw_results["validation"]["candidate"]),
        protected_baseline=tuple(raw_results["protected"]["baseline"]),
        protected_candidate=tuple(raw_results["protected"]["candidate"]),
        baseline_latency_ms=_mean(baseline_latency),
        candidate_latency_ms=_mean(candidate_latency),
        baseline_cost=_token_cost(baseline_tokens),
        candidate_cost=_token_cost(candidate_tokens),
        training_baseline_statuses=tuple(
            raw_results["training"]["baseline_statuses"]
        ),
        training_candidate_statuses=tuple(
            raw_results["training"]["candidate_statuses"]
        ),
        validation_baseline_statuses=tuple(
            raw_results["validation"]["baseline_statuses"]
        ),
        validation_candidate_statuses=tuple(
            raw_results["validation"]["candidate_statuses"]
        ),
        protected_baseline_statuses=tuple(
            raw_results["protected"]["baseline_statuses"]
        ),
        protected_candidate_statuses=tuple(
            raw_results["protected"]["candidate_statuses"]
        ),
    )


def _mean(values: list[float]) -> float:
    return fmean(values) if values else 0.0


def _token_cost(values: list[int | None]) -> float:
    if any(value is None for value in values):
        return float("nan")
    return float(sum(value for value in values if value is not None))
