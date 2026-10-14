"""Fact-checking routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.deps import get_fact_check_service, get_llm_provider
from app.engines.base import BaseLLMProvider
from app.schemas.fact_check import FactCheckReport, TextFactCheckRequest
from app.services.fact_checker import FactCheckService

router = APIRouter(prefix="/fact-check", tags=["fact-check"])

REQUEST_EXAMPLES = {
    "br_inflacao": {
        "summary": "BR · Inflação (IBGE)",
        "value": {"claim": "A inflação no Brasil passou de 10% nos últimos 12 meses."},
    },
    "br_desemprego": {
        "summary": "BR · Desemprego (IBGE)",
        "value": {"claim": "O desemprego no Brasil está abaixo de 6% em 2026."},
    },
    "br_legislativo": {
        "summary": "BR · Câmara dos Deputados",
        "value": {"claim": "A Câmara aprovou a reforma tributária que cria o IBS e a CBS."},
    },
    "fr_chomage": {
        "summary": "FR · Desemprego (data.gouv.fr)",
        "value": {"claim": "Le taux de chômage en France a doublé depuis 2020.", "country": "FR"},
    },
}

RESPONSE_EXAMPLE = {
    "claim": "A inflação no Brasil passou de 10% nos últimos 12 meses.",
    "verdict": "FALSO",
    "confidence_score": 0.9,
    "primary_sources": [
        {
            "evidence_id": "E1",
            "title": "IPCA - variação acumulada em 12 meses (%) - Brasil",
            "url": "https://sidra.ibge.gov.br/tabela/1737",
            "publisher": "IBGE - Instituto Brasileiro de Geografia e Estatística",
            "connector": "br.ibge",
            "country": "BR",
            "excerpt": "08/2026: 4.22; 09/2026: 4.58",
            "retrieved_at": "2026-10-14T20:30:00Z",
            "cited": True,
        }
    ],
    "explanation": "Segundo o IBGE [E1], o IPCA acumulado em 12 meses foi de 4,58% em 09/2026.",
    "country_context": "BR",
    "keywords": ["inflação", "IPCA"],
    "connectors_queried": ["br.camara", "br.ibge"],
    "connector_failures": [],
    "provider": "groq",
    "model": "llama-3.3-70b-versatile",
    "checked_at": "2026-10-14T20:30:02Z",
    "notes": [],
}


@router.post(
    "/text",
    response_model=FactCheckReport,
    summary="Verifica uma alegação textual contra fontes oficiais (BR/FR)",
    description=(
        "Antes de testar, clique em **Authorize** (cadeado) e informe `X-Provider` e `X-API-Key` "
        "(ou só `X-Provider: ollama` para modelos locais). Escolha um exemplo pronto abaixo."
    ),
    responses={
        200: {"content": {"application/json": {"example": RESPONSE_EXAMPLE}}},
        400: {"description": "Configuração BYOK inválida ou ausente (ex.: faltou X-Provider)"},
        401: {"description": "Chave rejeitada pelo provedor"},
        429: {"description": "Limite de taxa do provedor"},
        502: {"description": "Falha ou resposta inválida do provedor de IA"},
    },
)
async def fact_check_text(
    body: Annotated[TextFactCheckRequest, Body(openapi_examples=REQUEST_EXAMPLES)],
    llm: Annotated[BaseLLMProvider, Depends(get_llm_provider)],
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
) -> FactCheckReport:
    return await service.check_text(body.claim, llm, country_override=body.country)
