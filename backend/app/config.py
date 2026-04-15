from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./adaptive_agent.db"
    anthropic_api_key: str = ""
    default_model: str = "claude-sonnet-4-6"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3737"]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
