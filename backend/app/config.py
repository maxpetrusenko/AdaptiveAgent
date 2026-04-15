from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3737"]

    class Config:
        env_file = ("../.env", ".env")
        extra = "ignore"


settings = Settings()
