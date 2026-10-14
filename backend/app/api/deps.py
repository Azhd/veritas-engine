"""FastAPI dependencies: per-request BYOK provider and shared services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings
from app.engines.base import BaseLLMProvider
from app.engines.factory import ProviderFactory
from app.services.fact_checker import FactCheckService

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


async def get_llm_provider(
    factory: Annotated[ProviderFactory, Depends(get_provider_factory)],
    x_provider: Annotated[str | None, Security(provider_header)] = None,
    x_api_key: Annotated[str | None, Security(api_key_header)] = None,
    x_endpoint_url: Annotated[str | None, Security(endpoint_header)] = None,
    x_model: Annotated[str | None, Security(model_header)] = None,
) -> AsyncIterator[BaseLLMProvider]:
    """Create a provider scoped to this request and dispose of it (and the key) afterwards."""
    provider = factory.create(
        provider=x_provider, api_key=x_api_key, endpoint_url=x_endpoint_url, model=x_model
    )
    try:
        yield provider
    finally:
        await provider.aclose()
