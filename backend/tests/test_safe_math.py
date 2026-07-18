import pytest

from app.safe_math import SafeMathError, safe_calculate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2 + 3 * 4", "14"),
        ("-(8 - 3) / 2", "-2.5"),
        ("7 // 2 + 7 % 2", "4"),
        ("2 ** 10", "1024"),
    ],
)
def test_safe_calculate_supports_bounded_arithmetic(
    expression: str,
    expected: str,
) -> None:
    assert safe_calculate(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo unsafe')",
        "abs(-1)",
        "pi + 1",
        "(1).__class__",
        "[1, 2][0]",
    ],
)
def test_safe_calculate_rejects_code_execution_surfaces(expression: str) -> None:
    with pytest.raises(SafeMathError, match="not allowed"):
        safe_calculate(expression)


def test_safe_calculate_rejects_exponents_outside_the_bound() -> None:
    with pytest.raises(SafeMathError, match="exponent"):
        safe_calculate("2 ** 11")


def test_safe_calculate_rejects_overlong_input() -> None:
    with pytest.raises(SafeMathError, match="too long"):
        safe_calculate("1+" * 65 + "1")


def test_safe_calculate_rejects_oversized_intermediate_results() -> None:
    with pytest.raises(SafeMathError, match="magnitude"):
        safe_calculate("1000000000000 * 1000000000000")


@pytest.mark.parametrize("expression", ["1 / 0", "1 // 0", "1 % 0"])
def test_safe_calculate_reports_division_by_zero(expression: str) -> None:
    with pytest.raises(SafeMathError, match="division by zero"):
        safe_calculate(expression)


def test_safe_calculate_rejects_non_numeric_literals() -> None:
    with pytest.raises(SafeMathError, match="numeric"):
        safe_calculate("True")
