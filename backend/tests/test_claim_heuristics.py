"""Zero-cost claim analysis (no LLM) and domain-based source routing."""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.connectors.base import BaseGovConnector
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery
from app.schemas.fact_check import ClaimAnalysis, CountryContext
from app.services.claim_heuristics import (
    enrich_analysis,
    extract_urls,
    heuristic_analysis,
    heuristic_domains,
    translate_terms,
)
from app.services.fact_checker import FactCheckService

# =============================================================== heuristics


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("Vacinas causam autismo em crianças", {Domain.HEALTH_SCIENCE}),
        ("A Rússia invadiu a Ucrânia e a ONU condenou", {Domain.GEOPOLITICS}),
        ("O STF julgou a lei inconstitucional", {Domain.LEGAL_JUSTICE}),
        ("A inflação passou de 10% e o desemprego subiu", {Domain.ECONOMY_STATISTICS}),
        ("O deputado votou contra o projeto de lei", {Domain.POLITICS_LEGISLATION}),
        ("Le vaccin contre la rougeole est dangereux", {Domain.HEALTH_SCIENCE}),
    ],
)
def test_heuristic_domains(claim, expected):
    assert expected <= set(heuristic_domains(claim))


def test_urls_add_web_history_domain():
    claim = "A matéria https://g1.globo.com/x foi apagada."
    assert extract_urls(claim) == ["https://g1.globo.com/x"]
    assert Domain.WEB_HISTORY in heuristic_domains(claim, extract_urls(claim))


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("Vacinas causam autismo", ["vaccines", "autism"]),
        ("A expectativa de vida caiu no Brasil", ["life expectancy"]),
        ("Le cessez-le-feu à Gaza", ["ceasefire", "gaza"]),
        ("A hidroxicloroquina cura covid", ["hydroxychloroquine", "covid-19"]),
        ("Nada traduzível aqui", []),
    ],
)
def test_offline_glossary(claim, expected):
    assert translate_terms(claim) == expected


def test_heuristic_analysis_is_complete_without_llm():
    analysis = heuristic_analysis(
        "Segundo a Lei 12.965/2014, vacinas causam autismo: veja www.exemplo.com.br/x"
    )
    assert analysis.country is CountryContext.BR
    assert analysis.legal_references == ["Lei 12965/2014"]
    assert analysis.urls == ["www.exemplo.com.br/x"]
    assert {"vaccines", "autism"} <= set(analysis.keywords_en)
    assert {Domain.HEALTH_SCIENCE, Domain.LEGAL_JUSTICE, Domain.WEB_HISTORY} <= set(
        analysis.domains
    )
    assert "www" not in " ".join(analysis.keywords)


def test_enrich_keeps_llm_values_and_adds_deterministic_extractions():
    llm = ClaimAnalysis(
        country=CountryContext.BR,
        domains=[Domain.HEALTH_SCIENCE],
        keywords=["vacina autismo"],
        keywords_en=["vaccine autism"],
    )
    enriched = enrich_analysis(llm, "Vacina causa autismo? http://boato.com e Lei 8.080/1990")
    assert enriched.keywords_en == ["vaccine autism"]  # LLM value kept
    assert enriched.urls == ["http://boato.com"]
    assert enriched.legal_references == ["Lei 8080/1990"]
    # the cited law adds the legal area to the AI's health area
    assert enriched.domains == [Domain.HEALTH_SCIENCE, Domain.LEGAL_JUSTICE, Domain.WEB_HISTORY]


def test_enrich_adds_rule_based_areas_the_ai_missed():
    # An open model filed this EU regulation under politics only: EUR-Lex was never queried.
    llm = ClaimAnalysis(domains=[Domain.POLITICS_LEGISLATION], keywords=["Union européenne"])
    claim = "L’Union européenne a adopté en 2024 un règlement sur l’intelligence artificielle."
    enriched = enrich_analysis(llm, claim)
    assert enriched.domains[0] is Domain.POLITICS_LEGISLATION  # the AI's areas come first
    assert Domain.LEGAL_JUSTICE in enriched.domains


def test_unknown_llm_domains_are_dropped():
    analysis = ClaimAnalysis.model_validate({"domains": ["health_science", "astrology"]})
    assert analysis.domains == [Domain.HEALTH_SCIENCE]


# =============================================================== routing
class _Fake(BaseGovConnector):
    base_url = "https://fake.invalid"
    publisher = "fake"
    calls: ClassVar[list[str]] = []

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        _Fake.calls.append(self.source_id)
        return []


def _fake(source_id: str, country: Country, *domains: Domain, enabled: bool = True):
    attrs = {
        "source_id": source_id,
        "country": country,
        "domains": frozenset(domains),
        "disabled_reason": property(lambda self: None if enabled else "needs key"),
    }
    return type(f"Fake_{source_id.replace('.', '_')}", (_Fake,), attrs)()


@pytest.fixture
def service() -> FactCheckService:
    return FactCheckService(
        [
            _fake("br.camara", Country.BR, Domain.POLITICS_LEGISLATION),
            _fake("br.ibge", Country.BR, Domain.ECONOMY_STATISTICS),
            _fake("br.stj", Country.BR, Domain.LEGAL_JUSTICE),
            _fake("fr.data_gouv", Country.FR, Domain.ECONOMY_STATISTICS),
            _fake("eu.eurlex", Country.EU, Domain.LEGAL_JUSTICE),
            _fake("science.pubmed", Country.GLOBAL, Domain.HEALTH_SCIENCE),
            _fake("geo.gdelt", Country.GLOBAL, Domain.GEOPOLITICS),
            _fake("geo.reliefweb", Country.GLOBAL, Domain.GEOPOLITICS, enabled=False),
            _fake("web.wayback", Country.GLOBAL, Domain.WEB_HISTORY),
        ]
    )


def _ids(service, **analysis) -> list[str]:
    return [c.source_id for c in service.select_connectors(ClaimAnalysis(**analysis))]


def test_health_claim_routes_to_science_only(service):
    assert _ids(service, country="BR", domains=["health_science"]) == ["science.pubmed"]


def test_default_domains_keep_phase1_behavior(service):
    assert _ids(service, country="BR") == ["br.camara", "br.ibge"]


def test_legal_fr_claim_includes_eu_law(service):
    assert _ids(service, country="FR", domains=["legal_justice"]) == ["eu.eurlex"]
    assert _ids(service, country="BR", domains=["legal_justice"]) == ["br.stj"]


def test_disabled_connectors_are_skipped(service):
    assert _ids(service, country="BR", domains=["geopolitics"]) == ["geo.gdelt"]


def test_urls_always_trigger_web_archive(service):
    assert "web.wayback" in _ids(service, country="BR", urls=["http://a.com/b"])


def test_brazilian_law_citation_implies_brazil():
    from app.services.claim_heuristics import heuristic_country

    claim = "A Lei 12.965/2014 obriga provedores a guardar registros por 5 anos."
    assert heuristic_country(claim) is CountryContext.BR
