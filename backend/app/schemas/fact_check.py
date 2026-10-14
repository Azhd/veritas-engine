"""Pydantic schemas for fact-checking requests, LLM intermediate outputs and the final report."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.evidence import Country, Domain


class Verdict(StrEnum):
    VERDADEIRO = "VERDADEIRO"
    FALSO = "FALSO"
    ENGANOSO = "ENGANOSO"
    INCONCLUSIVO = "INCONCLUSIVO"
    SEM_DADOS_SUFICIENTES = "SEM_DADOS_SUFICIENTES"
    #: Citizen mode: no AI was available, the report lists raw official evidence for the reader.
    SEM_CHAVE_IA_DADOS_BRUTOS = "SEM_CHAVE_IA_DADOS_BRUTOS"


#: Verdicts that assert something about reality and therefore require cited official evidence.
ASSERTIVE_VERDICTS = frozenset({Verdict.VERDADEIRO, Verdict.FALSO, Verdict.ENGANOSO})


class CountryContext(StrEnum):
    BR = "BR"
    FR = "FR"
    AMBOS = "AMBOS"
    DESCONHECIDO = "DESCONHECIDO"

    def countries(self) -> set[Country]:
        if self is CountryContext.BR:
            return {Country.BR}
        if self is CountryContext.FR:
            return {Country.FR}
        return {Country.BR, Country.FR}


# ---------------------------------------------------------------- API input
class TextFactCheckRequest(BaseModel):
    claim: str = Field(min_length=5, max_length=5000, description="Afirmação a ser verificada.")
    country: CountryContext | None = Field(
        default=None, description="Força o país de contexto (senão é detectado automaticamente)."
    )

    @field_validator("claim")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("claim must have at least 5 non-blank characters")
        return value


# ---------------------------------------------------------------- LLM intermediate outputs
class ClaimAnalysis(BaseModel):
    """Step 2 output: context, knowledge areas and search terms extracted from the claim."""

    country: CountryContext = CountryContext.DESCONHECIDO
    domains: list[Domain] = Field(default_factory=list, max_length=6)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    keywords_en: list[str] = Field(default_factory=list, max_length=8)
    people: list[str] = Field(default_factory=list, max_length=5)
    topics: list[str] = Field(default_factory=list, max_length=5)
    topics_en: list[str] = Field(default_factory=list, max_length=5)
    legal_references: list[str] = Field(default_factory=list, max_length=5)
    urls: list[str] = Field(default_factory=list, max_length=5)
    language: str = Field(default="pt", description="ISO 639-1 language of the claim.")

    @field_validator("domains", mode="before")
    @classmethod
    def _drop_unknown_domains(cls, value: Any) -> Any:
        # LLMs sometimes invent categories; keep only the known ones instead of failing.
        if isinstance(value, list):
            allowed = {d.value for d in Domain}
            return [v for v in value if isinstance(v, str) and v in allowed]
        return value


class LLMVerdict(BaseModel):
    """Step 5 output produced by the LLM."""

    verdict: Verdict
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)
    cited_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("verdict")
    @classmethod
    def _not_citizen_mode(cls, value: Verdict) -> Verdict:
        if value is Verdict.SEM_CHAVE_IA_DADOS_BRUTOS:
            raise ValueError("SEM_CHAVE_IA_DADOS_BRUTOS is reserved for the no-AI mode")
        return value


# ---------------------------------------------------------------- Report
class SourceReference(BaseModel):
    evidence_id: str
    title: str
    url: str
    publisher: str
    connector: str
    country: Country
    excerpt: str = ""
    authors: list[str] = Field(default_factory=list)
    venue: str | None = None
    published_at: date | None = None
    identifiers: dict[str, str] = Field(default_factory=dict)
    retrieved_at: datetime
    cited: bool = Field(description="True when the LLM explicitly relied on this source.")


class ConnectorFailure(BaseModel):
    connector: str
    error: str


class FactCheckReport(BaseModel):
    claim: str
    verdict: Verdict
    confidence_score: float = Field(ge=0.0, le=1.0)
    primary_sources: list[SourceReference] = Field(default_factory=list)
    explanation: str
    country_context: CountryContext
    domains: list[Domain] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    connectors_queried: list[str] = Field(default_factory=list)
    connector_failures: list[ConnectorFailure] = Field(default_factory=list)
    ai_used: bool = Field(default=True, description="False in citizen mode (raw official data).")
    provider: str
    model: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self.confidence_score = round(self.confidence_score, 3)
