from app.eval.checks import check_grounded_by_tools


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
