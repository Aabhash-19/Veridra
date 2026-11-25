from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_key_set(raw: str, placeholder: str) -> bool:
    key = raw.strip()
    return bool(key) and not key.startswith("replace_") and key != placeholder


class Settings(BaseSettings):
    """Application settings loaded from environment variables and local .env files."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Veridra"
    app_base_url: str = "http://localhost:5173"
    api_base_url: str = "http://localhost:8000"
    secret_key: str = "dev-local-change-me"
    log_level: str = "INFO"
    debug_log_content: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # LLM providers (Gemini, OpenAI/ChatGPT, Groq, OpenRouter, Anthropic)
    llm_provider: str = "gemini"
    gemini_api_key: str = Field(default="")
    gemini_model: str = "gemini-3.6-flash"

    openai_api_key: str = Field(default="")
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    groq_api_key: str = Field(default="")
    groq_model: str = "openai/gpt-oss-120b"

    openrouter_api_key: str = Field(default="")
    openrouter_model: str = "openai/gpt-4o-mini"

    anthropic_api_key: str = Field(default="")
    anthropic_model: str = "claude-3-5-haiku-latest"

    # Optional direct social publishing credentials
    linkedin_access_token: str = Field(default="")
    linkedin_person_urn: str = Field(default="")
    x_access_token: str = Field(default="")

    # Search
    search_provider: str = "tavily"
    tavily_api_key: str = Field(default="")

    # Persistence
    database_url: str = "sqlite:///./veridra.db"
    checkpoint_db_path: str = "./veridra_checkpoints.db"

    # Workflow / guardrails (Appendix A.1)
    max_editor_revisions: int = 3
    max_fact_remediations: int = 2
    max_research_retries: int = 1
    max_graph_steps: int = 24
    run_timeout_seconds: int = 600
    editor_approval_threshold: int = 75
    max_search_queries: int = 6
    max_sources: int = 12
    max_urls_per_request: int = 8
    max_input_characters: int = 12000

    # Observability
    langsmith_tracing: bool = False
    langsmith_api_key: str = Field(default="")
    langsmith_project: str = "veridra"

    # Demo mode
    demo_mode: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_gemini_configured(self) -> bool:
        return _is_key_set(self.gemini_api_key, "your_gemini_api_key")

    @property
    def is_openai_configured(self) -> bool:
        return _is_key_set(self.openai_api_key, "your_openai_api_key")

    @property
    def is_groq_configured(self) -> bool:
        return _is_key_set(self.groq_api_key, "your_groq_api_key")

    @property
    def is_openrouter_configured(self) -> bool:
        return _is_key_set(self.openrouter_api_key, "your_openrouter_api_key")

    @property
    def is_anthropic_configured(self) -> bool:
        return _is_key_set(self.anthropic_api_key, "your_anthropic_api_key")

    @property
    def provider_statuses(self) -> dict[str, bool]:
        return {
            "openai": self.is_openai_configured,
            "groq": self.is_groq_configured,
            "openrouter": self.is_openrouter_configured,
            "anthropic": self.is_anthropic_configured,
            "gemini": self.is_gemini_configured,
        }

    @property
    def configured_llm_providers(self) -> list[str]:
        return [name for name, ok in self.provider_statuses.items() if ok]

    @property
    def is_any_llm_configured(self) -> bool:
        return any(self.provider_statuses.values())

    @property
    def active_default_provider(self) -> str:
        preferred = self.llm_provider.strip().lower()
        statuses = self.provider_statuses
        if statuses.get(preferred):
            return preferred
        for cand in ("openai", "groq", "anthropic", "openrouter", "gemini"):
            if statuses.get(cand):
                return cand
        return preferred or "gemini"

    @property
    def resolved_gemini_model(self) -> str:
        from app.core.pricing import resolve_live_gemini_model

        return resolve_live_gemini_model(self.gemini_model)

    @property
    def active_default_model(self) -> str:
        from app.core.pricing import resolve_default_model_for_provider

        return resolve_default_model_for_provider(self.active_default_provider, self)

    @property
    def is_tavily_configured(self) -> bool:
        return _is_key_set(self.tavily_api_key, "your_tavily_api_key")

    @property
    def is_linkedin_connected(self) -> bool:
        return _is_key_set(self.linkedin_access_token, "your_linkedin_access_token") and bool(
            self.linkedin_person_urn.strip()
        )

    @property
    def is_x_connected(self) -> bool:
        return _is_key_set(self.x_access_token, "your_x_access_token")

    @property
    def social_connections(self) -> dict[str, bool]:
        return {
            "linkedin": self.is_linkedin_connected,
            "x": self.is_x_connected,
            "instagram": False,
        }

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def resolved_checkpoint_db(self) -> str:
        if self.checkpoint_db_path:
            return str(Path(self.checkpoint_db_path).resolve())
        return str(Path("./veridra_checkpoints.db").resolve())

    def secret_values(self) -> list[str]:
        """Return non-empty secrets for log redaction."""
        secrets = [
            self.gemini_api_key.strip(),
            self.openai_api_key.strip(),
            self.groq_api_key.strip(),
            self.openrouter_api_key.strip(),
            self.anthropic_api_key.strip(),
            self.tavily_api_key.strip(),
            self.langsmith_api_key.strip(),
            self.linkedin_access_token.strip(),
            self.x_access_token.strip(),
            self.secret_key.strip(),
        ]
        return [s for s in secrets if len(s) >= 8 and s != "dev-local-change-me"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
