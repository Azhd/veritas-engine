"""BYOK discovery route: lets clients know which providers/headers the server accepts."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import (
    ProviderSelection,
    get_app_settings,
    get_optional_llm_provider,
    get_provider_factory,
)
from app.core.config import Settings
from app.core.errors import VeritasError
from app.engines.factory import ProviderFactory

router = APIRouter(prefix="/byok", tags=["byok"])


class FreeTierInfo(BaseModel):
    free_tier: bool
    requires_credit_card: bool
    get_key_url: str | None
    steps: list[str]


#: Zero-cost first: how a citizen gets started with each provider without paying.
FREE_TIER: dict[str, FreeTierInfo] = {
    "gemini": FreeTierInfo(
        free_tier=True,
        requires_credit_card=False,
        get_key_url="https://aistudio.google.com/apikey",
        steps=[
            "Entre com qualquer conta Google em https://aistudio.google.com/apikey",
            "Clique em 'Create API key' e copie a chave",
            "No Veritas: X-Provider = gemini e X-API-Key = a chave copiada",
        ],
    ),
    "groq": FreeTierInfo(
        free_tier=True,
        requires_credit_card=False,
        get_key_url="https://console.groq.com/keys",
        steps=[
            "Crie uma conta gratuita em https://console.groq.com",
            "Em 'API Keys', clique em 'Create API Key' e copie a chave",
            "No Veritas: X-Provider = groq e X-API-Key = a chave copiada",
        ],
    ),
    "ollama": FreeTierInfo(
        free_tier=True,
        requires_credit_card=False,
        get_key_url=None,
        steps=[
            "Instale o Ollama (https://ollama.com) e rode: ollama pull llama3.1",
            "No Veritas: X-Provider = ollama (sem chave; roda no seu computador)",
        ],
    ),
    "anthropic": FreeTierInfo(
        free_tier=False,
        requires_credit_card=True,
        get_key_url="https://console.anthropic.com/settings/keys",
        steps=[],
    ),
    "openai": FreeTierInfo(
        free_tier=False,
        requires_credit_card=True,
        get_key_url="https://platform.openai.com/api-keys",
        steps=[],
    ),
}


class ProviderInfo(BaseModel):
    name: str
    default_model: str
    requires_api_key: bool
    accepts_custom_endpoint: bool
    server_key_available: bool
    free_tier: bool
    requires_credit_card: bool
    get_key_url: str | None
    steps: list[str]


class ByokInfo(BaseModel):
    headers: list[str]
    default_provider: str | None
    custom_endpoints_enabled: bool
    citizen_mode: str
    providers: list[ProviderInfo]


@router.get(
    "/providers",
    response_model=ByokInfo,
    summary="Provedores de IA aceitos (gratuitos primeiro)",
    description="Gemini, Groq e Ollama funcionam sem custo e sem cartão de crédito.",
)
async def list_providers(
    factory: Annotated[ProviderFactory, Depends(get_provider_factory)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ByokInfo:
    providers = []
    for name in factory.available_providers:
        cls = factory.provider_class(name)
        env_key = settings.env_api_key(name)
        free = FREE_TIER.get(
            name.value,
            FreeTierInfo(free_tier=False, requires_credit_card=True, get_key_url=None, steps=[]),
        )
        providers.append(
            ProviderInfo(
                name=name.value,
                default_model=settings.default_model(name),
                requires_api_key=cls.requires_api_key,
                accepts_custom_endpoint=cls.supports_custom_endpoint,
                server_key_available=bool(
                    settings.allow_env_fallback and env_key and env_key.get_secret_value()
                ),
                **free.model_dump(),
            )
        )
    providers.sort(key=lambda p: not p.free_tier)  # stable: Gemini, Groq, Ollama first
    return ByokInfo(
        headers=["X-Provider", "X-API-Key", "X-Endpoint-URL", "X-Model"],
        default_provider=settings.default_provider.value if settings.default_provider else None,
        custom_endpoints_enabled=settings.allow_custom_endpoints,
        citizen_mode=(
            "Sem nenhuma chave, POST /api/v1/fact-check/text devolve as fontes oficiais brutas "
            "(verdict SEM_CHAVE_IA_DADOS_BRUTOS)."
        ),
        providers=providers,
    )


class ConnectionTest(BaseModel):
    ok: bool
    provider: str | None = None
    model: str | None = None
    message: str


@router.post(
    "/test",
    response_model=ConnectionTest,
    summary="Testa a chave de IA informada (chamada mínima ao provedor)",
    description="Use antes de verificar: confirma que a chave e o modelo funcionam.",
)
async def test_connection(
    selection: Annotated[ProviderSelection, Depends(get_optional_llm_provider)],
) -> ConnectionTest:
    provider = selection.provider
    if provider is None:
        reason = selection.notes[0] if selection.notes else "Nenhuma IA configurada."
        return ConnectionTest(ok=False, message=reason)
    try:
        await asyncio.wait_for(
            provider.generate_text("Responda apenas: OK", temperature=0.0), timeout=25
        )
    except VeritasError as exc:
        return ConnectionTest(
            ok=False, provider=provider.name.value, model=provider.model, message=exc.message
        )
    except TimeoutError:
        return ConnectionTest(
            ok=False,
            provider=provider.name.value,
            model=provider.model,
            message="O provedor demorou demais para responder.",
        )
    return ConnectionTest(
        ok=True,
        provider=provider.name.value,
        model=provider.model,
        message="Conectado com sucesso.",
    )
