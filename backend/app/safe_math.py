"""Bounded arithmetic evaluation without Python code execution."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable

MAX_EXPRESSION_LENGTH = 128
MAX_AST_NODES = 64
MAX_AST_DEPTH = 16
MAX_ABS_VALUE = 1_000_000_000_000
MAX_ABS_EXPONENT = 10


class SafeMathError(ValueError):
    """The expression is invalid, unsafe, or outside the arithmetic budget."""


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def safe_calculate(expression: str) -> str:
    """Evaluate a small arithmetic expression and return a display-safe result."""
    if not isinstance(expression, str) or not expression.strip():
        raise SafeMathError("Expression must be a non-empty string")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise SafeMathError("Expression is too long")

    try:
        parsed = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as error:
        raise SafeMathError("Expression syntax is invalid") from error

    nodes = list(ast.walk(parsed))
    if len(nodes) > MAX_AST_NODES:
        raise SafeMathError("Expression is too complex")
    if _tree_depth(parsed) > MAX_AST_DEPTH:
        raise SafeMathError("Expression is too deeply nested")

    result = _evaluate(parsed.body)
    if isinstance(result, float) and result.is_integer():
        return str(int(result))
    return str(result)


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise SafeMathError("Only numeric literals are allowed")
        return _bounded(node.value)

    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise SafeMathError(f"Expression element {type(node.op).__name__} is not allowed")
        return _bounded(operation(_evaluate(node.operand)))

    if isinstance(node, ast.BinOp):
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise SafeMathError(f"Expression element {type(node.op).__name__} is not allowed")
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_ABS_EXPONENT:
            raise SafeMathError("Absolute exponent exceeds the allowed bound")
        try:
            result = operation(left, right)
        except ZeroDivisionError as error:
            raise SafeMathError("Expression contains division by zero") from error
        except (OverflowError, ValueError) as error:
            raise SafeMathError("Expression result is outside the numeric bound") from error
        return _bounded(result)

    raise SafeMathError(f"Expression element {type(node).__name__} is not allowed")


def _bounded(value: int | float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeMathError("Expression did not produce a real numeric result")
    if not math.isfinite(value):
        raise SafeMathError("Expression result must be finite")
    if abs(value) > MAX_ABS_VALUE:
        raise SafeMathError("Expression result magnitude exceeds the allowed bound")
    return value


def _tree_depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_tree_depth(child) for child in children)
