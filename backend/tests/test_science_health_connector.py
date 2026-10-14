"""PubMed (NCBI E-utilities) and WHO GHO connectors - HTTP fully mocked."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.connectors.science_health import (
    PubMedConnector,
    WhoGhoConnector,
    parse_abstracts,
    parse_pubmed_date,
)
from app.schemas.evidence import Country, Domain, EvidenceQuery
from tests.conftest import SleepRecorder, json_response, mock_client

ESEARCH = {"esearchresult": {"count": "2", "idlist": ["35726131", "11111111"]}}
ESUMMARY = {
    "result": {
        "uids": ["35726131", "11111111"],
        "35726131": {
            "uid": "35726131",
            "pubdate": "2022 Jun 21",
            "source": "Cochrane Database Syst Rev",
            "fulljournalname": "The Cochrane database of systematic reviews",
            "title": "Ivermectin for preventing and treating COVID-19.",
            "authors": [{"name": f"Author {i}"} for i in range(10)],
            "pubtype": ["Journal Article", "Meta-Analysis", "Systematic Review"],
            "articleids": [
                {"idtype": "pubmed", "value": "35726131"},
                {"idtype": "doi", "value": "10.1002/14651858.CD015017.pub3"},
                {"idtype": "pmc", "value": "PMC9215332"},
            ],
        },
        "11111111": {
            "uid": "11111111",
            "pubdate": "1998",
            "source": "Lancet",
            "title": "Retracted study",
            "authors": [{"name": "Wakefield AJ"}],
            "pubtype": ["Journal Article", "Retracted Publication"],
            "articleids": [],
        },
    }
}
EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation><PMID>35726131</PMID><Article><Abstract>
    <AbstractText Label="BACKGROUND">Ivermectin is an antiparasitic agent.</AbstractText>
    <AbstractText Label="AUTHORS' CONCLUSIONS">Evidence does <i>not</i> support its use.
    </AbstractText>
  </Abstract></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


def _pubmed(handler, **kw) -> PubMedConnector:
    return PubMedConnector(mock_client(handler), sleep=SleepRecorder(), **kw)


class TestPubMed:
    async def test_full_flow_maps_unified_evidence(self):
        seen: list[httpx.URL] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.url)
            path = request.url.path
            if path.endswith("esearch.fcgi"):
                return json_response(ESEARCH)
            if path.endswith("esummary.fcgi"):
                return json_response(ESUMMARY)
            if path.endswith("efetch.fcgi"):
                return httpx.Response(200, text=EFETCH_XML)
            return httpx.Response(404)

        conn = _pubmed(handler, email="dev@example.org")
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["ivermectina covid"], keywords_en=["ivermectin covid-19"])
        )

        search = seen[0]
        assert search.params["term"] == "ivermectin covid-19"  # English terms preferred
        assert search.params["db"] == "pubmed"
        assert search.params["email"] == "dev@example.org"
        assert search.params["tool"] == "veritas-engine"
        assert seen[1].params["id"] == "35726131,11111111"

        first = evidence[0]
        assert first.country is Country.GLOBAL
        assert first.url == "https://pubmed.ncbi.nlm.nih.gov/35726131/"
        assert first.identifiers == {
            "pmid": "35726131",
            "doi": "10.1002/14651858.CD015017.pub3",
            "pmcid": "PMC9215332",
        }
        assert first.venue == "The Cochrane database of systematic reviews"
        assert first.published_at == date(2022, 6, 21)
        assert len(first.authors) == 9 and first.authors[-1] == "et al."
        assert "AUTHORS' CONCLUSIONS: Evidence does not support its use." in first.excerpt
        assert first.data["high_level_evidence"] is True

        retracted = evidence[1]
        assert retracted.data["retracted"] is True
        assert retracted.data["high_level_evidence"] is False

    async def test_api_key_is_sent_when_configured(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return json_response({"esearchresult": {"idlist": []}})

        conn = _pubmed(handler, api_key=SecretStr("ncbi-123"))
        assert await conn.search_evidence(EvidenceQuery(keywords_en=["measles"])) == []
        assert seen[0].params["api_key"] == "ncbi-123"
        assert len(seen) == 1  # no summary/abstract calls without hits

    async def test_abstract_failure_keeps_metadata(self):
        def handler(request):
            path = request.url.path
            if path.endswith("esearch.fcgi"):
                return json_response(ESEARCH)
            if path.endswith("esummary.fcgi"):
                return json_response(ESUMMARY)
            return httpx.Response(400)

        evidence = await _pubmed(handler).search_evidence(EvidenceQuery(keywords_en=["x y"]))
        assert len(evidence) == 2
        assert "Meta-Analysis" in evidence[0].excerpt  # falls back to publication types

    async def test_no_terms_no_calls(self):
        conn = _pubmed(lambda r: (_ for _ in ()).throw(AssertionError("no call expected")))
        assert await conn.search_evidence(EvidenceQuery()) == []

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2022 Jun 21", date(2022, 6, 21)),
            ("2021 Jul", date(2021, 7, 1)),
            ("2019", date(2019, 1, 1)),
            ("2020 Feb 30", date(2020, 2, 1)),
            ("", None),
            ("unknown", None),
        ],
    )
    def test_parse_pubmed_date(self, raw, expected):
        assert parse_pubmed_date(raw) == expected

    def test_parse_abstracts_rejects_entity_expansion(self):
        bomb = (
            '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;">]><PubmedArticleSet>&lol2;</PubmedArticleSet>'
        )
        with pytest.raises(Exception, match=r"(?i)entit"):
            parse_abstracts(bomb)

    def test_domain_metadata(self):
        assert PubMedConnector.domains == {Domain.HEALTH_SCIENCE}


WHO_INDICATORS = {
    "value": [
        {"IndicatorCode": "WHOSIS_000001", "IndicatorName": "Life expectancy at birth (years)"},
    ]
}
WHO_VALUES = {
    "value": [
        {"TimeDim": 2023, "Dim1": "SEX_MLE", "Value": "72.1", "NumericValue": 72.1},
        {"TimeDim": 2023, "Dim1": "SEX_BTSX", "Value": "75.9 [75.2-76.5]", "NumericValue": 75.9},
        {"TimeDim": 2022, "Dim1": "SEX_BTSX", "Value": "75.3", "NumericValue": 75.3},
    ]
}


class TestWhoGho:
    async def test_indicator_search_and_country_values(self):
        seen: list[httpx.URL] = []

        def handler(request):
            seen.append(request.url)
            if request.url.path == "/api/Indicator":
                return json_response(WHO_INDICATORS)
            if request.url.path == "/api/WHOSIS_000001":
                return json_response(WHO_VALUES)
            return httpx.Response(404)

        conn = WhoGhoConnector(mock_client(handler), sleep=SleepRecorder())
        evidence = await conn.search_evidence(
            EvidenceQuery(topics_en=["Life Expectancy"], countries=["BR"])
        )
        assert seen[0].params["$filter"] == "contains(tolower(IndicatorName),'life expectancy')"
        assert seen[1].params["$filter"] == "SpatialDim eq 'BRA'"
        item = evidence[0]
        assert item.title == "Life expectancy at birth (years) - BRA"
        assert item.excerpt == "2023: 75.9 [75.2-76.5]; 2022: 75.3"  # both sexes, one per year
        assert item.identifiers == {"who_indicator": "WHOSIS_000001", "spatial": "BRA"}
        assert item.published_at == date(2023, 1, 1)

    async def test_global_when_no_supported_country(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            if request.url.path == "/api/Indicator":
                return json_response(WHO_INDICATORS)
            return json_response({"value": []})

        conn = WhoGhoConnector(mock_client(handler), sleep=SleepRecorder())
        assert await conn.search_evidence(EvidenceQuery(keywords_en=["life expectancy"])) == []
        assert seen[1].params["$filter"] == "SpatialDim eq 'GLOBAL'"

    async def test_odata_injection_is_neutralized(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return json_response({"value": []})

        conn = WhoGhoConnector(mock_client(handler), sleep=SleepRecorder())
        await conn.find_indicators("x') or true or contains(IndicatorName,'")
        assert "'" not in seen[0].params["$filter"].split("'")[1]
        assert seen[0].params["$filter"].count("'") == 2
