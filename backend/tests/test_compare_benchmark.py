from app.benchmarks.compare import (
    CaseResult,
    SystemSummary,
    _aggregate_pairwise,
    _aggregate_system_runs,
    _pairwise_delta,
    _render_leaderboard,
    run_compare_benchmark,
)


def _summary(system: str, statuses: list[str], *, tokens: int = 20) -> SystemSummary:
    results = [
        CaseResult(
            case_name=f"case-{idx}",
            status=status,
            score=1.0 if status == "pass" else 0.0,
            error=None,
            actual_output="ok",
            latency_ms=10,
            usage={"total_tokens": tokens},
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
        metadata={"usage_totals": {"total_tokens": float(tokens * len(statuses))}},
    )


def test_pairwise_delta_counts_wins_losses_and_ties():
    adaptive = _summary("adaptive_agent", ["pass", "pass", "fail"])
    baseline = _summary("baseline", ["fail", "pass", "fail"])

    delta = _pairwise_delta(adaptive, baseline)

    assert delta["wins"] == 1
    assert delta["losses"] == 0
    assert delta["ties"] == 2
    assert delta["pass_rate_delta"] > 0


def test_aggregate_system_runs_includes_bootstrap_ci_and_usage():
    summary = _aggregate_system_runs(
        "adaptive_agent",
        [
            _summary("adaptive_agent", ["pass", "fail"]),
            _summary("adaptive_agent", ["pass", "pass"]),
        ],
        bootstrap_samples=200,
    )

    assert summary["pass_rate_mean"] == 0.75
    assert (
        summary["pass_rate_ci_95"][0]
        <= summary["pass_rate_mean"]
        <= summary["pass_rate_ci_95"][1]
    )
    assert summary["usage_totals"]["total_tokens"]["mean"] > 0


def test_aggregate_pairwise_includes_ci_and_sign_test():
    adaptive_runs = [
        _summary("adaptive_agent", ["pass", "fail"]),
        _summary("adaptive_agent", ["pass", "pass"]),
    ]
    baseline_runs = [
        _summary("baseline", ["fail", "fail"]),
        _summary("baseline", ["pass", "fail"]),
    ]

    pairwise = _aggregate_pairwise(adaptive_runs, baseline_runs, bootstrap_samples=200)

    assert pairwise["wins"] == 2
    assert pairwise["losses"] == 0
    assert (
        pairwise["pass_rate_delta_ci_95"][0]
        <= pairwise["pass_rate_delta_mean"]
        <= pairwise["pass_rate_delta_ci_95"][1]
    )
    assert pairwise["sign_test"]["p_value"] <= 1.0


def test_render_leaderboard_sorts_by_pass_rate_then_latency():
    slower = _summary("slower", ["pass", "pass"])
    slower.avg_latency_ms = 20
    faster = _summary("faster", ["pass", "pass"])
    faster.avg_latency_ms = 5

    text = _render_leaderboard(
        [
            _aggregate_system_runs("slower", [slower], bootstrap_samples=200),
            _aggregate_system_runs("faster", [faster], bootstrap_samples=200),
        ],
        {
            "faster": {
                "pass_rate_delta_mean": 0.0,
                "pass_rate_delta_std": 0.0,
                "pass_rate_delta_ci_95": [0.0, 0.0],
                "wins": 0,
                "losses": 0,
                "ties": 2,
                "sign_test": {"p_value": 1.0, "significant_at_0_05": False},
            }
        },
    )

    assert "1. faster" in text


async def test_run_compare_benchmark_includes_sdk_hardening_and_calibration(monkeypatch):
    import app.benchmarks.compare as compare

    async def fake_direct_llm_benchmark(**kwargs):
        return _summary("direct_llm", ["fail", "pass"])

    async def fake_tool_agent_benchmark(*, system_name, **kwargs):
        mapping = {
            "weak_static_agent": _summary("weak_static_agent", ["fail", "fail"]),
            "seed_tool_agent": _summary("seed_tool_agent", ["pass", "pass"]),
        }
        return mapping[system_name]

    async def fake_sdk_tool_baseline(**kwargs):
        return _summary("sdk_tool_agent", ["pass", "fail"])

    async def fake_adaptive_agent_benchmark(**kwargs):
        return _summary("adaptive_agent", ["pass", "pass"]), {
            "initial": {
                "eval": {
                    "pass_rate": 0.5,
                    "avg_latency_ms": 10,
                    "hallucination_failures": 0,
                    "usage_totals": {},
                    "pass_rate_ci_95": [0.0, 1.0],
                    "tag_pass_rates": {},
                }
            },
            "cycles": [],
        }

    async def fake_adversarial_benchmark(**kwargs):
        return {
            "hardening_checks": {
                "null_agent": {"sound": True},
                "judge_bias_agent": {"sound": True},
            }
        }

    async def fake_judge_calibration():
        return {"case_count": 56}

    monkeypatch.setattr(compare, "train_cases", lambda *args, **kwargs: [])
    monkeypatch.setattr(compare, "eval_cases", lambda *args, **kwargs: [])
    monkeypatch.setattr(compare, "run_direct_llm_benchmark", fake_direct_llm_benchmark)
    monkeypatch.setattr(compare, "run_tool_agent_benchmark", fake_tool_agent_benchmark)
    monkeypatch.setattr(compare, "run_sdk_tool_baseline", fake_sdk_tool_baseline)
    monkeypatch.setattr(compare, "run_adaptive_agent_benchmark", fake_adaptive_agent_benchmark)
    monkeypatch.setattr(compare, "run_adversarial_benchmark", fake_adversarial_benchmark)
    monkeypatch.setattr(compare, "run_judge_calibration", fake_judge_calibration)

    report = await run_compare_benchmark(repeats=1)

    systems = {system["system"] for system in report["systems"]}
    assert "sdk_tool_agent" in systems
    assert report["hardening"]["hardening_checks"]["null_agent"]["sound"] is True
    assert "harness_checks" not in report
    assert report["judge_calibration"]["case_count"] == 56
    assert "evaluator_isolation" in report["hardening"]["hardening_checks"]


def test_compare_eval_suite_has_expanded_diverse_coverage():
    from app.benchmarks.compare_suite import eval_cases

    cases = eval_cases()
    tags = {tag for case in cases for tag in case.tags}

    assert len(cases) >= 42
    assert {"retrieval", "privacy", "prompt-injection"}.issubset(tags)
