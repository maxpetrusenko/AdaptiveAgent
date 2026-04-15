"""CLI benchmark runner for adaptation quality.

Runs repeated evals before and after one adaptation loop, then writes a JSON report.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev

from sqlalchemy import select

from app.adapt.loop import create_adaptation_run, run_adaptation_loop
from app.database import async_session, init_db
from app.eval.runner import run_eval_suite
from app.models import EvalCase, EvalResult, EvalRun, PromptVersion
from app.seed import seed_eval_cases, seed_prompt_v1

STRESS_BASELINES = {
    "none": None,
    "tool-agnostic": (
        "You are an adaptive AI assistant. Answer directly from your own reasoning.\n\n"
        "Rules:\n"
        "- Never call any tools.\n"
        "- For time questions, say you do not have live time access.\n"
        "- For arithmetic, answer from mental math only.\n"
        "- Keep answers short and confident."
    ),
}


@dataclass
class RunSummary:
    run_id: str
    prompt_version_id: str
    pass_rate: float
    passed: int
    failed: int
    hallucination_failures: int
    protected_failures: int
    tag_pass_rates: dict[str, float]


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _safe_std(values: list[float]) -> float:
    return pstdev(values) if len(values) > 1 else 0.0


async def _summarize_run(db, run: EvalRun) -> RunSummary:
    results_query = await db.execute(
        select(EvalResult, EvalCase)
        .join(EvalCase, EvalResult.eval_case_id == EvalCase.id)
        .where(EvalResult.eval_run_id == run.id)
    )
    rows = results_query.all()

    hallucination_failures = 0
    protected_failures = 0
    tag_counts: dict[str, int] = {}
    tag_pass_counts: dict[str, int] = {}

    for result, case in rows:
        tags = case.tags if isinstance(case.tags, list) else []
        if result.error and "hallucination" in result.error.lower():
            hallucination_failures += 1
        if "protected" in tags and result.status != "pass":
            protected_failures += 1
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if result.status == "pass":
                tag_pass_counts[tag] = tag_pass_counts.get(tag, 0) + 1

    tag_pass_rates = {
        tag: tag_pass_counts.get(tag, 0) / total
        for tag, total in sorted(tag_counts.items())
    }

    return RunSummary(
        run_id=run.id,
        prompt_version_id=run.prompt_version_id,
        pass_rate=run.pass_rate or 0.0,
        passed=run.passed,
        failed=run.failed,
        hallucination_failures=hallucination_failures,
        protected_failures=protected_failures,
        tag_pass_rates=tag_pass_rates,
    )


async def _load_active_prompt(db) -> PromptVersion:
    result = await db.execute(
        select(PromptVersion).where(PromptVersion.is_active == True)  # noqa: E712
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise RuntimeError("No active prompt version found")
    return prompt


async def ensure_seed_state() -> None:
    await init_db()
    async with async_session() as db:
        await seed_prompt_v1(db)
        await seed_eval_cases(db)

        # Promote a small, fixed protected suite.
        protected_names = {
            "Simple greeting",
            "Math calculation",
            "Current time",
            "Factual knowledge",
            "Refusal - harmful",
        }
        cases = (await db.execute(select(EvalCase))).scalars().all()
        for case in cases:
            tags = case.tags if isinstance(case.tags, list) else []
            changed = False
            if "benchmark" not in tags:
                tags.append("benchmark")
                changed = True
            if case.name in protected_names and "protected" not in tags:
                tags.append("protected")
                changed = True
            if changed:
                case.tags = tags
        await db.commit()


async def _apply_stress_baseline(db, mode: str) -> None:
    """Replace the active prompt with a deliberately weak benchmark baseline."""
    content = STRESS_BASELINES.get(mode)
    if content is None:
        return

    prompts = (
        await db.execute(select(PromptVersion).order_by(PromptVersion.version.asc()))
    ).scalars().all()
    if not prompts:
        raise RuntimeError("No prompt versions available for stress baseline")

    for prompt in prompts:
        prompt.is_active = False

    baseline = prompts[0]
    baseline.content = content
    baseline.change_reason = f"Stress baseline: {mode}"
    baseline.is_active = True
    await db.commit()


async def _select_case_ids(
    db,
    *,
    tag: str | None,
    max_cases: int | None,
) -> list[str]:
    query = select(EvalCase).order_by(EvalCase.created_at.asc())
    cases = (await db.execute(query)).scalars().all()

    if tag:
        cases = [
            case
            for case in cases
            if isinstance(case.tags, list) and tag in case.tags
        ]
    if max_cases is not None:
        cases = cases[:max_cases]
    return [case.id for case in cases]


async def run_benchmark(
    repeats: int,
    *,
    case_tag: str | None = "benchmark",
    max_cases: int | None = None,
    consistency_repeats: int = 2,
    stress_baseline: str = "none",
) -> dict:
    await ensure_seed_state()

    async with async_session() as db:
        await _apply_stress_baseline(db, stress_baseline)
        baseline_prompt = await _load_active_prompt(db)
        case_ids = await _select_case_ids(db, tag=case_tag, max_cases=max_cases)
        if not case_ids:
            raise RuntimeError("No eval cases matched the requested benchmark filter")

        baseline_runs: list[RunSummary] = []
        for _ in range(repeats):
            baseline_runs.append(
                await _summarize_run(
                    db,
                    await run_eval_suite(
                        db,
                        case_ids=case_ids,
                        consistency_repeats=consistency_repeats,
                    ),
                )
            )

        adaptation_run = await create_adaptation_run(db)
        adaptation_run = await run_adaptation_loop(
            db,
            adaptation_run.id,
            case_ids=case_ids,
            consistency_repeats=consistency_repeats,
        )
        final_prompt = await _load_active_prompt(db)

        post_runs: list[RunSummary] = []
        for _ in range(repeats):
            post_runs.append(
                await _summarize_run(
                    db,
                    await run_eval_suite(
                        db,
                        case_ids=case_ids,
                        consistency_repeats=consistency_repeats,
                    ),
                )
            )

    baseline_pass_rates = [r.pass_rate for r in baseline_runs]
    post_pass_rates = [r.pass_rate for r in post_runs]

    report = {
        "baseline_prompt_version": baseline_prompt.version,
        "final_prompt_version": final_prompt.version,
        "adaptation": {
            "run_id": adaptation_run.id,
            "accepted": adaptation_run.accepted,
            "before_pass_rate": adaptation_run.before_pass_rate,
            "after_pass_rate": adaptation_run.after_pass_rate,
            "before_version_id": adaptation_run.before_version_id,
            "after_version_id": adaptation_run.after_version_id,
        },
        "baseline": {
            "runs": [r.__dict__ for r in baseline_runs],
            "mean_pass_rate": _safe_mean(baseline_pass_rates),
            "std_pass_rate": _safe_std(baseline_pass_rates),
        },
        "post_adaptation": {
            "runs": [r.__dict__ for r in post_runs],
            "mean_pass_rate": _safe_mean(post_pass_rates),
            "std_pass_rate": _safe_std(post_pass_rates),
        },
        "delta": {
            "mean_pass_rate_delta": _safe_mean(post_pass_rates) - _safe_mean(baseline_pass_rates),
            "active_prompt_changed": baseline_prompt.id != final_prompt.id,
        },
        "config": {
            "repeats": repeats,
            "case_tag": case_tag,
            "max_cases": max_cases,
            "consistency_repeats": consistency_repeats,
            "stress_baseline": stress_baseline,
            "case_count": len(case_ids),
        },
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run adaptation benchmark")
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Repeated eval runs before and after adaptation",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("benchmark-results/latest.json"),
        help="Path to JSON benchmark report",
    )
    parser.add_argument(
        "--case-tag",
        default="benchmark",
        help="Only include cases carrying this tag",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Limit benchmark to the first N matching cases",
    )
    parser.add_argument(
        "--consistency-repeats",
        type=int,
        default=2,
        help="Extra reruns for consistency-checked cases",
    )
    parser.add_argument(
        "--stress-baseline",
        default="none",
        choices=sorted(STRESS_BASELINES.keys()),
        help="Seed a deliberately weak active prompt to prove the adaptation loop can recover",
    )
    return parser


async def _async_main() -> int:
    args = build_parser().parse_args()
    report = await run_benchmark(
        repeats=args.repeats,
        case_tag=args.case_tag,
        max_cases=args.max_cases,
        consistency_repeats=args.consistency_repeats,
        stress_baseline=args.stress_baseline,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Benchmark report written to {args.out}")
    print(
        "Baseline mean pass rate: "
        f"{report['baseline']['mean_pass_rate']:.1%} "
        f"(std {report['baseline']['std_pass_rate']:.1%})"
    )
    print(
        "Post-adaptation mean pass rate: "
        f"{report['post_adaptation']['mean_pass_rate']:.1%} "
        f"(std {report['post_adaptation']['std_pass_rate']:.1%})"
    )
    print(
        "Adaptation accepted: "
        f"{report['adaptation']['accepted']} | "
        f"Prompt changed: {report['delta']['active_prompt_changed']}"
    )
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
