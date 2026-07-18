"""Message and usage helpers for comparative benchmark runners."""

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.benchmarks.compare_suite import BenchmarkCase


def extract_usage(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        usage = payload.get("usage")
        if isinstance(usage, dict):
            return {
                key: value
                for key, value in usage.items()
                if isinstance(value, (int, float))
            }
        return None

    for attr_name in ("usage", "usage_metadata", "response_metadata"):
        value = getattr(payload, attr_name, None)
        if isinstance(value, dict):
            usage = value.get("token_usage") if attr_name == "response_metadata" else value
            if isinstance(usage, dict):
                return {
                    key: value
                    for key, value in usage.items()
                    if isinstance(value, (int, float))
                }
    return None


def merge_usage(current: dict[str, float], usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    for key, value in usage.items():
        if isinstance(value, (int, float)):
            current[key] = current.get(key, 0.0) + float(value)


def case_messages(case: BenchmarkCase) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in case.messages]


def langchain_messages(
    case: BenchmarkCase,
    *,
    system_prompt: str,
) -> list[SystemMessage | HumanMessage | AIMessage]:
    messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=system_prompt)
    ]
    for role, content in case.messages:
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages
