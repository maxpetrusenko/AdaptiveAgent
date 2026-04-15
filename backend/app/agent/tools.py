from langchain_core.tools import tool


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression. Input should be a valid Python math expression."""
    try:
        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error: {e}"


@tool
def current_time() -> str:
    """Get the current date and time."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
