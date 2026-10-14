"""Normalized evidence returned by every government connector."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Country(StrEnum):
    BR = "BR"
    FR = "FR"


class EvidenceQuery(BaseModel):
    """What the orchestrator asks connectors to look for."""

    keywords: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=1, le=50)

    @property
    def text(self) -> str:
        """Compact full-text query: public search APIs degrade with too many AND-ed terms."""
        return " ".join(self.keywords[:3])


class Evidence(BaseModel):
    """A single piece of evidence retrieved from an official source."""

    connector: str = Field(description="Connector identifier, e.g. 'br.camara'.")
    country: Country
    publisher: str = Field(description="Public authority that publishes the data.")
    title: str
    url: str = Field(description="Human-auditable URL of the primary source.")
    excerpt: str = ""
    data: dict[str, Any] = Field(default_factory=dict, description="Raw structured data points.")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
