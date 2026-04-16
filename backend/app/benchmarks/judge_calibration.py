"""Human-labeled calibration harness for the pass/fail and hallucination judges."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

from app.benchmarks.compare_suite import JudgeCalibrationCase
from app.benchmarks.judge_calibration_cases import JUDGE_CALIBRATION_SET
from app.eval.checks import check_hallucination, check_pass_fail

CALIBRATION_CASES: list[JudgeCalibrationCase] = list(JUDGE_CALIBRATION_SET)


@dataclass(frozen=True)
class BinaryJudgeMetrics:
    accuracy: float
    precision: float
    recall: float
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    support: int


@dataclass(frozen=True)
class CalibrationCaseResult:
    name: str
    tags: tuple[str, ...]
    expected_pass: bool
    predicted_pass: bool
    expected_hallucination: bool
    predicted_hallucination: bool
    pass_reason: str
    hallucination_details: str
    pass_correct: bool
    hallucination_correct: bool


def calibration_cases() -> list[JudgeCalibrationCase]:
    return list(CALIBRATION_CASES)


def _normalize_tool_results(
    tool_results: Sequence[tuple[str, str]] | Sequence[dict[str, str]] | None,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for tool_result in tool_results or []:
        if isinstance(tool_result, dict):
            normalized.append(
                {
                    "name": str(tool_result.get("name", "")),
                    "output": str(tool_result.get("output", "")),
                }
            )
            continue

        name, output = tool_result
        normalized.append({"name": str(name), "output": str(output)})
    return normalized


def _compute_binary_metrics(
    rows: Sequence[CalibrationCaseResult],
    *,
    truth_key: str,
    pred_key: str,
) -> BinaryJudgeMetrics:
    truth_values = [bool(getattr(row, truth_key)) for row in rows]
    pred_values = [bool(getattr(row, pred_key)) for row in rows]

    true_positive = sum(1 for truth, pred in zip(truth_values, pred_values) if truth and pred)
    true_negative = sum(
        1 for truth, pred in zip(truth_values, pred_values) if (not truth) and (not pred)
    )
    false_positive = sum(
        1 for truth, pred in zip(truth_values, pred_values) if (not truth) and pred
    )
    false_negative = sum(
        1 for truth, pred in zip(truth_values, pred_values) if truth and (not pred)
    )
    support = len(rows)
    precision = (
        true_positive / (true_positive + false_positive)
        if true_positive + false_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    accuracy = (true_positive + true_negative) / support if support else 0.0

    return BinaryJudgeMetrics(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        true_positive=true_positive,
        true_negative=true_negative,
        false_positive=false_positive,
        false_negative=false_negative,
        support=support,
    )


async def run_judge_calibration(
    cases: Sequence[JudgeCalibrationCase] | None = None,
    *,
    pass_fail_judge=check_pass_fail,
    hallucination_judge=check_hallucination,
) -> dict:
    """Run the current judges against a static human-labeled calibration set."""
    chosen_cases = list(CALIBRATION_CASES if cases is None else cases)
    results: list[CalibrationCaseResult] = []

    for case in chosen_cases:
        pass_result = await pass_fail_judge(
            case.input_text,
            case.expected_output,
            case.actual_output,
        )
        hallucination_result = await hallucination_judge(
            case.input_text,
            case.actual_output,
            tool_results=_normalize_tool_results(case.tool_results),
            case_tags=list(case.tags),
            deterministic_result=pass_result,
        )

        predicted_pass = bool(pass_result.get("pass", False))
        predicted_hallucination = bool(hallucination_result.get("has_hallucination", False))
        results.append(
            CalibrationCaseResult(
                name=case.name,
                tags=case.tags,
                expected_pass=case.expected_pass,
                predicted_pass=predicted_pass,
                expected_hallucination=case.expected_hallucination,
                predicted_hallucination=predicted_hallucination,
                pass_reason=str(pass_result.get("reason", "")),
                hallucination_details=str(hallucination_result.get("details", "")),
                pass_correct=predicted_pass == case.expected_pass,
                hallucination_correct=predicted_hallucination == case.expected_hallucination,
            )
        )

    pass_metrics = _compute_binary_metrics(
        results,
        truth_key="expected_pass",
        pred_key="predicted_pass",
    )
    hallucination_metrics = _compute_binary_metrics(
        results,
        truth_key="expected_hallucination",
        pred_key="predicted_hallucination",
    )

    return {
        "case_count": len(results),
        "pass_fail": asdict(pass_metrics),
        "hallucination": asdict(hallucination_metrics),
        "case_accuracy": sum(
            1 for result in results if result.pass_correct and result.hallucination_correct
        )
        / len(results)
        if results
        else 0.0,
        "cases": [asdict(result) for result in results],
    }


def main() -> None:
    """Print the calibration report as JSON."""
    import asyncio
    import json

    report = asyncio.run(run_judge_calibration())
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
