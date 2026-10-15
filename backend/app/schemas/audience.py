"""Audience modes (Phase 4): the same facts and official evidence, written for each reader.

The report keeps every section for every mode; ``mode`` says which reader the AI explanation
was written for and which sections the app shows first. Sections are structured data (dates,
identifiers, formatted references), so the citizen app can render them in any page language.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class AudienceMode(StrEnum):
    #: Plain words, short paragraphs, "why it is true/false in 1 minute", share card.
    GENERAL_FAMILY = "general_family"
    #: OSINT method, timeline, contradictions between sources, metadata, republication history.
    JOURNALISM_STUDENT = "journalism_student"
    #: Laws, case law, scientific references (ABNT / APA with DOI and PubMed ID).
    LAW_ACADEMIC = "law_academic"


class TimelineKind(StrEnum):
    PUBLICATION = "publication"  # article, report, dataset, legislative bill
    LAW = "law"  # law, EU act, court decision
    DATA = "data"  # official statistics series (last observation)
    ARCHIVE_FIRST = "archive_first"  # first capture of the cited page in the web archive
    ARCHIVE_LAST = "archive_last"  # last capture


class TimelineEvent(BaseModel):
    day: date
    kind: TimelineKind
    title: str
    evidence_id: str


class ArchiveHistory(BaseModel):
    """Republication history of a cited page (Internet Archive), for journalists."""

    evidence_id: str
    url: str
    captures_inspected: int = 0
    distinct_versions: int = 0
    content_changed: bool = False
    title_changed: bool = False
    removed_or_redirected: bool = False
    first_title: str | None = None
    last_title: str | None = None


class Citation(BaseModel):
    evidence_id: str
    abnt: str = Field(description="ABNT NBR 6023 reference.")
    apa: str = Field(description="APA 7th edition reference.")
    level: str | None = Field(
        default=None,
        description="'high_level' (systematic review, meta-analysis, RCT), 'retracted' or None.",
    )


class LegalReference(BaseModel):
    """A law, EU act, bill or court precedent among the sources."""

    kind: str = Field(description="norma | celex | tema | proposicao | materia | cid | pourvoi")
    value: str
    title: str
    url: str
    evidence_id: str
    cited: bool = False


class AudienceReport(BaseModel):
    mode: AudienceMode
    #: AI only: up to 3 short points ("why in 1 minute"); empty without AI.
    key_points: list[str] = Field(default_factory=list)
    #: AI only: disagreements between sources noticed by the model.
    contradictions: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    archive: list[ArchiveHistory] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    legal_references: list[LegalReference] = Field(default_factory=list)
