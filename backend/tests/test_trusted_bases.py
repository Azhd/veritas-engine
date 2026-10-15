"""World Bank, Eurostat, Crossref retractions and Google Fact Check (mocked, no network)."""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import SecretStr

from app.connectors.countries import countries_in, mentions_eu
from app.connectors.fact_checks import GoogleFactCheckConnector
from app.connectors.international import (
    EurostatConnector,
    WorldBankConnector,
    claim_countries,
    indicators_for,
)
from app.connectors.scholarly import CrossrefRetractionsConnector
from app.schemas.evidence import Country, EvidenceQuery
from tests.conftest import json_response, mock_client


def _params(request) -> dict[str, list[str]]:
    return parse_qs(urlparse(str(request.url)).query)


# =============================================================== countries / indicators
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("o desemprego na Alemanha subiu", ["DE"]),
        ("Brazil and France", ["BR", "FR"]),
        ("ele usa e irá ao mercado", []),
    ],
)
def test_countries_in(text, expected):
    assert countries_in(text) == expected


def test_eu_mentions():
    assert mentions_eu("A inflação na União Europeia caiu")
    assert not mentions_eu("A inflação na Europa caiu")  # a continent, not the EU statistics


@pytest.mark.parametrize(
    ("words", "keys"),
    [
        (["desemprego"], ["unemployment"]),
        (["crescimento", "pib"], ["gdp_growth"]),  # growth, not the GDP level
        (["pib"], ["gdp"]),
        (["life expectancy"], ["life_expectancy"]),
        (["vacinas"], []),
    ],
)
def test_indicators_for(words, keys):
    assert [i.key for i in indicators_for(EvidenceQuery(keywords=words))] == keys


def test_claim_countries_fall_back_to_a_single_context_country():
    assert claim_countries(EvidenceQuery(keywords=["desemprego"], countries=["BR"])) == ["BR"]
    assert claim_countries(EvidenceQuery(keywords=["desemprego"], countries=["BR", "FR"])) == []


# =============================================================== World Bank
WB = [
    {"page": 1},
    [
        {"country": {"id": "AR", "value": "Argentina"}, "date": "2025", "value": 7.2,
         "indicator": {"value": "Unemployment, total (% of total labor force)"}},
        {"country": {"id": "AR", "value": "Argentina"}, "date": "2024", "value": 7.9,
         "indicator": {"value": "Unemployment, total (% of total labor force)"}},
        {"country": {"id": "AR", "value": "Argentina"}, "date": "2023", "value": None,
         "indicator": {"value": "Unemployment, total (% of total labor force)"}},
    ],
]  # fmt: skip


async def test_world_bank_series():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(WB)

    conn = WorldBankConnector(mock_client(handler))
    (item,) = await conn.search_evidence(
        EvidenceQuery(keywords=["desemprego", "argentina"], language="pt")
    )
    assert "/country/AR/indicator/SL.UEM.TOTL.ZS" in str(seen[0].url)
    assert item.excerpt == "2025: 7,2%; 2024: 7,9%"  # empty years skipped
    assert item.published_at == date(2025, 12, 31) and item.country is Country.GLOBAL
    assert item.identifiers == {"wb_indicator": "SL.UEM.TOTL.ZS", "country": "AR"}


async def test_world_bank_needs_an_indicator_and_a_country():
    conn = WorldBankConnector(mock_client(lambda r: pytest.fail("no request expected")))
    assert await conn.search_evidence(EvidenceQuery(keywords=["argentina", "futebol"])) == []
    assert await conn.search_evidence(EvidenceQuery(keywords=["desemprego"])) == []


# =============================================================== Eurostat
JSONSTAT = {
    "label": "Unemployment by sex and age - annual data",
    "value": {"0": 3.0, "1": 3.4, "2": 3.7},
    "dimension": {"time": {"category": {"index": {"2023": 0, "2024": 1, "2025": 2}}}},
}


async def test_eurostat_country_and_eu_aggregate():
    seen = []

    def handler(request):
        seen.append(_params(request))
        return json_response(JSONSTAT)

    conn = EurostatConnector(mock_client(handler))
    query = EvidenceQuery(keywords=["chômage", "allemagne", "union européenne"], language="fr")
    first, second = await conn.search_evidence(query)
    assert [p["geo"] for p in seen] == [["DE"], ["EU27_2020"]]
    assert seen[0]["unit"] == ["PC_ACT"] and seen[0]["age"] == ["Y15-74"]
    assert first.excerpt == "2025: 3,7%; 2024: 3,4%; 2023: 3,0%"  # newest first
    assert first.country is Country.EU and "União Europeia (27)" in second.title


async def test_eurostat_ignores_countries_outside_the_eu():
    conn = EurostatConnector(mock_client(lambda r: pytest.fail("no request expected")))
    assert await conn.search_evidence(EvidenceQuery(keywords=["desemprego", "brasil"])) == []


# =============================================================== Crossref
NOTICES = {
    "message": {
        "items": [
            {
                "DOI": "10.1016/s0140-6736(10)60175-4",
                "title": ["Retraction—Ileal-lymphoid-nodular hyperplasia ... in children"],
                "container-title": ["The Lancet"],
                "URL": "https://doi.org/10.1016/s0140-6736(10)60175-4",
                "update-to": [
                    {"DOI": "10.1016/s0140-6736(97)11096-0", "type": "retraction",
                     "source": "retraction-watch",
                     "updated": {"date-parts": [[2010, 2, 6]]}},
                ],
            },
            {"DOI": "10.1/x", "title": ["Not an update"], "update-to": []},
        ]
    }
}  # fmt: skip


def _crossref(original_title: str, seen: list):
    def handler(request):
        seen.append(request)
        if request.url.path.startswith("/works/"):  # title of the retracted article
            return json_response({"message": {"title": [original_title]}})
        return json_response(NOTICES)

    return mock_client(handler)


async def test_crossref_retraction_notices():
    seen: list = []
    conn = CrossrefRetractionsConnector(
        _crossref("MMR vaccine and autism in children: an early report", seen)
    )
    query = EvidenceQuery(
        keywords=["estudo", "vacinas", "autismo"], keywords_en=["vaccines", "autism"]
    )
    (item,) = await conn.search_evidence(query)
    search = _params(seen[0])
    assert search["filter"] == ["update-type:retraction"]
    assert search["query.bibliographic"] == ["vaccines autism"]
    # the notice title said nothing: the retracted article's own title was looked up
    assert seen[1].url.path == "/works/10.1016/s0140-6736(97)11096-0"
    assert item.title == "Artigo retratado: MMR vaccine and autism in children: an early report"
    assert item.excerpt == (
        "Aviso de retratação na revista The Lancet em 06/02/2010: o artigo DOI "
        "10.1016/s0140-6736(97)11096-0 foi oficialmente marcado (fonte: Retraction Watch). "
        "Um estudo retratado não sustenta nenhuma alegação."
    )
    assert item.identifiers["retracted_doi"] == "10.1016/s0140-6736(97)11096-0"
    assert item.data["retracted"] is True


async def test_crossref_drops_retractions_about_another_subject():
    seen: list = []
    conn = CrossrefRetractionsConnector(_crossref("COVID-19 vaccine hesitancy in Germany", seen))
    query = EvidenceQuery(keywords=["estudo"], keywords_en=["study", "vaccines", "autism"])
    assert await conn.search_evidence(query) == []  # only "vaccine" matches, "study" is ignored


async def test_crossref_only_for_claims_citing_research():
    conn = CrossrefRetractionsConnector(mock_client(lambda r: pytest.fail("no request")))
    assert await conn.search_evidence(EvidenceQuery(keywords_en=["vaccines", "autism"])) == []


# =============================================================== Google Fact Check
CLAIMS = {
    "claims": [
        {
            "text": "Vacinas causam autismo",
            "claimant": "Post no Facebook",
            "claimDate": "2024-03-01T00:00:00Z",
            "claimReview": [
                {
                    "publisher": {"name": "Agência Lupa", "site": "lupa.uol.com.br"},
                    "url": "https://lupa.uol.com.br/jornalismo/2024/03/02/vacinas-autismo",
                    "title": "É falso que vacinas causam autismo",
                    "reviewDate": "2024-03-02T00:00:00Z",
                    "textualRating": "Falso",
                    "languageCode": "pt",
                }
            ],
        }
    ]
}


def test_fact_check_is_disabled_without_a_key():
    assert "VERITAS_GOOGLE_FACTCHECK_API_KEY" in GoogleFactCheckConnector().disabled_reason
    assert GoogleFactCheckConnector(api_key=SecretStr("k")).enabled


async def test_fact_check_key_goes_in_a_header_not_the_url():
    seen = []

    def handler(request):
        seen.append(request)
        return json_response(CLAIMS)

    conn = GoogleFactCheckConnector(mock_client(handler), api_key=SecretStr("secret-key"))
    (item,) = await conn.search_evidence(
        EvidenceQuery(keywords=["vacinas", "autismo"], language="pt")
    )
    request = seen[0]
    assert request.headers["X-Goog-Api-Key"] == "secret-key"
    assert "secret-key" not in str(request.url)
    assert _params(request)["languageCode"] == ["pt"]
    assert item.venue == "Agência Lupa" and item.data["rating"] == "Falso"
    assert item.excerpt == (
        "Checagem de Agência Lupa: classificação “Falso”. Afirmação checada: "
        "“Vacinas causam autismo” (autor: Post no Facebook)."
    )
    assert item.published_at == date(2024, 3, 2)
