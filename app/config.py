from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    database_url: str = ""
    agent_tool_secret: str = ""
    session_signing_secret: str = ""
    demo_admin_pin: str = "0000"
    sarvam_api_key: str = ""
    plan_budget_s: float = 8.0  # planning time budget before the "shall I try again?" reply (R9)
    git_commit: str = "dev"
    render_git_commit: str = ""  # set automatically by Render

    @property
    def commit(self) -> str:
        return (self.render_git_commit or self.git_commit)[:7]

    @property
    def async_database_url(self) -> str:
        """Supabase URL if provided, otherwise a local SQLite file for dev/tests."""
        url = self.database_url.strip()
        if not url:
            return "sqlite+aiosqlite:///./raahi_dev.db"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
