"""Pydantic schemas for fact-checking requests, LLM intermediate outputs and the final report."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.evidence import Country


class Verdict(StrEnum):
    VERDADEIRO = "VERDADEIRO"
    FALSO = "FALSO"
    ENGANOSO = "ENGANOSO"
    INCONCLUSIVO = "INCONCLUSIVO"
    SEM_DADOS_SUFICIENTES = "SEM_DADOS_SUFICIENTES"


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
    """Step 2 output: context country and search terms extracted from the claim."""

    country: CountryContext = CountryContext.DESCONHECIDO
    keywords: list[str] = Field(default_factory=list, max_length=8)
    people: list[str] = Field(default_factory=list, max_length=5)
    topics: list[str] = Field(default_factory=list, max_length=5)
    language: str = Field(default="pt", description="ISO 639-1 language of the claim.")


class LLMVerdict(BaseModel):
    """Step 5 output produced by the LLM."""

    verdict: Verdict
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)
    cited_evidence_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- Report
class SourceReference(BaseModel):
    evidence_id: str
    title: str
    url: str
    publisher: str
    connector: str
    country: Country
    excerpt: str = ""
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
    keywords: list[str] = Field(default_factory=list)
    connectors_queried: list[str] = Field(default_factory=list)
    connector_failures: list[ConnectorFailure] = Field(default_factory=list)
    provider: str
    model: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        self.confidence_score = round(self.confidence_score, 3)
