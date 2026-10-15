"""FastAPI dependencies: per-request BYOK provider and shared services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError
from app.engines.base import BaseLLMProvider
from app.engines.factory import ProviderFactory
from app.services.fact_checker import FactCheckService
from app.services.media_checker import MediaCheckService

# The BYOK headers are declared as security schemes so Swagger UI shows a single "Authorize"
# dialog: users fill them once and every "Try it out" request carries them.
provider_header = APIKeyHeader(
    name="X-Provider",
    scheme_name="1. X-Provider",
    description="Provedor de IA: `gemini`, `anthropic`, `openai`, `groq` ou `ollama`.",
    auto_error=False,
)
api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="2. X-API-Key",
    description="Sua chave do provedor (dispensável para `ollama`). Usada só nesta requisição.",
    auto_error=False,
)
endpoint_header = APIKeyHeader(
    name="X-Endpoint-URL",
    scheme_name="3. X-Endpoint-URL (opcional)",
    description="Servidor próprio: Ollama (padrão `http://localhost:11434`) ou OpenAI-compatible.",
    auto_error=False,
)
model_header = APIKeyHeader(
    name="X-Model",
    scheme_name="4. X-Model (opcional)",
    description="Sobrescreve o modelo padrão do provedor (ex.: `llama3.1`, `gpt-4o`).",
    auto_error=False,
)


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_provider_factory(request: Request) -> ProviderFactory:
    return request.app.state.provider_factory


def get_fact_check_service(request: Request) -> FactCheckService:
    return request.app.state.fact_check_service


def get_media_check_service(request: Request) -> MediaCheckService:
    return request.app.state.media_check_service


@dataclass
class ProviderSelection:
    """The request's BYOK provider, or ``None`` (citizen mode) with the reason in ``notes``."""

    provider: BaseLLMProvider | None
    notes: list[str] = field(default_factory=list)


async def get_optional_llm_provider(
    factory: Annotated[ProviderFactory, Depends(get_provider_factory)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_provider: Annotated[str | None, Security(provider_header)] = None,
    x_api_key: Annotated[str | None, Security(api_key_header)] = None,
    x_endpoint_url: Annotated[str | None, Security(endpoint_header)] = None,
    x_model: Annotated[str | None, Security(model_header)] = None,
) -> AsyncIterator[ProviderSelection]:
    """Create a provider scoped to this request and dispose of it (and the key) afterwards.

    Zero-cost principle: a missing or invalid AI configuration never blocks the citizen; the
    request continues in raw-official-data mode and the reason is reported in the notes.
    """
    nothing_sent = not any(v and v.strip() for v in (x_provider, x_api_key, x_endpoint_url))
    if nothing_sent and settings.default_provider is None:
        yield ProviderSelection(None, ["Nenhuma chave de IA informada: modo cidadão ativado."])
        return
    try:
        provider = factory.create(
            provider=x_provider, api_key=x_api_key, endpoint_url=x_endpoint_url, model=x_model
        )
    except ProviderConfigurationError as exc:
        yield ProviderSelection(None, [f"Configuração de IA não utilizada: {exc.message}"])
        return
    try:
        yield ProviderSelection(provider)
    finally:
        await provider.aclose()
