"""Metrics helpers for the comparative benchmark."""

from __future__ import annotations

import random
from dataclasses import asdict
from math import comb
from statistics import mean, pstdev
from typing import Any, Sequence

from app.benchmarks.compare_types import CaseResult, SystemSummary


def bootstrap_ci(
    values: Sequence[float],
    *,
    samples: int = 2000,
    seed: int = 0,
) -> tuple[float, float]:
    points = list(values)
    if not points:
        return (0.0, 0.0)
    if len(points) == 1:
        return (points[0], points[0])

    rng = random.Random(seed)
    draws = [
        mean(rng.choice(points) for _ in range(len(points)))
        for _ in range(samples)
    ]
    draws.sort()
    lower = draws[max(0, int(0.025 * (samples - 1)))]
    upper = draws[min(samples - 1, int(0.975 * (samples - 1)))]
    return (lower, upper)


def series_stats(values: Sequence[float], *, bootstrap_samples: int) -> dict[str, Any]:
    points = list(values)
    if not points:
        return {"mean": 0.0, "std": 0.0, "ci_95": [0.0, 0.0]}
    return {
        "mean": mean(points),
        "std": pstdev(points) if len(points) > 1 else 0.0,
        "ci_95": list(bootstrap_ci(points, samples=bootstrap_samples)),
    }


def case_pass_values(results: Sequence[CaseResult]) -> list[float]:
    return [1.0 if result.status == "pass" else 0.0 for result in results]


def pairwise_delta(left: SystemSummary, right: SystemSummary) -> dict[str, Any]:
    left_results = {result.case_name: result.status for result in left.results}
    right_results = {result.case_name: result.status for result in right.results}
    wins = 0
    losses = 0
    ties = 0

    for case_name, left_status in left_results.items():
        right_status = right_results.get(case_name)
        left_pass = left_status == "pass"
        right_pass = right_status == "pass"
        if left_pass and not right_pass:
            wins += 1
        elif right_pass and not left_pass:
            losses += 1
        else:
            ties += 1

    return {
        "pass_rate_delta": left.pass_rate - right.pass_rate,
        "wins": wins,
        "losses": losses,
        "ties": ties,
    }


def aggregate_cycle_metric(
    snapshots: list[dict[str, Any]],
    path: tuple[str, ...],
    *,
    bootstrap_samples: int,
) -> dict[str, Any]:
    def extract(snapshot: dict[str, Any]) -> float:
        value: Any = snapshot
        for key in path:
            value = value[key]
        return float(value)

    values = [extract(snapshot) for snapshot in snapshots]
    stats = series_stats(values, bootstrap_samples=bootstrap_samples)
    return {
        "mean": stats["mean"],
        "std": stats["std"],
        "ci_95": stats["ci_95"],
        "values": values,
    }


def aggregate_trajectory_runs(
    runs: list[dict[str, Any]],
    *,
    bootstrap_samples: int,
) -> dict[str, Any]:
    valid_runs = [
        run
        for run in runs
        if run.get("initial", {}).get("eval", {}).get("pass_rate") is not None
    ]
    if not valid_runs:
        return {
            "initial": {},
            "cycles": [],
            "runs": runs,
            "errors": [run.get("error") for run in runs if run.get("error")],
        }

    initial_snapshots = [run["initial"] for run in valid_runs]
    initial_pass_rates = [float(snapshot["eval"]["pass_rate"]) for snapshot in initial_snapshots]
    initial_usage_keys = sorted(
        {
            key
            for snapshot in initial_snapshots
            for key in (snapshot["eval"].get("usage_totals") or {}).keys()
        }
    )
    initial_summary = {
        "pass_rate": mean(initial_pass_rates),
        "pass_rate_ci_95": list(bootstrap_ci(initial_pass_rates, samples=bootstrap_samples)),
        "avg_latency_ms": mean(
            float(snapshot["eval"]["avg_latency_ms"]) for snapshot in initial_snapshots
        ),
        "hallucination_failures": mean(
            float(snapshot["eval"]["hallucination_failures"]) for snapshot in initial_snapshots
        ),
        "usage_totals": {
            key: series_stats(
                [
                    float((snapshot["eval"].get("usage_totals") or {}).get(key, 0.0))
                    for snapshot in initial_snapshots
                ],
                bootstrap_samples=bootstrap_samples,
            )
            for key in initial_usage_keys
        },
    }

    cycle_count = max(len(run["cycles"]) for run in valid_runs)
    cycles: list[dict[str, Any]] = []
    for index in range(cycle_count):
        snapshots = [run["cycles"][index] for run in valid_runs if len(run["cycles"]) > index]
        cycle_usage_keys = sorted(
            {
                key
                for snapshot in snapshots
                for key in (snapshot["eval"].get("usage_totals") or {}).keys()
            }
        )
        cycles.append(
            {
                "cycle": index + 1,
                "prompt_version": [snapshot["prompt_version"] for snapshot in snapshots],
                "accepted_rate": mean(
                    1.0 if snapshot["accepted"] else 0.0 for snapshot in snapshots
                ),
                "eval_pass_rate": aggregate_cycle_metric(
                    snapshots,
                    ("eval", "pass_rate"),
                    bootstrap_samples=bootstrap_samples,
                ),
                "gain": {
                    "train_pass_rate_delta": aggregate_cycle_metric(
                        snapshots,
                        ("gain", "train_pass_rate_delta"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                    "eval_pass_rate_delta_from_start": aggregate_cycle_metric(
                        snapshots,
                        ("gain", "eval_pass_rate_delta_from_start"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                },
                "stability": {
                    "eval_pass_rate_delta_from_previous": aggregate_cycle_metric(
                        snapshots,
                        ("stability", "eval_pass_rate_delta_from_previous"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                    "stable_rate": mean(
                        1.0 if snapshot["stability"]["stable"] else 0.0 for snapshot in snapshots
                    ),
                    "protected_pass_rate": aggregate_cycle_metric(
                        snapshots,
                        ("alignment", "protected_pass_rate"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                },
                "alignment": {
                    "hallucination_failures": aggregate_cycle_metric(
                        snapshots,
                        ("alignment", "hallucination_failures"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                    "hallucination_rate": aggregate_cycle_metric(
                        snapshots,
                        ("alignment", "hallucination_rate"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                    "protected_pass_rate": aggregate_cycle_metric(
                        snapshots,
                        ("alignment", "protected_pass_rate"),
                        bootstrap_samples=bootstrap_samples,
                    ),
                },
                "eval": {
                    "usage_totals": {
                        key: series_stats(
                            [
                                float((snapshot["eval"].get("usage_totals") or {}).get(key, 0.0))
                                for snapshot in snapshots
                            ],
                            bootstrap_samples=bootstrap_samples,
                        )
                        for key in cycle_usage_keys
                    },
                },
            }
        )

    return {
        "initial": initial_summary,
        "cycles": cycles,
        "runs": runs,
        "errors": [run.get("error") for run in runs if run.get("error")],
    }


def aggregate_system_runs(
    system: str,
    runs: list[SystemSummary],
    *,
    bootstrap_samples: int = 2000,
) -> dict[str, Any]:
    pass_rates = [run.pass_rate for run in runs]
    latencies = [run.avg_latency_ms for run in runs]
    hallucinations = [run.hallucination_failures for run in runs]
    flattened_pass_values = [value for run in runs for value in case_pass_values(run.results)]
    usage_keys = sorted(
        {
            key
            for run in runs
            for key in (run.metadata.get("usage_totals") or {}).keys()
        }
    )

    tag_names = sorted({tag for run in runs for tag in run.tag_pass_rates})
    tag_stats = {
        tag: series_stats(
            [run.tag_pass_rates.get(tag, 0.0) for run in runs],
            bootstrap_samples=bootstrap_samples,
        )
        for tag in tag_names
    }
    usage_stats = {
        key: series_stats(
            [float((run.metadata.get("usage_totals") or {}).get(key, 0.0)) for run in runs],
            bootstrap_samples=bootstrap_samples,
        )
        for key in usage_keys
    }

    return {
        "system": system,
        "pass_rate_mean": mean(pass_rates),
        "pass_rate_std": pstdev(pass_rates) if len(runs) > 1 else 0.0,
        "pass_rate_ci_95": list(bootstrap_ci(flattened_pass_values, samples=bootstrap_samples)),
        "avg_latency_ms_mean": mean(latencies),
        "avg_latency_ms_std": pstdev(latencies) if len(runs) > 1 else 0.0,
        "hallucination_failures_mean": mean(hallucinations),
        "runs": [
            {
                **asdict(run),
                "results": [asdict(result) for result in run.results],
            }
            for run in runs
        ],
        "tag_pass_rates": tag_stats,
        "usage_totals": usage_stats,
    }


def aggregate_pairwise_runs(
    adaptive_runs: list[SystemSummary],
    baseline_runs: list[SystemSummary],
    *,
    bootstrap_samples: int,
) -> dict[str, Any]:
    deltas = [
        pairwise_delta(adaptive, baseline)
        for adaptive, baseline in zip(adaptive_runs, baseline_runs, strict=True)
    ]
    pass_rate_deltas = [delta["pass_rate_delta"] for delta in deltas]
    wins = sum(delta["wins"] for delta in deltas)
    losses = sum(delta["losses"] for delta in deltas)
    return {
        "pass_rate_delta_mean": mean(pass_rate_deltas),
        "pass_rate_delta_std": pstdev(pass_rate_deltas) if len(pass_rate_deltas) > 1 else 0.0,
        "pass_rate_delta_ci_95": list(bootstrap_ci(pass_rate_deltas, samples=bootstrap_samples)),
        "wins": wins,
        "losses": losses,
        "ties": sum(delta["ties"] for delta in deltas),
        "sign_test": sign_test(wins=wins, losses=losses),
    }


def sign_test(*, wins: int, losses: int) -> dict[str, Any]:
    trials = wins + losses
    if trials == 0:
        return {"wins": wins, "losses": losses, "p_value": 1.0, "significant_at_0_05": False}

    tail = sum(comb(trials, k) for k in range(0, min(wins, losses) + 1)) / (2**trials)
    p_value = min(1.0, 2 * tail)
    return {
        "wins": wins,
        "losses": losses,
        "p_value": p_value,
        "significant_at_0_05": p_value < 0.05,
    }


def render_leaderboard(summaries: list[dict[str, Any]], pairwise: dict[str, dict[str, Any]]) -> str:
    ordered = sorted(
        summaries,
        key=lambda item: (-item["pass_rate_mean"], item["avg_latency_ms_mean"]),
    )
    lines = ["Leaderboard:"]
    for idx, summary in enumerate(ordered, start=1):
        usage = summary.get("usage_totals", {})
        token_bits = []
        if "total_tokens" in usage:
            token_bits.append(f"tokens={usage['total_tokens']['mean']:.0f}")
        if "input_tokens" in usage:
            token_bits.append(f"input={usage['input_tokens']['mean']:.0f}")
        if "output_tokens" in usage:
            token_bits.append(f"output={usage['output_tokens']['mean']:.0f}")
        token_text = f", {'; '.join(token_bits)}" if token_bits else ""
        lines.append(
            f"{idx}. {summary['system']}: "
            f"pass_rate={summary['pass_rate_mean']:.1%} "
            f"[{summary['pass_rate_ci_95'][0]:.1%}, {summary['pass_rate_ci_95'][1]:.1%}], "
            f"avg_latency_ms={summary['avg_latency_ms_mean']:.0f}, "
            f"hallucinations={summary['hallucination_failures_mean']:.1f}"
            f"{token_text}"
        )
    lines.append("")
    lines.append("Adaptive deltas:")
    for name, delta in pairwise.items():
        lines.append(
            f"- adaptive_agent vs {name}: "
            f"delta={delta['pass_rate_delta_mean']:.1%} "
            f"[{delta['pass_rate_delta_ci_95'][0]:.1%}, {delta['pass_rate_delta_ci_95'][1]:.1%}], "
            f"wins={delta['wins']}, losses={delta['losses']}, ties={delta['ties']}"
        )
    return "\n".join(lines)
