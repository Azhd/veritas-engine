"""FastAPI dependencies: per-request BYOK provider and shared services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.config import Settings
from app.engines.base import BaseLLMProvider
from app.engines.factory import ProviderFactory
from app.services.fact_checker import FactCheckService


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_provider_factory(request: Request) -> ProviderFactory:
    return request.app.state.provider_factory


def get_fact_check_service(request: Request) -> FactCheckService:
    return request.app.state.fact_check_service


async def get_llm_provider(
    factory: Annotated[ProviderFactory, Depends(get_provider_factory)],
    x_provider: Annotated[
        str | None, Header(description="gemini | anthropic | openai | groq | ollama")
    ] = None,
    x_api_key: Annotated[str | None, Header(description="Chave do provedor (BYOK).")] = None,
    x_endpoint_url: Annotated[
        str | None, Header(description="Endpoint customizado (Ollama / OpenAI-compatible).")
    ] = None,
    x_model: Annotated[str | None, Header(description="Sobrescreve o modelo padrão.")] = None,
) -> AsyncIterator[BaseLLMProvider]:
    """Create a provider scoped to this request and dispose of it (and the key) afterwards."""
    provider = factory.create(
        provider=x_provider, api_key=x_api_key, endpoint_url=x_endpoint_url, model=x_model
    )
    try:
        yield provider
    finally:
        await provider.aclose()
