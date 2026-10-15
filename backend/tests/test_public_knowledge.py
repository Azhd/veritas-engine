"""Wikidata (public, non-official knowledge base): who holds which office."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.connectors.public_knowledge import WikidataConnector, countries_in, is_about_office
from app.schemas.evidence import Country, Evidence, EvidenceQuery
from app.services.fact_checker import FactCheckService
from tests.conftest import FakeLLMProvider, fake_credentials, json_response, mock_client

ENTITY = "http://www.wikidata.org/entity/"


def _binding(**values: str) -> dict:
    return {key: {"value": value} for key, value in values.items()}


LEADERS = {
    "results": {
        "bindings": [
            _binding(country="http://www.wikidata.org/entity/Q212", countryLabel="Ucrânia",
                     role="head_of_state", person="http://www.wikidata.org/entity/Q3874799",
                     personLabel="Volodymyr Zelensky", start="2019-05-20T00:00:00Z",
                     referenced="false"),
        ]
    }
}  # fmt: skip
HUMANS = {"results": {"bindings": [_binding(item="http://www.wikidata.org/entity/Q3052772")]}}
POSITIONS = {
    "results": {
        "bindings": [
            _binding(person=f"{ENTITY}Q3052772", personLabel="Emmanuel Macron",
                     positionLabel="Presidente da França", start="2017-05-14T00:00:00Z",
                     referenced="true"),
            _binding(person=f"{ENTITY}Q3052772", personLabel="Emmanuel Macron",
                     positionLabel="Ministro da Economia", start="2014-08-26T00:00:00Z",
                     end="2016-08-30T00:00:00Z", referenced="false"),
        ]
    }
}  # fmt: skip
SEARCH = {
    "search": [
        {"id": "Q627627", "label": "mácron"},  # the diacritic, not a person
        {"id": "Q3052772", "label": "Emmanuel Macron"},
    ]
}


def _handler(seen: list):
    def handler(request):
        seen.append(request)
        params = parse_qs(urlparse(str(request.url)).query)
        if params.get("action") == ["wbsearchentities"]:
            return json_response(SEARCH)
        query = params["query"][0]
        if "p:P35" in query:
            return json_response(LEADERS)
        if "wdt:P31 wd:Q5" in query and "P39" not in query:
            return json_response(HUMANS)
        return json_response(POSITIONS)

    return handler


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Macron é presidente da Ucrânia", ["Q212"]),
        ("Macron é presidente da Franca", ["Q142"]),  # not Franca, the Brazilian city
        ("Lula is the president of Brazil and visited France", ["Q155", "Q142"]),
        ("ele usa e irá ao mercado", []),  # Portuguese verbs are not USA / Iran
    ],
)
def test_countries_in(text, expected):
    assert countries_in(text) == expected


def test_is_about_office():
    assert is_about_office("Macron é presidente")
    assert is_about_office("le Premier ministre a démissionné")
    assert not is_about_office("A Câmara aprovou a reforma tributária")


async def test_claim_without_office_makes_no_request():
    seen: list = []
    conn = WikidataConnector(mock_client(_handler(seen)))
    query = EvidenceQuery(keywords=["reforma", "tributária"], language="pt")
    assert await conn.search_evidence(query) == []
    assert seen == []


async def test_office_claim_brings_leaders_and_positions():
    seen: list = []
    conn = WikidataConnector(mock_client(_handler(seen)))
    query = EvidenceQuery(keywords=["presidente", "ucrania", "macron"], language="pt")
    evidence = await conn.search_evidence(query)
    leaders, positions = evidence
    assert leaders.connector == "kb.wikidata" and leaders.country is Country.GLOBAL
    assert "não oficial" in leaders.publisher
    assert (
        "Chefe de Estado: Volodymyr Zelensky (desde 20/05/2019; sem referência" in leaders.excerpt
    )
    assert leaders.url == "https://www.wikidata.org/wiki/Q212"
    assert leaders.data == {
        "official": False,
        "referenced": False,
        "holders": [
            {
                "role": "head_of_state",
                "person": "Volodymyr Zelensky",
                "person_id": "Q3874799",
                "start": "2019-05-20",
                "referenced": False,
            }
        ],
    }
    assert positions.title == "Emmanuel Macron: cargos ocupados"
    assert positions.excerpt.startswith(
        "Cargos: Presidente da França (desde 14/05/2017, atual); Ministro da Economia "
        "(26/08/2014 a 30/08/2016)"
    )
    assert positions.data["referenced"] is True  # the current office has a reference
    search = parse_qs(urlparse(str(seen[1].url)).query)
    assert search["search"] == ["macron"]  # country and office words are not searched as names
    assert any('wikibase:language "pt,mul,en,fr"' in str(r.url) or "pt%2Cmul" in str(r.url)
               for r in seen)  # fmt: skip


def _evidence(connector: str, referenced: bool) -> Evidence:
    return Evidence(
        connector=connector,
        country=Country.GLOBAL,
        publisher="x",
        title="France: chefe de Estado",
        url="https://www.wikidata.org/wiki/Q142",
        data={"referenced": referenced},
    )


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([_evidence("kb.wikidata", False)], 0.75),  # only an unreferenced public base
        ([_evidence("kb.wikidata", True)], 0.95),  # Wikidata backs it with a reference
        ([_evidence("kb.wikidata", False), _evidence("fr.data_gouv", False)], 0.95),
    ],
)
async def test_confidence_capped_when_only_unofficial_unreferenced(items, expected):
    cited = ", ".join(f'"E{i}"' for i in range(1, len(items) + 1))
    llm = FakeLLMProvider(
        fake_credentials(),
        outputs=[
            '{"language": "pt"}',
            '{"verdict": "VERDADEIRO", "confidence_score": 0.95, "explanation": "Sim [E1].",'
            f' "cited_evidence_ids": [{cited}]}}',
        ],
    )
    service = FactCheckService([])

    async def fixed(analysis):
        return items, [], []

    service.collect_evidence = fixed  # type: ignore[method-assign]
    report = await service.check_text("Macron é presidente da França.", llm)
    assert report.confidence_score == expected
    capped = any(n.startswith("Veredito apoiado só em base pública") for n in report.notes)
    assert capped is (expected == 0.75)
