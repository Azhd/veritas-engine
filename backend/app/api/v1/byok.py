"""BYOK discovery route: lets clients know which providers/headers the server accepts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_app_settings, get_provider_factory
from app.core.config import Settings
from app.engines.factory import ProviderFactory

router = APIRouter(prefix="/byok", tags=["byok"])


class ProviderInfo(BaseModel):
    name: str
    default_model: str
    requires_api_key: bool
    accepts_custom_endpoint: bool
    server_key_available: bool


class ByokInfo(BaseModel):
    headers: list[str]
    default_provider: str | None
    custom_endpoints_enabled: bool
    providers: list[ProviderInfo]


@router.get("/providers", response_model=ByokInfo, summary="Provedores BYOK suportados")
async def list_providers(
    factory: Annotated[ProviderFactory, Depends(get_provider_factory)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> ByokInfo:
    providers = []
    for name in factory.available_providers:
        cls = factory.provider_class(name)
        env_key = settings.env_api_key(name)
        providers.append(
            ProviderInfo(
                name=name.value,
                default_model=settings.default_model(name),
                requires_api_key=cls.requires_api_key,
                accepts_custom_endpoint=cls.supports_custom_endpoint,
                server_key_available=bool(
                    settings.allow_env_fallback and env_key and env_key.get_secret_value()
                ),
            )
        )
    return ByokInfo(
        headers=["X-Provider", "X-API-Key", "X-Endpoint-URL", "X-Model"],
        default_provider=settings.default_provider.value if settings.default_provider else None,
        custom_endpoints_enabled=settings.allow_custom_endpoints,
        providers=providers,
    )
