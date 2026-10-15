"""Connector deadlines and the live health check script (no network here)."""

from __future__ import annotations

import asyncio

import pytest

from app.connectors.base import BaseGovConnector
from app.connectors.healthcheck import PROBES, Result, check, probe_query, report
from app.connectors.registry import CONNECTOR_CLASSES
from app.connectors.web_archive import WaybackConnector
from app.core.errors import ConnectorUnavailableError
from app.schemas.evidence import Country, Domain, EvidenceQuery


class _Slow(BaseGovConnector):
    source_id = "test.slow"
    country = Country.GLOBAL
    publisher = "test"
    base_url = "https://example.invalid"
    domains = frozenset({Domain.GEOPOLITICS})

    async def search_evidence(self, query: EvidenceQuery):
        await asyncio.sleep(5)
        return []


async def test_slow_source_is_given_up_at_its_deadline():
    connector = _Slow(timeout_seconds=0.05)
    assert connector.deadline_seconds == pytest.approx(0.1)
    with pytest.raises(ConnectorUnavailableError, match="sem resposta"):
        await connector.search_within_deadline(EvidenceQuery())


def test_bulk_datasets_keep_their_longer_budget():
    connector = _Slow(timeout_seconds=8)
    connector.dataset_timeout_seconds = 30  # type: ignore[attr-defined]
    assert connector.deadline_seconds == 38


def test_wayback_retries_at_most_once():
    assert WaybackConnector(max_retries=3).max_retries == 1


def test_every_registered_source_has_a_probe_claim():
    assert {cls.source_id for cls in CONNECTOR_CLASSES} == set(PROBES)


@pytest.mark.parametrize("source_id", sorted(PROBES))
def test_probe_queries_are_searchable(source_id):
    query = probe_query(source_id)
    assert query.keywords or query.keywords_en or query.legal_references or query.urls


async def test_check_reports_disabled_and_failures():
    class _Broken(_Slow):
        source_id = "kb.wikidata"

        async def search_evidence(self, query):
            raise ConnectorUnavailableError("down")

    result = await check(_Broken())
    assert result.status == "FAIL" and "down" in result.detail
    text = report([result, Result("br.ibge", "OK", 1.0, 2, "IPCA")])
    assert "OK: 1 · EMPTY: 0 · FAIL: 1 · DISABLED: 0" in text
