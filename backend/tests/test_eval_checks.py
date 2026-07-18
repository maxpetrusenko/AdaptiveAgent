import pytest

from app.eval.checks import (
    check_consistency,
    check_deterministic,
    check_grounded_by_tools,
    check_grounded_deterministically,
    check_hallucination,
    check_pass_fail,
)


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeJudge:
    def __init__(self, content: str | None = None, error: Exception | None = None):
        self.content = content
        self.error = error

    async def ainvoke(self, messages):
        if self.error is not None:
            raise self.error
        return FakeResponse(self.content or "")


def test_check_grounded_by_tools_accepts_calculator_backed_answer():
    result = check_grounded_by_tools(
        "387",
        [{"name": "calculator", "output": "387"}],
    )

    assert result is not None
    assert result["has_hallucination"] is False


def test_check_grounded_by_tools_accepts_current_time_backed_answer():
    result = check_grounded_by_tools(
        "It's currently 2026-04-15 21:43:58 UTC.",
        [{"name": "current_time", "output": "2026-04-15T21:43:58+00:00"}],
    )

    assert result is not None
    assert result["has_hallucination"] is False


def test_check_grounded_deterministically_accepts_numeric_math_match():
    result = check_grounded_deterministically(
        {"pass": True, "score": 1.0, "reason": "Numeric match: 1680.0"},
        ["math", "eval"],
    )

    assert result is not None
    assert result["has_hallucination"] is False


def test_check_deterministic_accepts_uncertainty_acknowledgment():
    result = check_deterministic(
        "Acknowledge uncertainty about future stock prices",
        "No one can know for sure whether the stock will rise tomorrow.",
    )

    assert result is not None
    assert result["pass"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"pass": "false", "score": 1.0, "reason": "string boolean"}',
        '{"pass": true, "score": 100, "reason": "unbounded"}',
        '{"pass": true, "score": -0.1, "reason": "negative"}',
        '{"pass": true, "score": 1.0, "reason": "unterminated"',
    ],
)
async def test_pass_fail_judge_schema_rejects_malformed_or_unsafe_values(
    monkeypatch,
    content,
):
    monkeypatch.setattr(
        "app.eval.checks._get_judge_model",
        lambda: FakeJudge(content),
    )

    result = await check_pass_fail("input", "expected", "actual")

    assert result["pass"] is False
    assert result["score"] == 0.0
    assert "parse" in result["reason"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "judge",
    [
        FakeJudge('{"has_hallucination": "false", "confidence": 1.0, "details": "bad"}'),
        FakeJudge('{"has_hallucination": false, "confidence": 2.0, "details": "bad"}'),
        FakeJudge('not json'),
        FakeJudge(error=RuntimeError("provider unavailable")),
    ],
)
async def test_hallucination_judge_errors_fail_closed(monkeypatch, judge):
    monkeypatch.setattr("app.eval.checks._get_judge_model", lambda: judge)

    result = await check_hallucination("input", "unsupported output")

    assert result["has_hallucination"] is True
    assert result["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "judge",
    [
        FakeJudge('{"consistent": "true", "variance": 0.0, "details": "bad"}'),
        FakeJudge('{"consistent": true, "variance": -0.1, "details": "bad"}'),
        FakeJudge('not json'),
        FakeJudge(error=RuntimeError("provider unavailable")),
    ],
)
async def test_consistency_judge_errors_fail_closed(monkeypatch, judge):
    monkeypatch.setattr("app.eval.checks._get_judge_model", lambda: judge)

    result = await check_consistency("input", ["one", "two"])

    assert result["consistent"] is False
    assert result["error"]


@pytest.mark.asyncio
async def test_judge_provider_construction_errors_fail_closed(monkeypatch):
    def unavailable_provider():
        raise RuntimeError("provider cannot initialize")

    monkeypatch.setattr(
        "app.eval.checks._get_judge_model",
        unavailable_provider,
    )

    pass_fail = await check_pass_fail("input", "expected", "actual")
    hallucination = await check_hallucination("input", "actual")
    consistency = await check_consistency("input", ["one", "two"])

    assert pass_fail["pass"] is False
    assert pass_fail["score"] == 0.0
    assert hallucination["has_hallucination"] is True
    assert hallucination["error"]
    assert consistency["consistent"] is False
    assert consistency["error"]
