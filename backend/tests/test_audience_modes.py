"""Phase 4 - audience modes: prompt style, deterministic sections, API and AI output."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.engines.prompt_templates.fact_check import build_verdict_prompt
from app.engines.verdict_engine import (
    abnt_reference,
    apa_reference,
    audience_instructions,
    build_audience_report,
)
from app.main import create_app
from app.schemas.audience import AudienceMode, TimelineKind
from app.schemas.evidence import Country, Evidence
from app.schemas.fact_check import LLMVerdict
from app.services.fact_checker import FactCheckService
from tests.conftest import FakeLLMProvider, fake_credentials, make_settings

ACCESSED = date(2026, 10, 15)


def _evidence(**overrides) -> Evidence:
    data = {
        "connector": "science.pubmed",
        "country": Country.GLOBAL,
        "publisher": "PubMed - National Library of Medicine (NCBI/NIH)",
        "title": "Vaccines are not associated with autism: an evidence-based meta-analysis.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/24814559/",
        "authors": ["Taylor LE", "Swerdfeger AL", "Eslick GD"],
        "venue": "Vaccine",
        "published_at": date(2014, 6, 17),
        "identifiers": {"pmid": "24814559", "doi": "10.1016/j.vaccine.2014.04.085"},
        "data": {"high_level_evidence": True, "retracted": False},
    }
    data.update(overrides)
    return Evidence(**data)


STUDY = _evidence()
LAW = _evidence(
    connector="eu.eurlex",
    country=Country.EU,
    publisher="EUR-Lex - Publications Office of the European Union",
    title="Directive (EU) 2019/790 on copyright in the Digital Single Market",
    url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32019L0790",
    authors=[],
    venue="Official Journal of the European Union",
    published_at=date(2019, 4, 17),
    identifiers={"celex": "32019L0790"},
    data={},
)
ARCHIVE = _evidence(
    connector="web.wayback",
    publisher="Internet Archive",
    title="Histórico no Internet Archive: https://boato.example/post",
    url="https://web.archive.org/web/20200101000000/https://boato.example/post",
    authors=[],
    venue="Wayback Machine",
    published_at=date(2020, 1, 1),
    identifiers={"snapshot_first": "20200101000000", "snapshot_last": "20231105120000"},
    data={
        "archived": True,
        "captures_inspected": 12,
        "distinct_versions": 3,
        "content_changed": True,
        "title_changed": True,
        "first_title": "Vacina causa autismo",
        "last_title": "Corrigido: vacina não causa autismo",
        "removed_or_redirected": False,
    },
)


# =============================================================== references
def test_abnt_reference_for_a_scientific_article():
    assert abnt_reference(STUDY, ACCESSED) == (
        "TAYLOR, L. E.; SWERDFEGER, A. L.; ESLICK, G. D. Vaccines are not associated with "
        "autism: an evidence-based meta-analysis. Vaccine, 2014. DOI: "
        "10.1016/j.vaccine.2014.04.085. Disponível em: https://pubmed.ncbi.nlm.nih.gov/24814559/. "
        "Acesso em: 15 out. 2026."
    )


def test_apa_reference_uses_doi_link():
    assert apa_reference(STUDY) == (
        "Taylor, L. E., Swerdfeger, A. L., & Eslick, G. D. (2014). Vaccines are not associated "
        "with autism: an evidence-based meta-analysis. Vaccine. "
        "https://doi.org/10.1016/j.vaccine.2014.04.085"
    )


def test_references_without_authors_use_the_institution():
    assert abnt_reference(LAW, ACCESSED).startswith(
        "EUR-LEX - PUBLICATIONS OFFICE OF THE EUROPEAN UNION. Directive (EU) 2019/790"
    )
    assert apa_reference(LAW).endswith("(2019). Directive (EU) 2019/790 on copyright in the "
                                       "Digital Single Market. https://eur-lex.europa.eu/legal-"
                                       "content/EN/TXT/?uri=CELEX:32019L0790")  # fmt: skip
    many = _evidence(authors=["A B", "C D", "E F", "G H"])
    assert "; et al." in abnt_reference(many, ACCESSED)


# =============================================================== deterministic sections
def test_audience_report_sections():
    numbered = [("E1", STUDY), ("E2", LAW), ("E3", ARCHIVE)]
    report = build_audience_report(
        AudienceMode.JOURNALISM_STUDENT, numbered, cited={"E2"}, accessed=ACCESSED,
        search_terms=["vaccine", "autism", "vaccine"],
    )  # fmt: skip
    assert report.search_terms == ["vaccine", "autism"]
    kinds = [(e.day.isoformat(), e.kind) for e in report.timeline]
    assert kinds == [
        ("2014-06-17", TimelineKind.PUBLICATION),
        ("2019-04-17", TimelineKind.LAW),
        ("2020-01-01", TimelineKind.ARCHIVE_FIRST),
        ("2023-11-05", TimelineKind.ARCHIVE_LAST),
    ]
    (page,) = report.archive
    assert page.url == "https://boato.example/post" and page.distinct_versions == 3
    assert page.title_changed and page.last_title.startswith("Corrigido")
    (law,) = report.legal_references
    assert (law.kind, law.value, law.cited) == ("celex", "32019L0790", True)
    assert [c.level for c in report.citations] == ["high_level", None, None]
    assert report.key_points == [] and report.contradictions == []  # AI only


def test_retracted_articles_are_flagged():
    retracted = _evidence(data={"retracted": True, "high_level_evidence": True})
    (citation,) = build_audience_report(AudienceMode.LAW_ACADEMIC, [("E1", retracted)]).citations
    assert citation.level == "retracted"


# =============================================================== prompt and AI output
@pytest.mark.parametrize(
    ("mode", "marker"),
    [
        (AudienceMode.GENERAL_FAMILY, "1 minuto"),
        (AudienceMode.JOURNALISM_STUDENT, "OSINT"),
        (AudienceMode.LAW_ACADEMIC, "nível de evidência"),
    ],
)
def test_verdict_prompt_carries_the_audience_style(mode, marker):
    prompt = build_verdict_prompt("Vacinas causam autismo.", [("E1", STUDY)], "fr", mode)
    assert audience_instructions(mode) in prompt and marker in prompt


def test_llm_audience_fields_are_lenient():
    verdict = LLMVerdict.model_validate(
        {
            "verdict": "FALSE",
            "confidence_score": "90%",
            "explanation": "x",
            "cited_evidence_ids": ["1"],
            "key_points": [{"text": "um"}, "dois", "", "três", "quatro"],
            "contradictions": "datas diferentes",
        }
    )
    assert verdict.key_points == ["um", "dois", "três"]
    assert verdict.contradictions == ["datas diferentes"]
    assert (
        LLMVerdict.model_validate(
            {"verdict": "TRUE", "confidence_score": 1, "explanation": "x"}
        ).key_points
        == []
    )


async def test_ai_points_reach_the_report():
    llm = FakeLLMProvider(
        fake_credentials(),
        outputs=[
            '{"language": "pt", "domains": ["health_science"]}',
            '{"verdict": "FALSO", "confidence_score": 0.95, "explanation": "Não há relação [E1].",'
            ' "cited_evidence_ids": ["E1"], "key_points": ["Estudos com milhões de crianças"],'
            ' "contradictions": []}',
        ],
    )
    service = FactCheckService([])
    service.collect_evidence = _fixed_evidence  # type: ignore[method-assign]
    report = await service.check_text(
        "Vacinas causam autismo.", llm, audience_mode=AudienceMode.LAW_ACADEMIC, language="pt"
    )
    assert report.audience.mode is AudienceMode.LAW_ACADEMIC
    assert report.audience.key_points == ["Estudos com milhões de crianças"]
    assert report.audience.citations[0].evidence_id == "E1"
    assert "nível de evidência" in llm.calls[1]["prompt"]


async def _fixed_evidence(analysis):
    return [STUDY], ["science.pubmed"], []


# =============================================================== API
@pytest.fixture
def api():
    with TestClient(create_app(make_settings())) as client:
        yield client


def test_text_route_accepts_audience_and_citizen_mode_has_sections(api, monkeypatch):
    monkeypatch.setattr(FactCheckService, "collect_evidence", lambda self, a: _fixed_evidence(a))
    body = {"claim": "Vacinas causam autismo.", "audience_mode": "law_academic"}
    report = api.post("/api/v1/fact-check/text", json=body).json()
    assert report["verdict"] == "SEM_CHAVE_IA_DADOS_BRUTOS"
    audience = report["audience"]
    assert audience["mode"] == "law_academic"
    assert audience["citations"][0]["abnt"].startswith("TAYLOR, L. E.")
    default = api.post("/api/v1/fact-check/text", json={"claim": "Vacinas causam autismo."})
    assert default.json()["audience"]["mode"] == "general_family"
    bad = api.post("/api/v1/fact-check/text", json={**body, "audience_mode": "kids"})
    assert bad.status_code == 422
