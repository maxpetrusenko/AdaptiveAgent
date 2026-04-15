from app.llm import _normalize_openai_compat_base_url, _ollama_tags_url


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
