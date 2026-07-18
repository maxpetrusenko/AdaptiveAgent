import sys
from types import ModuleType

from langchain_core.messages import HumanMessage

import app.llm as llm_module
from app.llm import (
    _normalize_openai_compat_base_url,
    _ollama_tags_url,
    estimate_usage_from_messages,
)


def test_build_chat_model_attaches_observability_callbacks(monkeypatch):
    captured: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    monkeypatch.setattr(llm_module, "get_provider", lambda: "openai")
    monkeypatch.setattr(
        llm_module,
        "langchain_callbacks",
        lambda _settings: ["trace-handler"],
        raising=False,
    )

    llm_module.build_chat_model(purpose="agent")

    assert captured["callbacks"] == ["trace-handler"]


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
