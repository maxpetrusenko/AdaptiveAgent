from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./adaptive_agent.db"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    model_provider: str = "auto"
    default_model: str = "claude-sonnet-4-6"
    judge_model: str = "claude-haiku-4-5-20251001"
    openai_default_model: str = "gpt-5.4"
    openai_judge_model: str = "gpt-5.4-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4"
    ollama_judge_model: str = "gemma4"
    gemma4_api_key: str = ""
    llm_timeout_seconds: int = 60
    benchmark_case_timeout_seconds: int = 90
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3737",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3737",
    ]
    operator_api_token: str | None = None

settings = Settings()
