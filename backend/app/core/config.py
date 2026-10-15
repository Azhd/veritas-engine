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
        # Blank values in .env (e.g. "VERITAS_DEFAULT_PROVIDER=") mean "use the default".
        env_ignore_empty=True,
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

    gemini_model: str = "gemini-flash-latest"  # Google alias: always the current free-tier Flash
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
    #: Bulk open-data files (e.g. STJ precedents CSV, ~2.5 MB) get a longer timeout and cache.
    dataset_timeout_seconds: float = Field(default=30.0, gt=0)
    dataset_cache_ttl_seconds: float = Field(default=86_400.0, ge=0)
    #: Preload bulk datasets (STJ precedents, INSEE catalog) in the background at startup.
    connector_warm_up: bool = True

    # ---------------- Media forensics (Phase 3) ----------------
    media_tmp_dir: str | None = None  # default: system temp dir / veritas-media
    media_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1)  # 50 MB
    media_max_duration_seconds: int = Field(default=900, ge=10)  # 15 min of audio/video
    media_keyframes: int = Field(default=6, ge=1, le=30)
    whisper_local_model: str = "base"  # faster-whisper model when installed

    # ---------------- Optional credentials for primary sources ----------------
    # Connectors whose credential is missing stay registered but are skipped (reported as
    # disabled), so the pipeline never fails because of them.
    ncbi_api_key: SecretStr | None = None  # optional: raises PubMed limit from 3 to 10 req/s
    ncbi_email: str | None = None  # NCBI asks API users to identify themselves
    reliefweb_appname: str | None = None  # must be approved by ReliefWeb (API v2)
    transparencia_api_key: SecretStr | None = None  # Portal da Transparência (CGU), free
    piste_client_id: SecretStr | None = None  # PISTE OAuth: Légifrance + Judilibre
    piste_client_secret: SecretStr | None = None
    piste_sandbox: bool = False

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
