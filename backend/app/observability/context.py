"""Small W3C-compatible trace context value objects."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, replace

_TRACEPARENT_PATTERN = re.compile(
    r"^00-(?P<trace_id>[0-9a-f]{32})-(?P<span_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    prompt_version: str | None = None
    model: str | None = None
    index_version: str | None = None
    sampled: bool = True


def new_trace_context(
    *,
    task_id: str | None = None,
    run_id: str | None = None,
    prompt_version: str | None = None,
    model: str | None = None,
    index_version: str | None = None,
) -> TraceContext:
    return TraceContext(
        trace_id=_nonzero_hex(16),
        span_id=_nonzero_hex(8),
        task_id=task_id,
        run_id=run_id,
        prompt_version=prompt_version,
        model=model,
        index_version=index_version,
    )


def child_context(context: TraceContext) -> TraceContext:
    return replace(
        context,
        span_id=_nonzero_hex(8),
        parent_span_id=context.span_id,
    )


def to_traceparent(context: TraceContext) -> str:
    flags = "01" if context.sampled else "00"
    return f"00-{context.trace_id}-{context.span_id}-{flags}"


def parse_traceparent(
    value: str,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
) -> TraceContext:
    match = _TRACEPARENT_PATTERN.fullmatch(value.strip().lower())
    if match is None:
        raise ValueError("Invalid W3C traceparent")
    trace_id = match.group("trace_id")
    parent_span_id = match.group("span_id")
    if int(trace_id, 16) == 0 or int(parent_span_id, 16) == 0:
        raise ValueError("Trace and span IDs must be non-zero")
    return TraceContext(
        trace_id=trace_id,
        span_id=_nonzero_hex(8),
        parent_span_id=parent_span_id,
        task_id=task_id,
        run_id=run_id,
        sampled=bool(int(match.group("flags"), 16) & 1),
    )


def correlation_fields(context: TraceContext) -> dict[str, str]:
    fields = {
        "trace_id": context.trace_id,
        "span_id": context.span_id,
        "parent_span_id": context.parent_span_id,
        "task_id": context.task_id,
        "run_id": context.run_id,
        "prompt_version": context.prompt_version,
        "model": context.model,
        "index_version": context.index_version,
    }
    return {key: value for key, value in fields.items() if value is not None}


def _nonzero_hex(byte_count: int) -> str:
    value = secrets.token_hex(byte_count)
    while int(value, 16) == 0:
        value = secrets.token_hex(byte_count)
    return value
