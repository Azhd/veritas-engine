"""Fact-checking routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile

from app.api.deps import (
    ProviderSelection,
    get_fact_check_service,
    get_media_check_service,
    get_optional_llm_provider,
)
from app.schemas.fact_check import (
    CountryContext,
    FactCheckReport,
    MediaFactCheckReport,
    ReplyLanguage,
    TextFactCheckRequest,
)
from app.services.fact_checker import FactCheckService
from app.services.media_checker import MediaCheckService

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
    "saude_vacina": {
        "summary": "Saúde · Vacinas e autismo (PubMed/OMS)",
        "value": {"claim": "Vacinas causam autismo em crianças."},
    },
    "juridico_lei": {
        "summary": "Jurídico · Marco Civil (Senado/STJ)",
        "value": {"claim": "A Lei 12.965/2014 obriga provedores a guardar registros por 5 anos."},
    },
    "geopolitica": {
        "summary": "Geopolítica · Cessar-fogo (GDELT)",
        "value": {"claim": "A Ucrânia e a Rússia assinaram um cessar-fogo este mês."},
    },
    "web_arquivo": {
        "summary": "Memória da web · Página alterada (Wayback)",
        "value": {"claim": "A notícia em http://g1.globo.com foi apagada depois de publicada."},
    },
    "fr_chomage": {
        "summary": "FR · Desemprego (data.gouv.fr/INSEE)",
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
        "**Funciona sem chave de IA** (modo cidadão): devolve as fontes oficiais encontradas com "
        "o status `SEM_CHAVE_IA_DADOS_BRUTOS`. Para um veredito explicado, clique em "
        "**Authorize** e informe uma chave gratuita do Gemini ou do Groq (ou `ollama`). "
        "Se a chave falhar ou a cota gratuita acabar, a resposta volta ao modo cidadão em vez "
        "de dar erro. Escolha um exemplo pronto abaixo."
    ),
    responses={200: {"content": {"application/json": {"example": RESPONSE_EXAMPLE}}}},
)
async def fact_check_text(
    body: Annotated[TextFactCheckRequest, Body(openapi_examples=REQUEST_EXAMPLES)],
    selection: Annotated[ProviderSelection, Depends(get_optional_llm_provider)],
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
) -> FactCheckReport:
    return await service.check_text(
        body.claim,
        selection.provider,
        country_override=body.country,
        notes=selection.notes,
        source_url=body.source_url,
        language=body.language,
    )


@router.post(
    "/media",
    response_model=MediaFactCheckReport,
    summary="Verifica vídeo, áudio ou imagem (arquivo ou link): perícia + afirmações com minutagem",
    description=(
        "Envie **um arquivo** (até 50 MB) **ou um link** (YouTube, TikTok, X, Instagram ou link "
        "direto de mídia). O Veritas calcula a impressão digital (SHA-256), lê os metadados "
        "(EXIF), verifica credenciais de conteúdo (C2PA: gerada por IA? câmera?), extrai "
        "quadros-chave, transcreve a fala com minutagem e checa as afirmações nas fontes "
        "oficiais. Com uma chave gratuita do Groq ou do Gemini, a transcrição usa a mesma chave."
    ),
)
async def fact_check_media(
    selection: Annotated[ProviderSelection, Depends(get_optional_llm_provider)],
    service: Annotated[MediaCheckService, Depends(get_media_check_service)],
    file: Annotated[UploadFile | None, File(description="Vídeo, áudio ou imagem.")] = None,
    url: Annotated[str | None, Form(description="Ou o link da mídia.")] = None,
    claim: Annotated[
        str | None, Form(max_length=5000, description="Texto que acompanha a mídia (opcional).")
    ] = None,
    country: Annotated[CountryContext | None, Form()] = None,
    language: Annotated[
        ReplyLanguage | None, Form(description="Idioma das explicações (pt, en, fr).")
    ] = None,
) -> MediaFactCheckReport:
    return await service.check(
        selection.provider,
        upload=file,
        url=(url or "").strip() or None,
        claim=claim,
        country=country,
        notes=selection.notes,
        language=language,
    )
