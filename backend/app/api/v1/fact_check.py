"""Fact-checking routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_fact_check_service, get_llm_provider
from app.engines.base import BaseLLMProvider
from app.schemas.fact_check import FactCheckReport, TextFactCheckRequest
from app.services.fact_checker import FactCheckService

router = APIRouter(prefix="/fact-check", tags=["fact-check"])


@router.post(
    "/text",
    response_model=FactCheckReport,
    summary="Verifica uma alegação textual contra fontes oficiais (BR/FR)",
    responses={
        400: {"description": "Configuração BYOK inválida ou ausente"},
        401: {"description": "Chave rejeitada pelo provedor"},
        429: {"description": "Limite de taxa do provedor"},
        502: {"description": "Falha ou resposta inválida do provedor de IA"},
    },
)
async def fact_check_text(
    body: TextFactCheckRequest,
    llm: Annotated[BaseLLMProvider, Depends(get_llm_provider)],
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
) -> FactCheckReport:
    return await service.check_text(body.claim, llm, country_override=body.country)
