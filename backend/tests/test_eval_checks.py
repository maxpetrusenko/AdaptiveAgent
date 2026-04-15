from app.eval.checks import (
    check_deterministic,
    check_grounded_by_tools,
    check_grounded_deterministically,
)


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
