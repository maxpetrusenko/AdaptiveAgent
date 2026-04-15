"""LLM factory with provider fallback (Ollama via OpenAI compat, OpenAI, Anthropic)."""

from __future__ import annotations

from app.config import settings


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
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", headers=headers, timeout=5)
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
        base_url = f"{settings.ollama_base_url}/v1"
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
