"""HTML benchmark report tests."""

# ruff: noqa: E501

import json
from pathlib import Path

from app.benchmarks.report_html import (
    _normalize_report,
    render_report,
    render_report_directory,
)


def test_render_compare_report_contains_graph_sections():
    html = render_report(
        "compare-smoke",
        {
            "leaderboard": [
                {
                    "system": "adaptive_agent",
                    "pass_rate_mean": 1.0,
                    "avg_latency_ms_mean": 1.0,
                    "hallucination_failures_mean": 0.0,
                },
                {
                    "system": "weak_static_agent",
                    "pass_rate_mean": 0.5,
                    "avg_latency_ms_mean": 1.0,
                    "hallucination_failures_mean": 0.0,
                },
            ],
            "pairwise": {
                "weak_static_agent": {
                    "pass_rate_delta_mean": 0.5,
                    "wins": 2,
                    "losses": 0,
                    "ties": 2,
                    "sign_test": {"p_value": 0.5},
                }
            },
            "trajectory": {
                "summary": {
                    "initial": {
                        "pass_rate": 0.5,
                        "pass_rate_ci_95": [0.0, 1.0],
                        "usage_totals": {},
                    },
                    "cycles": [
                        {
                            "cycle": 1,
                            "eval_pass_rate": {"mean": 1.0, "ci_95": [1.0, 1.0]},
                            "gain": {"eval_pass_rate_delta_from_start": {"mean": 0.5}},
                            "stability": {"eval_pass_rate_delta_from_previous": {"mean": 0.5}},
                            "alignment": {"hallucination_rate": {"mean": 0.0}},
                            "eval": {"usage_totals": {}},
                        }
                    ],
                }
            },
            "config": {"train_case_count": 3, "eval_case_count": 4},
            "judge_calibration": {
                "case_count": 56,
                "pass_fail": {"accuracy": 1.0, "precision": 1.0, "recall": 1.0, "support": 56},
                "hallucination": {"accuracy": 1.0, "precision": 1.0, "recall": 1.0, "support": 56},
            },
            "hardening": {
                "hardening_checks": {
                    "null_agent": {"observed_pass_rate": 0.0, "sound": True},
                    "judge_bias_agent": {"observed_pass_rate": 0.0, "sound": True},
                    "evaluator_isolation": {"agent_and_evaluator_share_process": True},
                }
            },
        },
    )

    assert "Leaderboard pass rate" in html
    assert "Adaptive trajectory" in html
    assert "judge calibration" in html.lower()


def test_render_compare_report_supports_legacy_harness_checks_alias():
    html = render_report(
        "compare-legacy",
        {
            "leaderboard": [{"system": "adaptive_agent", "pass_rate_mean": 1.0}],
            "systems": [{"system": "adaptive_agent", "pass_rate_mean": 1.0}],
            "pairwise": {},
            "trajectory": {"summary": {"initial": {"pass_rate": 1.0}, "cycles": []}},
            "config": {"train_case_count": 1, "eval_case_count": 1},
            "harness_checks": {
                "hardening_checks": {
                    "null_agent": {"observed_pass_rate": 0.0, "sound": True},
                    "judge_bias_agent": {"observed_pass_rate": 0.0, "sound": True},
                    "evaluator_isolation": {"agent_and_evaluator_share_process": True},
                }
            },
        },
    )

    assert "null_agent" in html
    assert "evaluator_isolation" in html


def test_render_report_directory_writes_html_and_index(tmp_path: Path):
    report_path = tmp_path / "run.json"
    report_path.write_text(
        json.dumps(
            {
                "baseline": {"mean_pass_rate": 0.5, "std_pass_rate": 0.0, "runs": []},
                "post_adaptation": {"mean_pass_rate": 1.0, "std_pass_rate": 0.0, "runs": []},
                "adaptation": {"accepted": True},
                "delta": {"mean_pass_rate_delta": 0.5},
                "baseline_prompt_version": 1,
                "final_prompt_version": 2,
            }
        ),
        encoding="utf-8",
    )

    outputs = render_report_directory(tmp_path)

    assert (tmp_path / "run.html") in outputs
    assert (tmp_path / "index.html") in outputs
    assert (tmp_path / "run.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "Benchmark Storyboard" in index_html
    assert "tab-button" in index_html


def test_normalize_report_for_compare_shape(tmp_path: Path):
    path = tmp_path / "compare.json"
    normalized = _normalize_report(
        path,
        {
            "systems": [{"system": "adaptive_agent", "pass_rate_mean": 1.0}],
            "pairwise": {"direct_llm": {"pass_rate_delta_mean": 0.5}},
            "trajectory": {"summary": {"initial": {"pass_rate": 0.5}, "cycles": [{"accepted_rate": 1.0}]}},
            "config": {"eval_case_count": 8},
        },
    )

    assert normalized["kind"] == "comparative"
    assert normalized["start"] == 0.5
    assert normalized["end"] == 1.0
    assert normalized["delta"] == 0.5
