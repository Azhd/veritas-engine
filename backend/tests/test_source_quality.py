"""Source quality: EUR-Lex ranking by year/act type, Brazil in any language, cited years."""

from __future__ import annotations

import pytest

from app.connectors.br_gov import INDICATORS
from app.connectors.legal_justice import EurLexConnector, build_eurlex_query, eurlex_act_type
from app.schemas.evidence import Country, Domain, EvidenceQuery
from app.schemas.fact_check import CountryContext
from app.services.claim_heuristics import (
    enrich_analysis,
    extract_years,
    heuristic_analysis,
    normalize,
)
from tests.conftest import json_response, mock_client
from tests.test_claim_heuristics import _fake


def _row(celex: str, title: str, day: str) -> dict:
    return {
        "celex": {"value": celex},
        "title": {"value": title},
        "date": {"value": day},
    }


AI_ACT_RESULTS = {
    "results": {
        "bindings": [
            _row("32026R1744", "Regulation (EU) 2026/1744 of the European Parliament and of the "
                 "Council amending Regulation (EU) 2024/1689", "2026-07-08"),
            _row("32024R1028R(01)", "Corrigendum to Regulation (EU) 2024/1028", "2024-06-01"),
            _row("32024R1732", "Council Regulation (EU) 2024/1732 amending Regulation 2021/1173",
                 "2024-06-17"),
            _row("32024R1689", "Regulation (EU) 2024/1689 of the European Parliament and of the "
                 "Council laying down harmonised rules on artificial intelligence and amending "
                 "Regulations", "2024-06-13"),
        ]
    }
}  # fmt: skip


# =============================================================== years
@pytest.mark.parametrize(
    ("claim", "years"),
    [
        ("La directive a été adoptée en 2019.", ["2019"]),
        ("2023 et 2024 ont été des records.", ["2023", "2024"]),
        ("A Lei 12.965/2014 obriga provedores.", []),  # law numbers are not cited years
        ("Mais de 2.000 casos e R$ 2024,50 gastos.", []),
        ("https://site.example/2021/x foi apagado em 2022.", ["2022"]),
    ],
)
def test_extract_years(claim, years):
    assert extract_years(claim) == years


# =============================================================== EUR-Lex
def test_act_type_filter_in_query():
    query = build_eurlex_query(["copyright"], limit=5, act_type="L")
    assert 'FILTER(SUBSTR(STR(?celex), 6, 1) = "L")' in query
    assert "SUBSTR" not in build_eurlex_query(["copyright"], limit=5)


@pytest.mark.parametrize(
    ("words", "kind"),
    [(["Directive"], "L"), (["règlement européen"], "R"), (["decisão"], "D"), (["lei"], None)],
)
def test_act_type_detection(words, kind):
    assert eurlex_act_type(words) == kind


async def test_cited_year_and_major_law_rank_first():
    seen = []

    def handler(request):
        seen.append(request.url.params["query"])
        return json_response(AI_ACT_RESULTS)

    conn = EurLexConnector(mock_client(handler))
    evidence = await conn.search_evidence(
        EvidenceQuery(
            keywords=["règlement", "intelligence", "artificielle"],
            keywords_en=["artificial intelligence"],
            years=["2024"],
            language="fr",
        )
    )
    # the act of the cited year adopted by Parliament and Council, then same-year acts,
    # corrections after them, later amendments last
    assert [e.identifiers["celex"] for e in evidence] == [
        "32024R1689",
        "32024R1732",
        "32024R1028R(01)",
        "32026R1744",
    ]
    first = seen[0]
    assert '"artificial" AND "intelligence" AND "2024"' in first  # the year narrows first
    assert '= "R")' in first  # "règlement" (French words) sets the act type
    assert "LIMIT 20" in first  # more candidates than shown, to rank them


async def test_ai_acronym_is_spelled_out_for_titles():
    seen = []

    def handler(request):
        seen.append(request.url.params["query"])
        return json_response(AI_ACT_RESULTS)

    conn = EurLexConnector(mock_client(handler))
    await conn.search_acts(["EU AI rules"], language="ENG")
    assert '"artificial" AND "intelligence" AND "rules"' in seen[0]


# =============================================================== Brazil in any language
@pytest.mark.parametrize(
    ("claim", "hint"),
    [
        ("Le Brésil compte plus de 200 millions d'habitants.", "fr"),
        ("Brazil has more than 200 million inhabitants.", "en"),
        ("O Brasil tem mais de 200 milhões de habitantes.", "pt"),
    ],
)
def test_brazil_population_claim_reaches_ibge_in_any_language(claim, hint):
    analysis = enrich_analysis(heuristic_analysis(claim, hint), claim)
    assert analysis.country is CountryContext.BR
    assert Domain.ECONOMY_STATISTICS in analysis.domains
    population = next(i for i in INDICATORS if "populacao" in i.triggers)
    haystack = normalize(" ".join([*analysis.keywords, *analysis.topics, *analysis.keywords_en]))
    assert any(trigger in haystack for trigger in population.triggers)


def test_ai_acronym_only_in_upper_case():
    assert "artificial intelligence" in heuristic_analysis("O regulamento de IA da UE.").keywords_en
    assert "artificial intelligence" not in heuristic_analysis("Ele ia ao mercado.").keywords_en


# =============================================================== Europe reaches EU sources first
def test_claim_about_europe_queries_eu_sources_first(service):
    analysis = heuristic_analysis("O regulamento europeu de IA foi adotado em 2024.", "pt")
    assert analysis.country is CountryContext.BR
    ids = [c.source_id for c in service.select_connectors(analysis)]
    assert ids[0] == "eu.eurlex"
    assert "br.legislacao" in ids  # national sources are still consulted


@pytest.fixture
def service():
    from app.services.fact_checker import FactCheckService

    return FactCheckService(
        [
            _fake("br.legislacao", Country.BR, Domain.LEGAL_JUSTICE),
            _fake("eu.eurlex", Country.EU, Domain.LEGAL_JUSTICE),
        ]
    )
