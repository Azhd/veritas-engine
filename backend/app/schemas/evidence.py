"""Normalized evidence returned by every primary-source connector."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Country(StrEnum):
    """Jurisdiction / scope of a source."""

    BR = "BR"
    FR = "FR"
    EU = "EU"
    GLOBAL = "GLOBAL"


class Domain(StrEnum):
    """Knowledge areas a claim can touch; connectors declare which ones they cover."""

    POLITICS_LEGISLATION = "politics_legislation"
    ECONOMY_STATISTICS = "economy_statistics"
    HEALTH_SCIENCE = "health_science"
    GEOPOLITICS = "geopolitics"
    LEGAL_JUSTICE = "legal_justice"
    WEB_HISTORY = "web_history"


#: Domains assumed when the claim analysis does not name any (Phase 1 behavior).
DEFAULT_DOMAINS = frozenset({Domain.POLITICS_LEGISLATION, Domain.ECONOMY_STATISTICS})


class EvidenceQuery(BaseModel):
    """What the orchestrator asks connectors to look for."""

    keywords: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(
        default_factory=list, description="English search terms for international sources."
    )
    people: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    topics_en: list[str] = Field(default_factory=list, description="English topic names.")
    countries: list[str] = Field(
        default_factory=list, description="ISO 3166-1 alpha-2 codes of the claim context."
    )
    legal_references: list[str] = Field(
        default_factory=list, description="Explicit legal citations, e.g. 'Lei 12.965/2014'."
    )
    urls: list[str] = Field(default_factory=list, description="URLs to audit in web archives.")
    max_results: int = Field(default=5, ge=1, le=50)

    @property
    def text(self) -> str:
        """Compact full-text query: public search APIs degrade with too many AND-ed terms."""
        return " ".join(self.keywords[:3])

    @property
    def text_en(self) -> str:
        """English query, falling back to the native keywords."""
        return " ".join((self.keywords_en or self.keywords)[:3])


class Evidence(BaseModel):
    """A single piece of evidence retrieved from a primary source."""

    connector: str = Field(description="Connector identifier, e.g. 'br.camara'.")
    country: Country
    publisher: str = Field(description="Authority or institution that publishes the data.")
    title: str
    url: str = Field(description="Human-auditable URL of the primary source.")
    excerpt: str = ""
    authors: list[str] = Field(default_factory=list)
    venue: str | None = Field(default=None, description="Journal, court, gazette or outlet.")
    published_at: date | None = Field(default=None, description="Publication / event date.")
    identifiers: dict[str, str] = Field(
        default_factory=dict, description="Stable ids: doi, pmid, celex, lei, tema, snapshot..."
    )
    data: dict[str, Any] = Field(default_factory=dict, description="Raw structured data points.")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
