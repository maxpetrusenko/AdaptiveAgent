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


async def run_benchmark(repeats: int) -> dict:
    await ensure_seed_state()

    async with async_session() as db:
        baseline_prompt = await _load_active_prompt(db)

        baseline_runs: list[RunSummary] = []
        for _ in range(repeats):
            baseline_runs.append(await _summarize_run(db, await run_eval_suite(db)))

        adaptation_run = await create_adaptation_run(db)
        adaptation_run = await run_adaptation_loop(db, adaptation_run.id)
        final_prompt = await _load_active_prompt(db)

        post_runs: list[RunSummary] = []
        for _ in range(repeats):
            post_runs.append(await _summarize_run(db, await run_eval_suite(db)))

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
    return parser


async def _async_main() -> int:
    args = build_parser().parse_args()
    report = await run_benchmark(repeats=args.repeats)

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
