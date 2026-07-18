from langchain_core.tools import tool

from app.safe_math import SafeMathError, safe_calculate


@tool
def calculator(expression: str) -> str:
    """Evaluate bounded arithmetic without executing Python code."""
    try:
        return safe_calculate(expression)
    except SafeMathError as error:
        return f"Error: unsafe expression: {error}"


@tool
def current_time() -> str:
    """Get the current date and time."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
