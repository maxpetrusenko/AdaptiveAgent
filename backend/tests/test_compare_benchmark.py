from app.benchmarks.compare import (
    CaseResult,
    SystemSummary,
    _aggregate_system_runs,
    _pairwise_delta,
    _render_leaderboard,
)


def _summary(system: str, statuses: list[str]) -> SystemSummary:
    results = [
        CaseResult(
            case_name=f"case-{idx}",
            status=status,
            score=1.0 if status == "pass" else 0.0,
            error=None,
            actual_output="ok",
            latency_ms=10,
        )
        for idx, status in enumerate(statuses, start=1)
    ]
    passed = sum(1 for status in statuses if status == "pass")
    return SystemSummary(
        system=system,
        pass_rate=passed / len(statuses),
        passed=passed,
        failed=len(statuses) - passed,
        avg_latency_ms=10.0,
        hallucination_failures=0,
        tag_pass_rates={"eval": passed / len(statuses)},
        results=results,
        metadata={},
    )


def test_pairwise_delta_counts_wins_losses_and_ties():
    adaptive = _summary("adaptive_agent", ["pass", "pass", "fail"])
    baseline = _summary("baseline", ["fail", "pass", "fail"])

    delta = _pairwise_delta(adaptive, baseline)

    assert delta["wins"] == 1
    assert delta["losses"] == 0
    assert delta["ties"] == 2
    assert delta["pass_rate_delta"] > 0


def test_render_leaderboard_sorts_by_pass_rate_then_latency():
    slower = _summary("slower", ["pass", "pass"])
    slower.avg_latency_ms = 20
    faster = _summary("faster", ["pass", "pass"])
    faster.avg_latency_ms = 5

    text = _render_leaderboard(
        [
            _aggregate_system_runs("slower", [slower]),
            _aggregate_system_runs("faster", [faster]),
        ],
        {
            "faster": {
                "pass_rate_delta_mean": 0.0,
                "pass_rate_delta_std": 0.0,
                "wins": 0,
                "losses": 0,
                "ties": 2,
            }
        },
    )

    assert "1. faster" in text
