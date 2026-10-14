"""Global application settings loaded from environment variables (prefix ``VERITAS_``)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderName(StrEnum):
    """LLM providers supported by the BYOK engine."""

    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GROQ = "groq"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERITAS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Veritas Engine"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # ---------------- BYOK ----------------
    default_provider: ProviderName | None = None
    allow_env_fallback: bool = True
    allow_custom_endpoints: bool = True

    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"

    gemini_model: str = "gemini-2.5-flash"
    anthropic_model: str = "claude-sonnet-5-5"
    openai_model: str = "gpt-4o"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_model: str = "llama3.1"
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 4096

    # ---------------- Government connectors ----------------
    connector_timeout_seconds: float = 8.0
    connector_max_retries: int = Field(default=3, ge=0, le=10)
    connector_backoff_base_seconds: float = Field(default=0.5, ge=0)
    connector_backoff_max_seconds: float = Field(default=8.0, ge=0)
    connector_cache_ttl_seconds: float = Field(default=900.0, ge=0)
    connector_cache_max_entries: int = Field(default=1024, ge=1)
    connector_max_results: int = Field(default=5, ge=1, le=50)

    def env_api_key(self, provider: ProviderName) -> SecretStr | None:
        return {
            ProviderName.GEMINI: self.gemini_api_key,
            ProviderName.ANTHROPIC: self.anthropic_api_key,
            ProviderName.OPENAI: self.openai_api_key,
            ProviderName.GROQ: self.groq_api_key,
            ProviderName.OLLAMA: None,
        }[provider]

    def default_model(self, provider: ProviderName) -> str:
        return {
            ProviderName.GEMINI: self.gemini_model,
            ProviderName.ANTHROPIC: self.anthropic_model,
            ProviderName.OPENAI: self.openai_model,
            ProviderName.GROQ: self.groq_model,
            ProviderName.OLLAMA: self.ollama_model,
        }[provider]


@lru_cache
def get_settings() -> Settings:
    return Settings()
