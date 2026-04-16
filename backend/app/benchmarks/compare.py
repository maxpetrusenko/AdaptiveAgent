"""Comparative benchmark entrypoint and report orchestration."""

from __future__ import annotations

from dataclasses import asdict
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


def _error_summary(
    *,
    system: str,
    eval_cases_subset: list[Any],
    error: Exception,
) -> SystemSummary:
    results = [
        CaseResult(
            case_name=case.name,
            status="error",
            score=0.0,
            error=str(error),
            actual_output="",
            latency_ms=0,
            usage=None,
        )
        for case in eval_cases_subset
    ]
    return SystemSummary(
        system=system,
        pass_rate=0.0,
        passed=0,
        failed=len(eval_cases_subset),
        avg_latency_ms=0.0,
        hallucination_failures=0,
        tag_pass_rates={},
        results=results,
        metadata={"runner_error": str(error)},
    )


def _render_trajectory(summary: dict[str, Any]) -> str:
    initial = summary.get("initial", {})
    if "pass_rate" not in initial:
        lines = ["Trajectory:"]
        lines.append("Trajectory unavailable for adaptive agent.")
        for error in summary.get("errors", []):
            if error:
                lines.append(f"- error: {error}")
        return "\n".join(lines)

    lines = ["Trajectory:"]
    initial_usage = initial.get("usage_totals", {})
    initial_token_text = ""
    if "total_tokens" in initial_usage:
        initial_token_text = f", tokens={initial_usage['total_tokens']['mean']:.0f}"
    lines.append(
        f"Initial eval pass_rate={initial['pass_rate']:.1%} "
        f"[{initial['pass_rate_ci_95'][0]:.1%}, "
        f"{initial['pass_rate_ci_95'][1]:.1%}]"
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
        direct_ok = True
        try:
            direct_summary = await run_direct_llm_benchmark(
                eval_cases_subset=eval_cases_subset,
                system_prompt=DIRECT_LLM_PROMPT,
            )
        except Exception as exc:
            direct_ok = False
            direct_summary = _error_summary(
                system="direct_llm",
                eval_cases_subset=eval_cases_subset,
                error=exc,
            )
            emit_progress(
                f"[repeat {repeat_idx}/{repeats}] direct_llm: failed ({exc})",
                system="direct_llm",
                repeat=repeat_idx,
                error=str(exc),
            )
        system_runs["direct_llm"].append(direct_summary)
        completed_steps += 1
        direct_status = "done" if direct_ok else "error recorded"
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] direct_llm: {direct_status}",
            system="direct_llm",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] weak_static_agent: start")
        weak_ok = True
        try:
            weak_summary = await run_tool_agent_benchmark(
                system_name="weak_static_agent",
                prompt_text=WEAK_TOOL_PROMPT,
                eval_cases_subset=eval_cases_subset,
            )
        except Exception as exc:
            weak_ok = False
            weak_summary = _error_summary(
                system="weak_static_agent",
                eval_cases_subset=eval_cases_subset,
                error=exc,
            )
            emit_progress(
                f"[repeat {repeat_idx}/{repeats}] weak_static_agent: failed ({exc})",
                system="weak_static_agent",
                repeat=repeat_idx,
                error=str(exc),
            )
        system_runs["weak_static_agent"].append(weak_summary)
        completed_steps += 1
        weak_status = "done" if weak_ok else "error recorded"
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] weak_static_agent: {weak_status}",
            system="weak_static_agent",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] adaptive_agent: start")
        adaptive_ok = True
        try:
            adaptive_summary, trajectory = await run_adaptive_agent_benchmark(
                weak_prompt=WEAK_TOOL_PROMPT,
                adaptation_cycles=adaptation_cycles,
                consistency_repeats=consistency_repeats,
                eval_cases_subset=eval_cases_subset,
                train_cases_subset=train_cases_subset,
            )
        except Exception as exc:
            adaptive_ok = False
            adaptive_summary = _error_summary(
                system="adaptive_agent",
                eval_cases_subset=eval_cases_subset,
                error=exc,
            )
            trajectory = {"initial": {}, "cycles": [], "error": str(exc)}
            emit_progress(
                f"[repeat {repeat_idx}/{repeats}] adaptive_agent: failed ({exc})",
                system="adaptive_agent",
                repeat=repeat_idx,
                error=str(exc),
            )
        system_runs["adaptive_agent"].append(adaptive_summary)
        adaptive_trajectories.append(trajectory)
        completed_steps += 1
        adaptive_status = "done" if adaptive_ok else "error recorded"
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] adaptive_agent: {adaptive_status}",
            system="adaptive_agent",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] seed_tool_agent: start")
        seed_ok = True
        try:
            seed_summary = await run_tool_agent_benchmark(
                system_name="seed_tool_agent",
                prompt_text=SYSTEM_PROMPT_V1,
                eval_cases_subset=eval_cases_subset,
            )
        except Exception as exc:
            seed_ok = False
            seed_summary = _error_summary(
                system="seed_tool_agent",
                eval_cases_subset=eval_cases_subset,
                error=exc,
            )
            emit_progress(
                f"[repeat {repeat_idx}/{repeats}] seed_tool_agent: failed ({exc})",
                system="seed_tool_agent",
                repeat=repeat_idx,
                error=str(exc),
            )
        system_runs["seed_tool_agent"].append(seed_summary)
        completed_steps += 1
        seed_status = "done" if seed_ok else "error recorded"
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] seed_tool_agent: {seed_status}",
            system="seed_tool_agent",
            repeat=repeat_idx,
        )
        emit_progress(f"[repeat {repeat_idx}/{repeats}] sdk_tool_agent: start")
        sdk_ok = True
        try:
            sdk_summary = await run_sdk_tool_baseline(
                prompt_text=SYSTEM_PROMPT_V1,
                eval_cases_subset=eval_cases_subset,
            )
        except Exception as exc:
            sdk_ok = False
            sdk_summary = _error_summary(
                system="sdk_tool_agent",
                eval_cases_subset=eval_cases_subset,
                error=exc,
            )
            emit_progress(
                f"[repeat {repeat_idx}/{repeats}] sdk_tool_agent: failed ({exc})",
                system="sdk_tool_agent",
                repeat=repeat_idx,
                error=str(exc),
            )
        system_runs["sdk_tool_agent"].append(sdk_summary)
        completed_steps += 1
        sdk_status = "done" if sdk_ok else "error recorded"
        emit_progress(
            f"[repeat {repeat_idx}/{repeats}] sdk_tool_agent: {sdk_status}",
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
    }
    return report


def build_parser():
    from app.benchmarks.compare_cli import build_parser as _build_parser

    return _build_parser()


def main() -> int:
    from app.benchmarks.compare_cli import main as _main

    return _main()


if __name__ == "__main__":
    raise SystemExit(main())
