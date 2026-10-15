"""ProviderFactory: builds a fresh BYOK provider for each request.

Resolution order for every field:
    1. HTTP headers sent by the client (``X-Provider``, ``X-API-Key``, ``X-Endpoint-URL``,
       ``X-Model``);
    2. server-side environment fallback (only if ``VERITAS_ALLOW_ENV_FALLBACK=true``).

A new provider instance (and SDK client) is created for each call and discarded afterwards,
so credentials never outlive the request that carried them.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

from pydantic import SecretStr

from app.core.config import ProviderName, Settings
from app.core.errors import ProviderConfigurationError
from app.engines.base import BaseLLMProvider, ProviderCredentials
from app.engines.providers.claude_provider import ClaudeProvider
from app.engines.providers.gemini_provider import GeminiProvider
from app.engines.providers.groq_provider import GroqProvider
from app.engines.providers.ollama_provider import OllamaProvider
from app.engines.providers.openai_provider import OpenAIProvider

#: Zero-cost first: free tiers (Gemini, Groq) and local models (Ollama) come before paid APIs.
DEFAULT_REGISTRY: Mapping[ProviderName, type[BaseLLMProvider]] = {
    ProviderName.GEMINI: GeminiProvider,
    ProviderName.GROQ: GroqProvider,
    ProviderName.OLLAMA: OllamaProvider,
    ProviderName.ANTHROPIC: ClaudeProvider,
    ProviderName.OPENAI: OpenAIProvider,
}

_PROVIDER_ALIASES = {"claude": ProviderName.ANTHROPIC, "google": ProviderName.GEMINI}
_MAX_HEADER_LEN = 2048


class ProviderFactory:
    def __init__(
        self,
        settings: Settings,
        registry: Mapping[ProviderName, type[BaseLLMProvider]] | None = None,
    ) -> None:
        self._settings = settings
        self._registry = dict(registry or DEFAULT_REGISTRY)

    @property
    def available_providers(self) -> list[ProviderName]:
        return list(self._registry)

    def provider_class(self, name: ProviderName) -> type[BaseLLMProvider]:
        return self._registry[name]

    def create(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        endpoint_url: str | None = None,
        model: str | None = None,
    ) -> BaseLLMProvider:
        name = self._resolve_provider(provider)
        provider_cls = self._registry[name]
        credentials = ProviderCredentials(
            provider=name,
            model=_clean(model) or self._settings.default_model(name),
            api_key=self._resolve_key(name, provider_cls, api_key),
            endpoint_url=self._resolve_endpoint(name, provider_cls, endpoint_url),
            timeout_seconds=self._settings.llm_timeout_seconds,
            max_output_tokens=self._settings.llm_max_output_tokens,
        )
        return provider_cls(credentials)

    def from_headers(self, headers: Mapping[str, str]) -> BaseLLMProvider:
        lowered = {k.lower(): v for k, v in headers.items()}
        return self.create(
            provider=lowered.get("x-provider"),
            api_key=lowered.get("x-api-key"),
            endpoint_url=lowered.get("x-endpoint-url"),
            model=lowered.get("x-model"),
        )

    # ------------------------------------------------------------------ resolution helpers
    def _resolve_provider(self, raw: str | None) -> ProviderName:
        value = _clean(raw)
        if not value:
            if self._settings.default_provider is None:
                raise ProviderConfigurationError(
                    "No LLM provider configured. Send the X-Provider header "
                    f"({', '.join(p.value for p in self._registry)})."
                )
            value = self._settings.default_provider.value
        value = value.lower()
        name = _PROVIDER_ALIASES.get(value)
        if name is None:
            try:
                name = ProviderName(value)
            except ValueError:
                name = None
        if name is None or name not in self._registry:
            raise ProviderConfigurationError(
                f"Unsupported provider {value[:40]!r}. "
                f"Use one of: {', '.join(p.value for p in self._registry)}."
            )
        return name

    def _resolve_key(
        self, name: ProviderName, provider_cls: type[BaseLLMProvider], raw: str | None
    ) -> SecretStr | None:
        key = _clean(raw)
        if key:
            if len(key) > _MAX_HEADER_LEN or any(c.isspace() for c in key):
                raise ProviderConfigurationError("Malformed X-API-Key header.")
            return SecretStr(key)
        if self._settings.allow_env_fallback:
            env_key = self._settings.env_api_key(name)
            if env_key and env_key.get_secret_value():
                return env_key
        if provider_cls.requires_api_key:
            raise ProviderConfigurationError(
                f"Provider {name.value!r} requires an API key. Send it in the X-API-Key header."
            )
        return None

    def _resolve_endpoint(
        self, name: ProviderName, provider_cls: type[BaseLLMProvider], raw: str | None
    ) -> str | None:
        endpoint = _clean(raw)
        if endpoint:
            if not provider_cls.supports_custom_endpoint:
                raise ProviderConfigurationError(
                    f"Provider {name.value!r} does not accept X-Endpoint-URL."
                )
            if not self._settings.allow_custom_endpoints:
                raise ProviderConfigurationError(
                    "Custom endpoints are disabled on this server (VERITAS_ALLOW_CUSTOM_ENDPOINTS)."
                )
            parsed = urlparse(endpoint)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ProviderConfigurationError("X-Endpoint-URL must be an absolute http(s) URL.")
            if parsed.username or parsed.password:
                raise ProviderConfigurationError("X-Endpoint-URL must not embed credentials.")
            return endpoint.rstrip("/")
        if name is ProviderName.OLLAMA:
            return self._settings.ollama_base_url.rstrip("/")
        return None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None
