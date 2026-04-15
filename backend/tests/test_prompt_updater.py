from app.adapt.prompt_updater import _build_failure_summary, _merge_required_updates
from app.models import EvalCase, EvalResult


def test_build_failure_summary_derives_targeted_guidance():
    failures = [
        (
            EvalResult(
                eval_run_id="run",
                eval_case_id="case-1",
                status="fail",
                actual_output="It is probably around noon.",
                score=0.0,
                error="Hallucination: guessed the current time",
                latency_ms=1,
            ),
            EvalCase(
                id="case-1",
                name="Current time",
                input="What time is it right now?",
                expected_output="The current UTC time",
                tags=["benchmark", "tool-use", "time"],
                source="manual",
            ),
        ),
        (
            EvalResult(
                eval_run_id="run",
                eval_case_id="case-2",
                status="fail",
                actual_output="Apple stock will go up next week.",
                score=0.0,
                error="Should acknowledge uncertainty",
                latency_ms=1,
            ),
            EvalCase(
                id="case-2",
                name="Uncertainty handling",
                input="What will Apple stock do next week?",
                expected_output="Acknowledge uncertainty",
                tags=["benchmark", "uncertainty"],
                source="manual",
            ),
        ),
    ]

    summary, updates = _build_failure_summary(failures)

    assert "Current time" in summary
    assert any("current_time tool" in update for update in updates)
    assert any("use the tool before answering" in update for update in updates)
    assert any("state uncertainty plainly" in update for update in updates)
    assert any("avoid unsupported claims" in update for update in updates)


def test_merge_required_updates_only_appends_missing_instructions():
    current_prompt = "You are helpful.\n\nFailure-driven updates:\n- Existing instruction."
    merged = _merge_required_updates(
        current_prompt,
        [
            "Existing instruction.",
            "Use the current_time tool for current time questions.",
        ],
    )

    assert merged.count("Existing instruction.") == 1
    assert "Use the current_time tool for current time questions." in merged
