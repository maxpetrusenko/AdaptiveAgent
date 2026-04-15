"""LLM factory with provider fallback (Ollama via OpenAI compat, OpenAI, Anthropic)."""

from __future__ import annotations

from collections.abc import Iterable

from app.config import settings


def _normalize_openai_compat_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def _ollama_tags_url(base_url: str) -> str:
    normalized = _normalize_openai_compat_base_url(base_url)
    root = normalized[: -len("/v1")] if normalized.endswith("/v1") else normalized
    return f"{root}/api/tags"


def get_provider() -> str:
    provider = settings.model_provider.lower()
    if provider in {"openai", "anthropic", "ollama"}:
        return provider

    # Auto-detect: prefer Ollama (free, local), then OpenAI, then Anthropic
    if _ollama_available():
        return "ollama"
    if settings.openai_api_key:
        return "openai"
    if settings.anthropic_api_key:
        return "anthropic"
    raise RuntimeError(
        "No LLM configured. Run Ollama locally, or set OPENAI_API_KEY or ANTHROPIC_API_KEY."
    )


def _ollama_available() -> bool:
    """Check if Ollama is reachable and has a model."""
    import httpx

    try:
        headers = {}
        if settings.gemma4_api_key:
            headers["Authorization"] = f"Bearer {settings.gemma4_api_key}"
        r = httpx.get(
            _ollama_tags_url(settings.ollama_base_url),
            headers=headers,
            timeout=5,
        )
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        return any(settings.ollama_model in m for m in models)
    except Exception:
        return False


def build_chat_model(*, purpose: str, streaming: bool = False):
    provider = get_provider()

    if provider == "ollama":
        from langchain_openai import ChatOpenAI

        # Use OpenAI-compatible endpoint — works with auth proxy bearer tokens
        model = settings.ollama_judge_model if purpose == "judge" else settings.ollama_model
        api_key = settings.gemma4_api_key or "ollama"
        base_url = _normalize_openai_compat_base_url(settings.ollama_base_url)
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            streaming=streaming,
            temperature=0,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = (
            settings.openai_judge_model if purpose == "judge" else settings.openai_default_model
        )
        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            streaming=streaming,
            temperature=0,
        )

    from langchain_anthropic import ChatAnthropic

    model = settings.judge_model if purpose == "judge" else settings.default_model
    return ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        max_tokens=200 if purpose == "judge" else 4096,
        streaming=streaming,
        temperature=0,
    )


def extract_usage_metadata(message) -> dict[str, int]:
    """Normalize provider usage metadata from a LangChain response/message."""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    response_metadata = getattr(message, "response_metadata", None)
    if not isinstance(response_metadata, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    raw_usage = response_metadata.get("usage") or response_metadata.get("token_usage") or {}
    if not isinstance(raw_usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    input_tokens = int(
        raw_usage.get("input_tokens")
        or raw_usage.get("prompt_tokens")
        or raw_usage.get("inputTokenCount")
        or 0
    )
    output_tokens = int(
        raw_usage.get("output_tokens")
        or raw_usage.get("completion_tokens")
        or raw_usage.get("outputTokenCount")
        or 0
    )
    total_tokens = int(raw_usage.get("total_tokens") or input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def sum_usage_metadata(usages: Iterable[dict[str, int]]) -> dict[str, int]:
    """Sum usage records across one interaction."""
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    for usage in usages:
        input_tokens += int(usage.get("input_tokens", 0))
        output_tokens += int(usage.get("output_tokens", 0))
        total_tokens += int(usage.get("total_tokens", 0))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
