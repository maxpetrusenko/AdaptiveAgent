from app.observability.context import new_trace_context
from app.observability.metadata import REDACTED, build_trace_metadata


def test_trace_content_is_off_by_default() -> None:
    context = new_trace_context(task_id="task-1")

    metadata = build_trace_metadata(
        context=context,
        attributes={"operation": "retrieve"},
        content={"prompt": "private customer content"},
    )

    assert metadata["operation"] == "retrieve"
    assert "content" not in metadata
    assert "private customer content" not in repr(metadata)


def test_explicit_content_capture_recursively_redacts_secret_fields() -> None:
    context = new_trace_context()

    metadata = build_trace_metadata(
        context=context,
        content={
            "query": "safe text",
            "api_key": "sk-secret-value",
            "nested": {
                "authorization": "Bearer hidden-token",
                "password": "hunter2",
            },
        },
        capture_content=True,
    )

    assert metadata["content"] == {
        "query": "safe text",
        "api_key": REDACTED,
        "nested": {
            "authorization": REDACTED,
            "password": REDACTED,
        },
    }


def test_secret_shaped_strings_are_redacted_outside_secret_fields() -> None:
    context = new_trace_context()

    metadata = build_trace_metadata(
        context=context,
        attributes={
            "header": "Bearer very-secret-token",
            "provider_key": "sk-ant-api03-this-must-not-leak",
            "operation": "generate",
        },
    )

    assert metadata["header"] == REDACTED
    assert metadata["provider_key"] == REDACTED
    assert metadata["operation"] == "generate"


def test_metadata_always_contains_available_correlation_fields() -> None:
    context = new_trace_context(
        task_id="task-1",
        run_id="run-1",
        prompt_version="prompt-v2",
        model="claude-sonnet-4-6",
        index_version="index-7",
    )

    metadata = build_trace_metadata(context=context)

    assert metadata["trace_id"] == context.trace_id
    assert metadata["span_id"] == context.span_id
    assert metadata["task_id"] == "task-1"
    assert metadata["run_id"] == "run-1"
    assert metadata["prompt_version"] == "prompt-v2"
    assert metadata["model"] == "claude-sonnet-4-6"
    assert metadata["index_version"] == "index-7"
