"""ReliefWeb (UN OCHA) and GDELT connectors - HTTP fully mocked."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.connectors.global_geopolitics import GdeltConnector, ReliefWebConnector, _gdelt_query
from app.core.errors import ConnectorHTTPError, ConnectorUnavailableError
from app.schemas.evidence import Country, EvidenceQuery
from tests.conftest import SleepRecorder, json_response, mock_client

RELIEFWEB_REPORTS = {
    "data": [
        {
            "id": "4123456",
            "href": "https://api.reliefweb.int/v2/reports/4123456",
            "fields": {
                "title": "Sudan: Humanitarian Situation Report No. 12",
                "url_alias": "https://reliefweb.int/report/sudan/sudan-situation-report-12",
                "date": {"created": "2026-10-01T10:00:00+00:00"},
                "source": [{"name": "UN Office for the Coordination of Humanitarian Affairs"}],
                "country": [{"name": "Sudan"}],
                "body": "More than 10 million people are internally displaced...",
            },
        }
    ]
}
GDELT_ARTICLES = {
    "articles": [
        {
            "url": "https://example-news.org/ukraine-ceasefire-talks",
            "title": "  Ceasefire talks resume in Istanbul ",
            "seendate": "20261010T064500Z",
            "domain": "example-news.org",
            "language": "English",
            "sourcecountry": "Turkey",
        },
        {"url": "", "title": "no url, skipped"},
    ]
}


class TestReliefWeb:
    def test_disabled_without_appname(self):
        conn = ReliefWebConnector(mock_client(lambda r: httpx.Response(500)))
        assert conn.enabled is False
        assert "RELIEFWEB_APPNAME" in conn.disabled_reason

    async def test_reports_mapping_and_appname(self):
        seen: list[httpx.URL] = []

        def handler(request):
            seen.append(request.url)
            return json_response(RELIEFWEB_REPORTS)

        conn = ReliefWebConnector(
            mock_client(handler), appname="veritas-approved", sleep=SleepRecorder()
        )
        assert conn.enabled
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["sudão deslocados"], keywords_en=["sudan displaced"])
        )
        url = seen[0]
        assert url.path == "/v2/reports"
        assert url.params["appname"] == "veritas-approved"
        assert url.params["query[value]"] == "sudan displaced"
        assert "body" in url.params.get_list("fields[include][]")
        item = evidence[0]
        assert item.country is Country.GLOBAL
        assert item.url == "https://reliefweb.int/report/sudan/sudan-situation-report-12"
        assert item.published_at == date(2026, 10, 1)
        assert item.authors == ["UN Office for the Coordination of Humanitarian Affairs"]
        assert item.data["countries"] == ["Sudan"]
        assert item.data["source_type"] == "humanitarian_report"

    async def test_unapproved_appname_is_a_clear_error(self):
        conn = ReliefWebConnector(
            mock_client(lambda r: json_response({"error": {}}, status=403)),
            appname="not-approved",
            sleep=SleepRecorder(),
        )
        with pytest.raises(ConnectorHTTPError) as exc_info:
            await conn.search_evidence(EvidenceQuery(keywords_en=["gaza"]))
        assert exc_info.value.status == 403


class TestGdelt:
    async def test_articles_are_flagged_as_media(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return httpx.Response(200, text=__import__("json").dumps(GDELT_ARTICLES))

        conn = GdeltConnector(mock_client(handler), sleep=SleepRecorder())
        evidence = await conn.search_evidence(EvidenceQuery(keywords_en=["ukraine ceasefire"]))
        params = seen[0].params
        assert params["query"] == "ukraine ceasefire"
        assert params["mode"] == "artlist" and params["format"] == "json"
        assert params["sort"] == "datedesc"
        assert len(evidence) == 1
        item = evidence[0]
        assert item.title == "Ceasefire talks resume in Istanbul"
        assert item.venue == "example-news.org"
        assert item.published_at == date(2026, 10, 10)
        assert item.data["source_type"] == "news_media"

    async def test_plain_text_rate_limit_message_is_unavailable(self):
        conn = GdeltConnector(
            mock_client(
                lambda r: httpx.Response(
                    200, text="Please limit requests to one every 5 seconds or contact us."
                )
            ),
            sleep=SleepRecorder(),
        )
        with pytest.raises(ConnectorUnavailableError, match="limit requests"):
            await conn.search_evidence(EvidenceQuery(keywords_en=["gaza ceasefire"]))

    async def test_empty_body_means_no_results(self):
        conn = GdeltConnector(mock_client(lambda r: httpx.Response(200, text="")))
        assert await conn.search_evidence(EvidenceQuery(keywords_en=["gaza"])) == []

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("ukraine ceasefire", "ukraine ceasefire"),
            ("EU & UN talks: Gaza!", "talks Gaza"),
            ("a b", ""),
            ("one two three four five", "one two three four"),
        ],
    )
    def test_query_sanitizing(self, text, expected):
        assert _gdelt_query(text) == expected
