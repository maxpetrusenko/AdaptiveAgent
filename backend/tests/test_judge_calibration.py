import pytest

from app.benchmarks.compare_suite import JudgeCalibrationCase
from app.benchmarks.judge_calibration import calibration_cases, run_judge_calibration


def test_calibration_cases_cover_twenty_static_labeled_examples():
    cases = calibration_cases()

    assert len(cases) >= 50
    assert any("math" in case.tags for case in cases)
    assert any(case.expected_pass for case in cases)
    assert any(not case.expected_pass for case in cases)
    assert any(case.expected_hallucination for case in cases)
    assert any(not case.expected_hallucination for case in cases)


async def test_run_judge_calibration_reports_metrics_and_wires_judges():
    calls: list[dict] = []

    async def fake_pass_judge(input_text: str, expected_output: str, actual_output: str):
        mapping = {
            "case-1": {"pass": True, "score": 1.0, "reason": "match"},
            "case-2": {"pass": True, "score": 1.0, "reason": "wrong pass"},
            "case-3": {"pass": False, "score": 0.0, "reason": "wrong fail"},
        }
        return mapping[input_text]

    async def fake_hallucination_judge(
        input_text: str,
        actual_output: str,
        *,
        tool_results=None,
        case_tags=None,
        deterministic_result=None,
    ):
        calls.append(
            {
                "input_text": input_text,
                "tool_results": tool_results,
                "case_tags": case_tags,
                "deterministic_result": deterministic_result,
            }
        )
        mapping = {
            "case-1": {"has_hallucination": False, "confidence": 1.0, "details": "ok"},
            "case-2": {"has_hallucination": False, "confidence": 1.0, "details": "wrong"},
            "case-3": {"has_hallucination": True, "confidence": 1.0, "details": "ok"},
        }
        return mapping[input_text]

    report = await run_judge_calibration(
        cases=[
            JudgeCalibrationCase(
                name="case-1",
                input_text="case-1",
                expected_output="expected-1",
                actual_output="actual-1",
                expected_pass=True,
                expected_hallucination=False,
                tags=("alpha",),
                tool_results=(("calculator", "9"),),
            ),
            JudgeCalibrationCase(
                name="case-2",
                input_text="case-2",
                expected_output="expected-2",
                actual_output="actual-2",
                expected_pass=False,
                expected_hallucination=True,
                tags=("beta",),
            ),
            JudgeCalibrationCase(
                name="case-3",
                input_text="case-3",
                expected_output="expected-3",
                actual_output="actual-3",
                expected_pass=True,
                expected_hallucination=True,
                tags=("gamma",),
            ),
        ],
        pass_fail_judge=fake_pass_judge,
        hallucination_judge=fake_hallucination_judge,
    )

    assert report["case_count"] == 3
    assert report["pass_fail"]["accuracy"] == pytest.approx(1 / 3)
    assert report["pass_fail"]["precision"] == pytest.approx(1 / 2)
    assert report["pass_fail"]["recall"] == pytest.approx(1 / 2)
    assert report["hallucination"]["accuracy"] == pytest.approx(2 / 3)
    assert report["hallucination"]["precision"] == pytest.approx(1.0)
    assert report["hallucination"]["recall"] == pytest.approx(1 / 2)
    assert report["case_accuracy"] == pytest.approx(1 / 3)

    assert calls[0]["tool_results"] == [{"name": "calculator", "output": "9"}]
    assert calls[0]["case_tags"] == ["alpha"]
    assert calls[0]["deterministic_result"]["pass"] is True
