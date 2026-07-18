from app.observability.context import (
    child_context,
    correlation_fields,
    new_trace_context,
    parse_traceparent,
    to_traceparent,
)


def test_new_trace_context_provides_w3c_sized_identifiers() -> None:
    context = new_trace_context(task_id="task-1", run_id="run-1")

    assert len(context.trace_id) == 32
    assert len(context.span_id) == 16
    assert context.task_id == "task-1"
    assert context.run_id == "run-1"


def test_child_context_preserves_trace_and_correlation() -> None:
    parent = new_trace_context(
        task_id="task-1",
        run_id="run-1",
        prompt_version="prompt-v2",
        model="claude-sonnet-4-6",
        index_version="index-7",
    )

    child = child_context(parent)

    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id
    assert child.parent_span_id == parent.span_id
    assert correlation_fields(child) == {
        "trace_id": parent.trace_id,
        "span_id": child.span_id,
        "parent_span_id": parent.span_id,
        "task_id": "task-1",
        "run_id": "run-1",
        "prompt_version": "prompt-v2",
        "model": "claude-sonnet-4-6",
        "index_version": "index-7",
    }


def test_traceparent_round_trip_preserves_remote_parent() -> None:
    original = new_trace_context(task_id="task-1")

    parsed = parse_traceparent(to_traceparent(original), task_id="task-1")

    assert parsed.trace_id == original.trace_id
    assert parsed.parent_span_id == original.span_id
    assert parsed.span_id != original.span_id
    assert parsed.task_id == "task-1"
