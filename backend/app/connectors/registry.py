"""Builds the set of government connectors sharing one HTTP client and cache."""

from __future__ import annotations

import httpx

from app.connectors.base import BaseGovConnector, TTLCache, build_http_client
from app.connectors.br.camara_connector import CamaraConnector
from app.connectors.br.ibge_connector import IbgeConnector
from app.connectors.fr.data_gouv_connector import DataGouvConnector
from app.core.config import Settings

CONNECTOR_CLASSES: tuple[type[BaseGovConnector], ...] = (
    CamaraConnector,
    IbgeConnector,
    DataGouvConnector,
)


def build_connectors(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> tuple[list[BaseGovConnector], httpx.AsyncClient]:
    """Return connectors plus the shared client (caller owns and must close it)."""
    client = client or build_http_client(
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    cache = TTLCache(
        ttl_seconds=settings.connector_cache_ttl_seconds,
        max_entries=settings.connector_cache_max_entries,
    )
    connectors = [
        cls(
            client,
            timeout_seconds=settings.connector_timeout_seconds,
            max_retries=settings.connector_max_retries,
            backoff_base_seconds=settings.connector_backoff_base_seconds,
            backoff_max_seconds=settings.connector_backoff_max_seconds,
            cache=cache,
        )
        for cls in CONNECTOR_CLASSES
    ]
    return connectors, client
