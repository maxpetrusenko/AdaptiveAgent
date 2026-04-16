"""CLI wrapper for the comparative benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.benchmarks.compare import (
    _render_leaderboard,
    _render_trajectory,
    run_compare_benchmark,
)
from app.benchmarks.compare_suite import eval_cases, train_cases
from app.benchmarks.report_html import render_report_file


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_running_report(
    *,
    repeats: int,
    adaptation_cycles: int,
    bootstrap_samples: int,
    consistency_repeats: int,
    train_cases_subset: list[Any],
    eval_cases_subset: list[Any],
    include_judge_calibration: bool,
    include_harness_checks: bool,
) -> dict[str, Any]:
    return {
        "status": "running",
        "suite": {
            "train_cases": [asdict(case) for case in train_cases_subset],
            "eval_cases": [asdict(case) for case in eval_cases_subset],
        },
        "config": {
            "repeats": repeats,
            "adaptation_cycles": adaptation_cycles,
            "bootstrap_samples": bootstrap_samples,
            "consistency_repeats": consistency_repeats,
            "train_case_count": len(train_cases_subset),
            "eval_case_count": len(eval_cases_subset),
            "include_judge_calibration": include_judge_calibration,
            "include_harness_checks": include_harness_checks,
        },
        "progress": {
            "completed_steps": [],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run comparative adaptive-agent benchmark")
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="How many times to run each system on the held-out eval split",
    )
    parser.add_argument(
        "--cycles",
        "--adaptation-cycles",
        dest="adaptation_cycles",
        type=int,
        default=3,
        help="How many adaptation cycles to run for the adaptive agent",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=2000,
        help="How many bootstrap samples to use for confidence intervals",
    )
    parser.add_argument(
        "--consistency-repeats",
        type=int,
        default=0,
        help="How many internal consistency repeats to use during adaptation",
    )
    parser.add_argument(
        "--max-train-cases",
        type=int,
        default=None,
        help="Optional train-split subset size",
    )
    parser.add_argument(
        "--max-eval-cases",
        type=int,
        default=None,
        help="Optional eval-split subset size",
    )
    parser.add_argument(
        "--skip-judge-calibration",
        action="store_true",
        help="Skip the labeled judge calibration pass",
    )
    parser.add_argument(
        "--skip-harness-checks",
        action="store_true",
        help="Skip null-agent and judge-bias adversarial probes",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("benchmark-results/compare.json"),
        help="Path to JSON benchmark report",
    )
    return parser


async def _async_main() -> int:
    args = build_parser().parse_args()
    train_cases_subset = train_cases(args.max_train_cases)
    eval_cases_subset = eval_cases(args.max_eval_cases)

    running_report = _build_running_report(
        repeats=args.repeats,
        adaptation_cycles=args.adaptation_cycles,
        bootstrap_samples=args.bootstrap_samples,
        consistency_repeats=args.consistency_repeats,
        train_cases_subset=train_cases_subset,
        eval_cases_subset=eval_cases_subset,
        include_judge_calibration=not args.skip_judge_calibration,
        include_harness_checks=not args.skip_harness_checks,
    )
    _write_json(args.out, running_report)

    progress_steps: list[dict[str, Any]] = []

    def progress_cb(payload: dict[str, Any]) -> None:
        progress_steps.append(payload)
        running_report["progress"]["completed_steps"] = progress_steps[-20:]
        _write_json(args.out, running_report)

    try:
        report = await run_compare_benchmark(
            repeats=args.repeats,
            adaptation_cycles=args.adaptation_cycles,
            bootstrap_samples=args.bootstrap_samples,
            consistency_repeats=args.consistency_repeats,
            max_train_cases=args.max_train_cases,
            max_eval_cases=args.max_eval_cases,
            include_judge_calibration=not args.skip_judge_calibration,
            include_harness_checks=not args.skip_harness_checks,
            progress_cb=progress_cb,
        )
    except BaseException as exc:
        running_report["status"] = "failed"
        running_report["error"] = str(exc)
        _write_json(args.out, running_report)
        raise

    _write_json(args.out, report)
    html_out = render_report_file(args.out)
    print(_render_leaderboard(report["leaderboard"], report["pairwise"]))
    print()
    print(_render_trajectory(report["trajectory"]["summary"]))
    print(f"\nBenchmark report written to {args.out}")
    print(f"HTML report written to {html_out}")
    return 0


def main() -> int:
    return asyncio.run(_async_main())
