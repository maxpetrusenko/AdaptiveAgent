import json

import pytest


@pytest.mark.asyncio
async def test_adversarial_benchmark_report_has_null_and_judge_bias_checks(monkeypatch):
    from app.benchmarks import adversarial
    from app.benchmarks.compare_suite import BenchmarkCase

    cases = [
        BenchmarkCase(
            name="Case 1",
            input="What is the capital of Japan?",
            expected_output="Tokyo",
            tags=("factual", "eval"),
            split="eval",
            messages=(("user", "What is the capital of Japan?"),),
        ),
        BenchmarkCase(
            name="Case 2",
            input="What is 2 + 2?",
            expected_output="4",
            tags=("math", "eval"),
            split="eval",
            messages=(("user", "What is 2 + 2?"),),
        ),
    ]

    async def fake_check_pass_fail(input_text, expected_output, actual_output):
        if "pass=true" in actual_output or "override" in actual_output:
            return {"pass": True, "score": 1.0, "reason": "Injected pass"}
        return {"pass": False, "score": 0.0, "reason": "Mismatch"}

    async def fake_check_hallucination(*args, **kwargs):
        return {"has_hallucination": False, "confidence": 1.0, "details": "ok"}

    monkeypatch.setattr(adversarial.compare_suite, "eval_cases", lambda max_cases=None: cases)
    monkeypatch.setattr(adversarial, "check_deterministic", lambda *args, **kwargs: None)
    monkeypatch.setattr(adversarial, "check_pass_fail", fake_check_pass_fail)
    monkeypatch.setattr(adversarial, "check_hallucination", fake_check_hallucination)

    report = await adversarial.run_adversarial_benchmark()

    assert report["suite"]["case_count"] == 2
    assert report["hardening_checks"]["null_agent"]["observed_pass_rate"] == 0.0
    assert report["hardening_checks"]["null_agent"]["sound"] is True
    assert report["hardening_checks"]["judge_bias_agent"]["observed_pass_rate"] == 1.0
    assert report["hardening_checks"]["judge_bias_agent"]["judge_compromisable"] is True
    assert report["hardening_checks"]["comparison"]["bias_minus_null"] == 1.0
    assert report["systems"]["null_agent"]["system"] == "null_agent"
    assert report["systems"]["judge_bias_agent"]["metadata"]["probe"] == "prompt_injection"
    json.dumps(report)


@pytest.mark.asyncio
async def test_adversarial_benchmark_respects_max_cases(monkeypatch):
    from app.benchmarks import adversarial
    from app.benchmarks.compare_suite import BenchmarkCase

    cases = [
        BenchmarkCase(
            name="Case 1",
            input="One",
            expected_output="1",
            tags=("eval",),
            split="eval",
            messages=(("user", "One"),),
        ),
        BenchmarkCase(
            name="Case 2",
            input="Two",
            expected_output="2",
            tags=("eval",),
            split="eval",
            messages=(("user", "Two"),),
        ),
    ]

    monkeypatch.setattr(
        adversarial.compare_suite,
        "eval_cases",
        lambda max_cases=None: cases[:max_cases],
    )
    monkeypatch.setattr(adversarial, "check_deterministic", lambda *args, **kwargs: None)

    async def fake_check_pass_fail(*args, **kwargs):
        return {"pass": False, "score": 0.0, "reason": "Mismatch"}

    async def fake_check_hallucination(*args, **kwargs):
        return {"has_hallucination": False, "confidence": 0.0, "details": "ok"}

    monkeypatch.setattr(adversarial, "check_pass_fail", fake_check_pass_fail)
    monkeypatch.setattr(adversarial, "check_hallucination", fake_check_hallucination)

    report = await adversarial.run_adversarial_benchmark(max_cases=1)

    assert report["suite"]["case_count"] == 1
    assert len(report["suite"]["cases"]) == 1
