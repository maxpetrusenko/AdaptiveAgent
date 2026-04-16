from langchain_core.messages import HumanMessage

from app.llm import (
    _normalize_openai_compat_base_url,
    _ollama_tags_url,
    estimate_usage_from_messages,
)


def test_normalize_openai_compat_base_url_accepts_full_chat_completions_url():
    assert (
        _normalize_openai_compat_base_url("https://example.com/v1/chat/completions")
        == "https://example.com/v1"
    )


def test_normalize_openai_compat_base_url_adds_v1_to_root():
    assert _normalize_openai_compat_base_url("https://example.com") == "https://example.com/v1"


def test_ollama_tags_url_uses_root_api_path():
    assert (
        _ollama_tags_url("https://example.com/v1/chat/completions")
        == "https://example.com/api/tags"
    )


def test_estimate_usage_from_messages_returns_nonzero_token_counts():
    usage = estimate_usage_from_messages(
        prompt_messages=[HumanMessage(content="What is 2 + 2?")],
        completion_messages=["4"],
    )

    assert usage["input_tokens"] > 0
    assert usage["output_tokens"] > 0
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
    assert usage["source"] == "estimated"
