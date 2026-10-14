"""Primary-source connector routes. They need no AI key: zero-cost access for every citizen."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_fact_check_service
from app.schemas.evidence import Country, Domain, Evidence
from app.schemas.fact_check import ClaimAnalysis, ConnectorFailure, CountryContext
from app.services.fact_checker import FactCheckService

router = APIRouter(prefix="/connectors", tags=["connectors"])


class ConnectorInfo(BaseModel):
    id: str
    country: Country
    publisher: str
    base_url: str
    domains: list[Domain]
    enabled: bool
    disabled_reason: str | None = None


class EvidenceSearchRequest(BaseModel):
    keywords: list[str] = Field(min_length=1, max_length=8, description="Termos de busca.")
    country: CountryContext = Field(
        default=CountryContext.AMBOS, description="Quais conectores consultar."
    )
    topics: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Temas estatísticos (IBGE): inflação, desemprego, população.",
    )
    people: list[str] = Field(
        default_factory=list, max_length=2, description="Deputados para buscar discursos."
    )
    domains: list[Domain] = Field(
        default_factory=list,
        description="Áreas a consultar; vazio = política/legislação e economia/estatística.",
    )
    keywords_en: list[str] = Field(
        default_factory=list, max_length=8, description="Termos em inglês (PubMed, OMS, GDELT)."
    )
    legal_references: list[str] = Field(
        default_factory=list, max_length=5, description="Ex.: 'Lei 12.965/2014'."
    )
    urls: list[str] = Field(
        default_factory=list, max_length=3, description="URLs para auditar no Internet Archive."
    )


class EvidenceSearchResponse(BaseModel):
    connectors_queried: list[str]
    evidence: list[Evidence]
    connector_failures: list[ConnectorFailure]


SEARCH_EXAMPLES = {
    "br_inflacao": {
        "summary": "BR · Inflação e desemprego (IBGE)",
        "value": {"keywords": ["inflação"], "country": "BR", "topics": ["inflação", "desemprego"]},
    },
    "br_legislativo": {
        "summary": "BR · Proposições na Câmara",
        "value": {"keywords": ["reforma tributária"], "country": "BR"},
    },
    "saude": {
        "summary": "Saúde · Vacinas e autismo (PubMed + OMS)",
        "value": {
            "keywords": ["vacina autismo"],
            "keywords_en": ["vaccine autism"],
            "domains": ["health_science"],
        },
    },
    "juridico": {
        "summary": "Jurídico · Lei citada + precedentes do STJ",
        "value": {
            "keywords": ["marco civil da internet"],
            "legal_references": ["Lei 12.965/2014"],
            "country": "BR",
            "domains": ["legal_justice"],
        },
    },
    "arquivo_web": {
        "summary": "Memória da web · Histórico de uma página (Wayback)",
        "value": {
            "keywords": ["pagina"],
            "urls": ["http://g1.globo.com"],
            "domains": ["web_history"],
        },
    },
    "fr_chomage": {
        "summary": "FR · Datasets sobre desemprego (data.gouv.fr + INSEE)",
        "value": {"keywords": ["chômage"], "country": "FR"},
    },
}


@router.get("", response_model=list[ConnectorInfo], summary="Lista as fontes oficiais disponíveis")
async def list_connectors(
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
) -> list[ConnectorInfo]:
    return [
        ConnectorInfo(
            id=c.source_id,
            country=c.country,
            publisher=c.publisher,
            base_url=c.base_url,
            domains=sorted(c.domains),
            enabled=c.enabled,
            disabled_reason=c.disabled_reason,
        )
        for c in service.connectors
    ]


@router.post(
    "/search",
    response_model=EvidenceSearchResponse,
    summary="Busca evidências nas fontes oficiais (não precisa de chave de IA)",
    description=(
        "Consulta diretamente os conectores governamentais, sem passar por um modelo de IA. "
        "Útil para conferir quais dados públicos sustentariam uma checagem."
    ),
)
async def search_evidence(
    body: Annotated[EvidenceSearchRequest, Body(openapi_examples=SEARCH_EXAMPLES)],
    service: Annotated[FactCheckService, Depends(get_fact_check_service)],
) -> EvidenceSearchResponse:
    analysis = ClaimAnalysis(
        country=body.country,
        domains=body.domains,
        keywords=body.keywords,
        keywords_en=body.keywords_en,
        topics=body.topics,
        topics_en=body.keywords_en,
        people=body.people,
        legal_references=body.legal_references,
        urls=body.urls,
    )
    evidence, queried, failures = await service.collect_evidence(analysis)
    return EvidenceSearchResponse(
        connectors_queried=queried, evidence=evidence, connector_failures=failures
    )
