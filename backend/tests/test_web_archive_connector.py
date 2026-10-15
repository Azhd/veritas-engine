"""Wayback Machine connector: archive history, edits, title changes and removals (mocked)."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from app.connectors.web_archive import (
    WaybackConnector,
    extract_title,
    normalize_url,
)
from app.schemas.evidence import Country, EvidenceQuery
from tests.conftest import SleepRecorder, json_response, mock_client

URL = "https://news.example.com/2026/politica/materia"
HEADER = ["timestamp", "original", "statuscode", "digest"]


def _cdx(*rows):
    return [HEADER, *[list(r) for r in rows]]


def _connector(cdx_rows, snapshots=None, availability=None, seen=None, latest_rows=None):
    snapshots = snapshots or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request.url)
        if request.url.path == "/cdx/search/cdx":
            if request.url.params.get("fastLatest") == "true":
                rows = latest_rows if latest_rows is not None else cdx_rows[:1] + cdx_rows[-1:]
                return json_response(rows if len(rows) > 1 else [])
            return json_response(cdx_rows)
        if request.url.host == "archive.org" and request.url.path == "/wayback/available":
            return json_response(availability or {"archived_snapshots": {}})
        for timestamp, body in snapshots.items():
            if f"/web/{timestamp}id_/" in str(request.url):
                return httpx.Response(200, text=body)
        return httpx.Response(404)

    return WaybackConnector(mock_client(handler), sleep=SleepRecorder())


async def test_edited_article_with_title_change():
    seen: list[httpx.URL] = []
    conn = _connector(
        _cdx(
            ("20260301120000", URL, "200", "AAA"),
            ("20260302080000", URL, "200", "BBB"),
            ("20260310090000", URL, "200", "CCC"),
        ),
        snapshots={
            "20260301120000": "<html><title>Ministro admite fraude</title></html>",
            "20260310090000": "<html><TITLE> Ministro nega fraude &amp; critica  </TITLE></html>",
        },
        seen=seen,
    )
    evidence = await conn.search_evidence(EvidenceQuery(urls=[URL]))
    cdx_params = seen[0].params
    assert cdx_params["url"] == URL
    assert cdx_params["collapse"] == "digest"
    assert cdx_params["output"] == "json"

    item = evidence[0]
    assert item.country is Country.GLOBAL
    assert item.url == f"https://web.archive.org/web/20260301120000/{URL}"
    assert item.published_at == date(2026, 3, 1)
    assert item.identifiers == {
        "snapshot_first": "20260301120000",
        "snapshot_last": "20260310090000",
    }
    assert item.data["distinct_versions"] == 3
    assert item.data["content_changed"] is True
    assert item.data["title_changed"] is True
    assert item.data["first_title"] == "Ministro admite fraude"
    assert item.data["last_title"] == "Ministro nega fraude & critica"
    assert item.data["removed_or_redirected"] is False
    assert "Primeira captura em 01/03/2026" in item.excerpt
    assert "3 versões distintas" in item.excerpt
    assert 'Título mudou de "Ministro admite fraude"' in item.excerpt


async def test_deleted_page_is_detected():
    conn = _connector(
        _cdx(
            ("20250101000000", URL, "200", "AAA"),
            ("20250201000000", URL, "404", "ZZZ"),
        ),
        snapshots={"20250101000000": "<title>Original</title>"},
    )
    item = (await conn.search_evidence(EvidenceQuery(urls=[URL])))[0]
    assert item.data["removed_or_redirected"] is True
    assert item.data["last_status"] == "404"
    assert item.data["content_changed"] is False
    assert "remoção ou redirecionamento" in item.excerpt


async def test_unchanged_page():
    conn = _connector(_cdx(("20240101000000", URL, "200", "AAA")))
    item = (await conn.search_evidence(EvidenceQuery(urls=[URL])))[0]
    assert item.data["content_changed"] is False
    assert item.data["title_changed"] is False
    assert "Conteúdo idêntico" in item.excerpt


async def test_falls_back_to_availability_api():
    conn = _connector(
        [],
        availability={
            "archived_snapshots": {
                "closest": {
                    "available": True,
                    "timestamp": "20261001000000",
                    "status": "200",
                    "url": f"http://web.archive.org/web/20261001000000/{URL}",
                }
            }
        },
    )
    item = (await conn.search_evidence(EvidenceQuery(urls=[URL])))[0]
    assert item.identifiers["snapshot_first"] == "20261001000000"


async def test_never_archived_url():
    conn = _connector([], availability={"archived_snapshots": {}})
    item = (await conn.search_evidence(EvidenceQuery(urls=["example.org/novo"])))[0]
    assert item.data == {"archived": False}
    assert item.title.startswith("Sem registro no Internet Archive")


async def test_snapshot_fetch_failure_does_not_drop_history():
    conn = _connector(
        _cdx(("20250101000000", URL, "200", "A"), ("20250102000000", URL, "200", "B")),
        snapshots={},  # raw snapshots answer 404
    )
    item = (await conn.search_evidence(EvidenceQuery(urls=[URL])))[0]
    assert item.data["content_changed"] is True
    assert item.data["title_changed"] is False


async def test_limits_and_deduplicates_urls():
    seen: list[httpx.URL] = []
    conn = _connector(_cdx(("20240101000000", URL, "200", "A")), seen=seen)
    urls = [URL, URL, "a.com/1", "b.com/2", "c.com/3", "not a url"]
    evidence = await conn.search_evidence(EvidenceQuery(urls=urls))
    assert len(evidence) == 3
    cdx = [u for u in seen if u.path == "/cdx/search/cdx"]
    assert len([u for u in cdx if u.params.get("collapse") == "digest"]) == 3
    assert len([u for u in cdx if u.params.get("fastLatest") == "true"]) == 3


async def test_latest_capture_beyond_oldest_versions_is_used():
    # The oldest-first CDX page stops early; the fastLatest call reveals the page is gone today.
    conn = _connector(
        _cdx(("20200101000000", URL, "200", "A"), ("20200201000000", URL, "200", "B")),
        latest_rows=_cdx(("20261012000000", URL, "404", "Z")),
        snapshots={"20200101000000": "<title>T1</title>", "20200201000000": "<title>T1</title>"},
    )
    item = (await conn.search_evidence(EvidenceQuery(urls=[URL])))[0]
    assert item.identifiers["snapshot_last"] == "20261012000000"
    assert item.data["last_status"] == "404"
    assert item.data["removed_or_redirected"] is True


async def test_latest_capture_failure_keeps_history():
    def handler(request):
        if request.url.params.get("fastLatest") == "true":
            return httpx.Response(503)
        return json_response(_cdx(("20240101000000", URL, "200", "A")))

    conn = WaybackConnector(mock_client(handler), max_retries=0, sleep=SleepRecorder())
    item = (await conn.search_evidence(EvidenceQuery(urls=[URL])))[0]
    assert item.identifiers["snapshot_first"] == "20240101000000"


async def test_no_urls_no_calls():
    conn = WaybackConnector(mock_client(lambda r: (_ for _ in ()).throw(AssertionError())))
    assert await conn.search_evidence(EvidenceQuery(keywords=["x"])) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://g1.globo.com/x", "https://g1.globo.com/x"),
        ("www.gov.br/saude.", "http://www.gov.br/saude"),
        ("(http://a.com/b)", "http://a.com/b"),
        ("localhost", None),
        ("", None),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_extract_title():
    assert extract_title("<head><title>\n Olá &eacute; mundo </title></head>") == "Olá é mundo"
    assert extract_title("<html>sem título</html>") is None
