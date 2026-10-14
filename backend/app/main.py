"""Veritas Engine - FastAPI application entrypoint.

Run locally:  ``uvicorn app.main:app --reload`` (from the ``backend/`` folder).
Swagger UI:   http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.v1 import byok, connectors, fact_check
from app.connectors.registry import build_connectors, warm_up
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.engines.factory import ProviderFactory
from app.services.fact_checker import FactCheckService

API_DESCRIPTION = """
Verificação de fatos em **fontes primárias**: governos do Brasil e da França, leis e
jurisprudência (Senado, STJ, EUR-Lex), ciência e saúde (PubMed, OMS), geopolítica (GDELT, ONU)
e memória da web (Internet Archive). **Gratuito e sem cadastro.**

### Como testar em 3 passos
1. **Sem chave nenhuma:** abra `POST /api/v1/fact-check/text`, escolha um exemplo e clique em
   *Execute*. Você recebe as fontes oficiais encontradas (modo cidadão).
2. **Veredito explicado por IA, de graça:** crie uma chave **gratuita e sem cartão** do
   [Google Gemini](https://aistudio.google.com/apikey) ou do [Groq](https://console.groq.com/keys),
   clique em **Authorize** 🔒 e preencha `X-Provider` (`gemini` ou `groq`) e `X-API-Key`.
   Com Ollama no seu computador basta `X-Provider = ollama`.
3. **Repita a checagem:** agora a resposta traz veredito, confiança e explicação com citações.

A chave vale só para a requisição e não é armazenada. Se ela falhar ou a cota gratuita acabar,
a checagem continua com os dados oficiais brutos, sem erro.
"""

OPENAPI_TAGS = [
    {
        "name": "fact-check",
        "description": "Checagem de alegações. **Funciona sem chave**; com IA traz veredito.",
    },
    {
        "name": "connectors",
        "description": "Fontes primárias consultadas. **Não precisa de chave.**",
    },
    {
        "name": "byok",
        "description": "Provedores de IA aceitos: gratuitos (Gemini, Groq, Ollama) primeiro.",
    },
    {"name": "health", "description": "Estado do serviço."},
]

# Pinned instead of FastAPI's floating ``swagger-ui-dist@5``: releases from 5.18 on ship a partial
# dark mode with unreadable text on dark-themed systems, and pinning keeps the docs reproducible.
SWAGGER_UI_VERSION = "5.17.14"
SWAGGER_UI_CDN = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}"

# Swagger UI only ships a light theme and leaves the page background transparent, so dark-mode
# browsers paint a dark canvas under dark text. Declare the light scheme and an opaque background.
SWAGGER_LIGHT_THEME = (
    '<meta name="color-scheme" content="light">'
    "<style>html, body { background: #fafafa; color-scheme: light; }</style>"
)

SWAGGER_UI_PARAMETERS = {
    "tryItOutEnabled": True,  # forms are editable right away, no extra "Try it out" click
    "defaultModelsExpandDepth": -1,  # hide the long "Schemas" section
    "docExpansion": "list",
    "displayRequestDuration": True,
    # Keys are kept only in the tab's memory: they are not saved to localStorage on purpose.
    "persistAuthorization": False,
}


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
        warm_task = asyncio.create_task(warm_up(connectors)) if settings.connector_warm_up else None
        try:
            yield
        finally:
            if warm_task is not None and not warm_task.done():
                warm_task.cancel()
            await http_client.aclose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        docs_url=None,  # served below with a pinned Swagger UI
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Provider", "X-API-Key", "X-Endpoint-URL", "X-Model"],
    )
    register_exception_handlers(app)

    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        page = get_swagger_ui_html(
            openapi_url=app.openapi_url or "/openapi.json",
            title=f"{settings.app_name} - Swagger UI",
            swagger_js_url=f"{SWAGGER_UI_CDN}/swagger-ui-bundle.js",
            swagger_css_url=f"{SWAGGER_UI_CDN}/swagger-ui.css",
            swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
        )
        html = page.body.decode().replace("</head>", f"{SWAGGER_LIGHT_THEME}</head>", 1)
        return HTMLResponse(html)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/healthz", tags=["health"], summary="Health check")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name, "version": settings.app_version}

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(fact_check.router)
    api_v1.include_router(connectors.router)
    api_v1.include_router(byok.router)
    app.include_router(api_v1)
    return app


app = create_app()
