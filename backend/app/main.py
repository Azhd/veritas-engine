"""Veritas Engine - FastAPI application entrypoint.

Run locally:  ``uvicorn app.main:app --reload`` (from the ``backend/`` folder).
Swagger UI:   http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import byok, fact_check
from app.connectors.registry import build_connectors
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.engines.factory import ProviderFactory
from app.services.fact_checker import FactCheckService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        connectors, http_client = build_connectors(settings)
        app.state.settings = settings
        app.state.connectors = connectors
        app.state.provider_factory = ProviderFactory(settings)
        app.state.fact_check_service = FactCheckService(
            connectors, max_results_per_connector=settings.connector_max_results
        )
        try:
            yield
        finally:
            await http_client.aclose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Fact-checking multimodal descentralizado (BYOK) com cruzamento de dados em fontes "
            "oficiais do Brasil e da França. Envie suas credenciais via headers "
            "`X-Provider`, `X-API-Key`, `X-Endpoint-URL` e `X-Model`."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Provider", "X-API-Key", "X-Endpoint-URL", "X-Model"],
    )
    register_exception_handlers(app)

    @app.get("/healthz", tags=["health"], summary="Health check")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": settings.app_version}

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(fact_check.router)
    api_v1.include_router(byok.router)
    app.include_router(api_v1)
    return app


app = create_app()
