from app.agent.tools import calculator


def test_calculator_uses_bounded_arithmetic() -> None:
    assert calculator.invoke({"expression": "(21 * 2) + 0.5"}) == "42.5"


def test_calculator_rejects_code_execution() -> None:
    result = calculator.invoke({"expression": "__import__('os').getcwd()"})

    assert result.startswith("Error: unsafe expression")
