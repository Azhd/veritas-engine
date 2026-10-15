"""Builds every primary-source connector sharing one HTTP client and one TTL cache."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.connectors.base import BaseGovConnector, TTLCache, build_http_client
from app.connectors.br_gov import (
    CamaraConnector,
    IbgeConnector,
    SenadoConnector,
    TransparenciaConnector,
)
from app.connectors.climate_environment import CopernicusClimateConnector, NoaaClimateConnector
from app.connectors.fr_gov import DataGouvConnector, InseeConnector, LegifranceConnector
from app.connectors.global_geopolitics import GdeltConnector, ReliefWebConnector
from app.connectors.legal_justice import (
    BrLegislationConnector,
    CourDeCassationConnector,
    EurLexConnector,
    StjPrecedentsConnector,
)
from app.connectors.piste import PisteAuth
from app.connectors.public_knowledge import WikidataConnector
from app.connectors.science_health import PubMedConnector, WhoGhoConnector
from app.connectors.web_archive import WaybackConnector
from app.core.config import Settings

logger = logging.getLogger(__name__)

#: Order = listing order. Keyless (zero-cost) sources first; credentialed ones are optional.
CONNECTOR_CLASSES: tuple[type[BaseGovConnector], ...] = (
    # Brazil
    CamaraConnector,
    SenadoConnector,
    IbgeConnector,
    BrLegislationConnector,
    StjPrecedentsConnector,
    TransparenciaConnector,
    # France / EU
    DataGouvConnector,
    InseeConnector,
    EurLexConnector,
    LegifranceConnector,
    CourDeCassationConnector,
    # Global
    PubMedConnector,
    WhoGhoConnector,
    GdeltConnector,
    ReliefWebConnector,
    CopernicusClimateConnector,
    NoaaClimateConnector,
    WaybackConnector,
    # Public knowledge bases (not official; listed last)
    WikidataConnector,
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
    extras = {
        "piste_auth": PisteAuth(
            client,
            settings.piste_client_id,
            settings.piste_client_secret,
            sandbox=settings.piste_sandbox,
            timeout_seconds=settings.connector_timeout_seconds,
        )
    }
    common = {
        "timeout_seconds": settings.connector_timeout_seconds,
        "max_retries": settings.connector_max_retries,
        "backoff_base_seconds": settings.connector_backoff_base_seconds,
        "backoff_max_seconds": settings.connector_backoff_max_seconds,
        "cache": cache,
    }
    connectors = [
        cls.from_settings(settings, client, extras, **common) for cls in CONNECTOR_CLASSES
    ]
    for connector in connectors:
        if not connector.enabled:
            logger.info("connector %s disabled: %s", connector.source_id, connector.disabled_reason)
    return connectors, client


async def warm_up(connectors: list[BaseGovConnector]) -> None:
    """Preload bulk datasets in the background; failures are logged, never raised."""
    results = await asyncio.gather(
        *(c.warm_up() for c in connectors if c.enabled), return_exceptions=True
    )
    for result in results:
        if isinstance(result, Exception):
            logger.warning("connector warm-up failed: %s", result)
