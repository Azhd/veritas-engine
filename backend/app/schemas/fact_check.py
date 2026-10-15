"""Pydantic schemas for fact-checking requests, LLM intermediate outputs and the final report."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.schemas.evidence import Country, Domain
from app.schemas.forensics import MediaForensicsReport


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


class ReplyLanguage(StrEnum):
    """Language of the citizen app page; the verdict explanation is written in it."""

    PT = "pt"
    EN = "en"
    FR = "fr"


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
    source_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Link de onde a informação veio; também é auditado no Internet Archive.",
    )
    language: ReplyLanguage | None = Field(
        default=None,
        description="Idioma da explicação (pt, en, fr). Sem ele, usa o idioma da afirmação.",
    )

    @field_validator("source_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or "." not in parsed.netloc:
            raise ValueError("source_url must be an absolute http(s) URL")
        return value

    @field_validator("claim")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("claim must have at least 5 non-blank characters")
        return value


# ---------------------------------------------------------------- LLM intermediate outputs
_LIST_LIMITS = {
    "years": 4,
    "keywords": 8,
    "keywords_en": 8,
    "people": 5,
    "topics": 5,
    "topics_en": 5,
    "legal_references": 5,
    "urls": 5,
}
_COUNTRY_ALIASES = {
    "BRASIL": "BR", "BRAZIL": "BR", "FRANCA": "FR", "FRANÇA": "FR", "FRANCE": "FR",
    "BOTH": "AMBOS", "UNKNOWN": "DESCONHECIDO", "": "DESCONHECIDO", "GLOBAL": "DESCONHECIDO",
    "EU": "DESCONHECIDO", "UE": "DESCONHECIDO", "INTERNACIONAL": "DESCONHECIDO",
}  # fmt: skip


def _as_str_list(value: Any) -> list[str]:
    """Free/open models return lists in many shapes: accept them instead of failing."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [part for part in value.split(",")]
    if not isinstance(value, list | tuple):
        value = [value]
    return [str(v).strip() for v in value if v is not None and str(v).strip()]


class ClaimAnalysis(BaseModel):
    """Step 2 output: context, knowledge areas and search terms extracted from the claim."""

    country: CountryContext = CountryContext.DESCONHECIDO
    domains: list[Domain] = Field(default_factory=list, max_length=7)
    keywords: list[str] = Field(default_factory=list, max_length=8)
    keywords_en: list[str] = Field(default_factory=list, max_length=8)
    people: list[str] = Field(default_factory=list, max_length=5)
    topics: list[str] = Field(default_factory=list, max_length=5)
    topics_en: list[str] = Field(default_factory=list, max_length=5)
    legal_references: list[str] = Field(default_factory=list, max_length=5)
    years: list[str] = Field(default_factory=list, max_length=4, description="Years cited.")
    urls: list[str] = Field(default_factory=list, max_length=5)
    language: str = Field(default="pt", description="ISO 639-1 language of the claim.")

    @field_validator("country", mode="before")
    @classmethod
    def _country(cls, value: Any) -> Any:
        if value is None:
            return CountryContext.DESCONHECIDO
        text = str(value).strip().upper()
        return _COUNTRY_ALIASES.get(text, text)

    @field_validator("domains", mode="before")
    @classmethod
    def _drop_unknown_domains(cls, value: Any) -> Any:
        # LLMs sometimes invent categories; keep only the known ones instead of failing.
        allowed = {d.value for d in Domain}
        cleaned = [v.lower() for v in _as_str_list(value)]
        return list(dict.fromkeys(v for v in cleaned if v in allowed))

    @field_validator(*_LIST_LIMITS, mode="before")
    @classmethod
    def _lists(cls, value: Any, info: Any) -> list[str]:
        return _as_str_list(value)[: _LIST_LIMITS[info.field_name]]

    @field_validator("language", mode="before")
    @classmethod
    def _language(cls, value: Any) -> str:
        text = str(value or "pt").strip().lower()
        names = {"portuguese": "pt", "português": "pt", "portugues": "pt", "french": "fr",
                 "français": "fr", "francais": "fr", "francês": "fr", "english": "en",
                 "inglês": "en", "spanish": "es", "español": "es"}  # fmt: skip
        return names.get(text, text[:2] if len(text) >= 2 else "pt")


class LLMVerdict(BaseModel):
    """Step 5 output produced by the LLM."""

    verdict: Verdict
    confidence_score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)
    cited_evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize_verdict(cls, value: Any) -> Any:
        text = str(value or "").strip().upper().replace(" ", "_")
        aliases = {
            "TRUE": "VERDADEIRO", "VERDADE": "VERDADEIRO", "FALSE": "FALSO",
            "MISLEADING": "ENGANOSO", "INCONCLUSIVE": "INCONCLUSIVO",
            "SEM_DADOS": "SEM_DADOS_SUFICIENTES", "INSUFFICIENT_DATA": "SEM_DADOS_SUFICIENTES",
        }  # fmt: skip
        return aliases.get(text, text)

    @field_validator("confidence_score", mode="before")
    @classmethod
    def _confidence(cls, value: Any) -> Any:
        try:
            number = float(str(value).strip().rstrip("%").replace(",", "."))
        except (TypeError, ValueError):
            return 0.5
        if number > 1:  # "85" or "85%"
            number /= 100
        return min(max(number, 0.0), 1.0)

    @field_validator("cited_evidence_ids", mode="before")
    @classmethod
    def _evidence_ids(cls, value: Any) -> list[str]:
        ids = []
        for item in _as_str_list(value):
            item = item.strip("[] ").upper()
            ids.append(f"E{item}" if item.isdigit() else item)
        return ids

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


# ---------------------------------------------------------------- media (Phase 3)
class TimedCheck(BaseModel):
    """A claim found in the media, where it was said, and its fact-check."""

    start_time: float | None = Field(
        default=None, description="Seconds into the media; None for the text sent by the user."
    )
    label: str = Field(description="'01:23' or 'Texto informado'.")
    quote: str = ""
    report: FactCheckReport


class MediaFactCheckReport(BaseModel):
    forensics: MediaForensicsReport
    checks: list[TimedCheck] = Field(default_factory=list)
    ai_used: bool
    provider: str
    model: str
    notes: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
