"""Comparative benchmark entrypoint and report orchestration."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.agent.prompts import SYSTEM_PROMPT_V1
from app.benchmarks.adversarial import run_adversarial_benchmark
from app.benchmarks.compare_metrics import (
    aggregate_pairwise_runs as _aggregate_pairwise_runs,
)
from app.benchmarks.compare_metrics import (
    aggregate_system_runs as _aggregate_system_runs,
)
from app.benchmarks.compare_metrics import (
    aggregate_trajectory_runs as _aggregate_trajectory_runs,
)
from app.benchmarks.compare_metrics import (
    pairwise_delta as _pairwise_delta,
)
from app.benchmarks.compare_metrics import (
    render_leaderboard as _render_leaderboard,
)
from app.benchmarks.compare_runners import (
    run_adaptive_agent_benchmark as _run_adaptive_agent_benchmark,
)
from app.benchmarks.compare_runners import (
    run_direct_llm_benchmark as _run_direct_llm_benchmark,
)
from app.benchmarks.compare_runners import (
    run_sdk_tool_baseline as _run_sdk_tool_baseline,
)
from app.benchmarks.compare_runners import (
    run_tool_agent_benchmark as _run_tool_agent_benchmark,
)
from app.benchmarks.compare_suite import eval_cases, train_cases
from app.benchmarks.compare_types import CaseResult, SystemSummary
from app.benchmarks.judge_calibration import run_judge_calibration
from app.benchmarks.report_html import render_report_file

WEAK_TOOL_PROMPT = """You are an adaptive AI assistant.

Rules:
- Never call any tools.
- For time questions, say you do not have live time access.
- For arithmetic, answer from mental math only.
- Keep answers short and confident.
"""

DIRECT_LLM_PROMPT = """You are a concise, helpful assistant.

Answer directly. If you cannot verify something current, say so plainly.
"""

_aggregate_pairwise = _aggregate_pairwise_runs
run_direct_llm_benchmark = _run_direct_llm_benchmark
run_tool_agent_benchmark = _run_tool_agent_benchmark
run_adaptive_agent_benchmark = _run_adaptive_agent_benchmark
run_sdk_tool_baseline = _run_sdk_tool_baseline

__all__ = [
    "CaseResult",
    "SystemSummary",
    "_aggregate_pairwise",
    "_aggregate_system_runs",
    "_pairwise_delta",
    "_render_leaderboard",
    "run_compare_benchmark",
    "run_direct_llm_benchmark",
    "run_tool_agent_benchmark",
    "run_adaptive_agent_benchmark",
    "run_sdk_tool_baseline",
    "build_parser",
    "main",
]


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
            "train_cases": [case.__dict__ for case in train_cases_subset],
            "eval_cases": [case.__dict__ for case in eval_cases_subset],
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


def _render_trajectory(summary: dict[str, Any]) -> str:
    lines = ["Trajectory:"]
    initial_usage = summary["initial"].get("usage_totals", {})
    initial_token_text = ""
    if "total_tokens" in initial_usage:
        initial_token_text = f", tokens={initial_usage['total_tokens']['mean']:.0f}"
    lines.append(
        f"Initial eval pass_rate={summary['initial']['pass_rate']:.1%} "
        f"[{summary['initial']['pass_rate_ci_95'][0]:.1%}, "
        f"{summary['initial']['pass_rate_ci_95'][1]:.1%}]"
        f"{initial_token_text}"
    )
    for cycle in summary["cycles"]:
        eval_usage = cycle["eval"].get("usage_totals", {})
        token_text = ""
        if "total_tokens" in eval_usage:
            token_text = f", tokens={eval_usage['total_tokens']['mean']:.0f}"
        lines.append(
            f"- cycle {cycle['cycle']}: "
            f"eval={cycle['eval_pass_rate']['mean']:.1%} "
            f"[{cycle['eval_pass_rate']['ci_95'][0]:.1%}, "
            f"{cycle['eval_pass_rate']['ci_95'][1]:.1%}], "
            f"gain={cycle['gain']['eval_pass_rate_delta_from_start']['mean']:+.1%}, "
            f"stability={cycle['stability']['eval_pass_rate_delta_from_previous']['mean']:+.1%}, "
            f"alignment={cycle['alignment']['hallucination_rate']['mean']:.1%} hallucination rate"
            f"{token_text}"
        )
    return "\n".join(lines)


async def run_compare_benchmark(
    *,
    repeats: int = 3,
    adaptation_cycles: int = 3,
    bootstrap_samples: int = 2000,
    consistency_repeats: int = 0,
    max_train_cases: int | None = None,
    max_eval_cases: int | None = None,
    include_judge_calibration: bool = True,
    include_harness_checks: bool = True,
    progress_cb=None,
) -> dict[str, Any]:
    train_cases_subset = train_cases(max_train_cases)
    eval_cases_subset = eval_cases(max_eval_cases)

    system_runs: dict[str, list[SystemSummary]] = {
        "direct_llm": [],
        "weak_static_agent": [],
        "adaptive_agent": [],
        "seed_tool_agent": [],
        "sdk_tool_agent": [],
    }
    adaptive_trajectories: list[dict[str, Any]] = []
    total_steps = repeats * len(system_runs)
    completed_steps = 0

    def emit_progress(message: str, **extra: Any) -> None:
        nonlocal completed_steps
        payload = {
            "message": message,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            **extra,
        }
        print(message, flush=True)
        if progress_cb is not None:
            progress_cb(payload)

    for repeat_idx in range(1, repeats + 1):
        emit_progress(f"[repeat {repeat_idx}/{repeats}] direct_llm: start")
        system_runs["direct_llm"].append(
            await run_direct_llm_benchmark(
                eval_cases_subset=eval_cases_subset,
                system_prompt=DIRECT_LLM_PROMPT,
            )
        )
        completed_steps += 1
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] direct_llm: done",
            system="direct_llm",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] weak_static_agent: start")
        system_runs["weak_static_agent"].append(
            await run_tool_agent_benchmark(
                system_name="weak_static_agent",
                prompt_text=WEAK_TOOL_PROMPT,
                eval_cases_subset=eval_cases_subset,
            )
        )
        completed_steps += 1
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] weak_static_agent: done",
            system="weak_static_agent",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] adaptive_agent: start")
        adaptive_summary, trajectory = await run_adaptive_agent_benchmark(
            weak_prompt=WEAK_TOOL_PROMPT,
            adaptation_cycles=adaptation_cycles,
            consistency_repeats=consistency_repeats,
            eval_cases_subset=eval_cases_subset,
            train_cases_subset=train_cases_subset,
        )
        system_runs["adaptive_agent"].append(adaptive_summary)
        adaptive_trajectories.append(trajectory)
        completed_steps += 1
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] adaptive_agent: done",
            system="adaptive_agent",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] seed_tool_agent: start")
        system_runs["seed_tool_agent"].append(
            await run_tool_agent_benchmark(
                system_name="seed_tool_agent",
                prompt_text=SYSTEM_PROMPT_V1,
                eval_cases_subset=eval_cases_subset,
            )
        )
        completed_steps += 1
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] seed_tool_agent: done",
            system="seed_tool_agent",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] sdk_tool_agent: start")
        system_runs["sdk_tool_agent"].append(
            await run_sdk_tool_baseline(
                prompt_text=SYSTEM_PROMPT_V1,
                eval_cases_subset=eval_cases_subset,
            )
        )
        completed_steps += 1
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] sdk_tool_agent: done",
            system="sdk_tool_agent",
            repeat=repeat_idx,
        )

    summaries = [
        _aggregate_system_runs(system, runs, bootstrap_samples=bootstrap_samples)
        for system, runs in system_runs.items()
    ]
    adaptive_runs = system_runs["adaptive_agent"]
    pairwise = {
        system: _aggregate_pairwise_runs(
            adaptive_runs,
            baseline_runs,
            bootstrap_samples=bootstrap_samples,
        )
        for system, baseline_runs in system_runs.items()
        if system != "adaptive_agent"
    }
    leaderboard = [
        {"rank": idx, **summary}
        for idx, summary in enumerate(
            sorted(
                summaries,
                key=lambda item: (-item["pass_rate_mean"], item["avg_latency_ms_mean"]),
            ),
            start=1,
        )
    ]

    hardening = None
    if include_harness_checks:
        emit_progress("hardening: start")
        hardening = await run_adversarial_benchmark(max_cases=max_eval_cases)
        hardening["hardening_checks"]["evaluator_isolation"] = {
            "agent_and_evaluator_share_process": True,
            "note": "Agent execution and evaluator logic still share one Python process.",
        }
        emit_progress("hardening: done")

    judge_calibration = None
    if include_judge_calibration:
        emit_progress("judge_calibration: start")
        judge_calibration = await run_judge_calibration()
        emit_progress("judge_calibration: done")

    report = {
        "status": "completed",
        "suite": {
            "train_cases": [case.__dict__ for case in train_cases_subset],
            "eval_cases": [case.__dict__ for case in eval_cases_subset],
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
        "systems": summaries,
        "leaderboard": leaderboard,
        "pairwise": pairwise,
        "trajectory": {
            "runs": adaptive_trajectories,
            "summary": _aggregate_trajectory_runs(
                adaptive_trajectories,
                bootstrap_samples=bootstrap_samples,
            ),
        },
        "judge_calibration": judge_calibration,
        "hardening": hardening,
        "harness_checks": hardening,
    }
    return report


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


if __name__ == "__main__":
    raise SystemExit(main())
