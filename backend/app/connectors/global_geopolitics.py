"""Geopolitics, conflicts and humanitarian crises.

* ReliefWeb API v2 (UN OCHA) - humanitarian situation reports. API v1 was decommissioned and v2
  requires an *approved* ``appname`` (``VERITAS_RELIEFWEB_APPNAME``); without it the connector is
  registered but disabled.
* GDELT Doc 2.0 API - worldwide news monitoring. These are *media* reports (secondary sources):
  useful to date events and statements, flagged as such in ``data.source_type``.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

from app.connectors.base import BaseGovConnector, truncate
from app.core.config import Settings
from app.core.errors import ConnectorHTTPError, ConnectorUnavailableError
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery


def _iso_date(value: Any) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


class ReliefWebConnector(BaseGovConnector):
    source_id = "geo.reliefweb"
    country = Country.GLOBAL
    publisher = "ReliefWeb - UN Office for the Coordination of Humanitarian Affairs (OCHA)"
    base_url = "https://api.reliefweb.int/v2"
    domains = frozenset({Domain.GEOPOLITICS})

    def __init__(
        self, client: httpx.AsyncClient | None = None, *, appname: str | None = None, **kw: Any
    ) -> None:
        super().__init__(client, **kw)
        self.appname = (appname or "").strip() or None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> ReliefWebConnector:
        return cls(client, appname=settings.reliefweb_appname, **common)

    @property
    def disabled_reason(self) -> str | None:
        if not self.appname:
            return "requires an approved VERITAS_RELIEFWEB_APPNAME (ReliefWeb API v2)"
        return None

    async def search_reports(self, text: str, *, limit: int = 5) -> list[dict[str, Any]]:
        payload = await self._get_json(
            "/reports",
            {
                "appname": self.appname,
                "query[value]": text,
                "limit": limit,
                "sort[]": "date.created:desc",
                "fields[include][]": [
                    "title",
                    "url_alias",
                    "date.created",
                    "source.name",
                    "country.name",
                    "body",
                ],
            },
        )
        return payload.get("data", []) if isinstance(payload, dict) else []

    async def get_report(self, report_id: str) -> dict[str, Any]:
        payload = await self._get_json(f"/reports/{report_id}", {"appname": self.appname})
        data = payload.get("data", []) if isinstance(payload, dict) else []
        return data[0].get("fields", {}) if data else {}

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        text = query.text_en
        if not text:
            return []
        evidence = []
        for item in await self.search_reports(text, limit=query.max_results):
            fields = item.get("fields", {})
            sources = [s.get("name") for s in fields.get("source", []) if s.get("name")]
            countries = [c.get("name") for c in fields.get("country", []) if c.get("name")]
            evidence.append(
                self._evidence(
                    title=fields.get("title") or "ReliefWeb report",
                    url=fields.get("url_alias") or fields.get("url") or item.get("href", ""),
                    excerpt=truncate(fields.get("body") or ", ".join(countries)),
                    authors=sources,
                    venue="ReliefWeb (UN OCHA)",
                    published_at=_iso_date((fields.get("date") or {}).get("created")),
                    identifiers={"reliefweb_id": str(item.get("id", ""))},
                    data={"countries": countries, "source_type": "humanitarian_report"},
                )
            )
        return evidence


class GdeltConnector(BaseGovConnector):
    source_id = "geo.gdelt"
    country = Country.GLOBAL
    publisher = "The GDELT Project"
    base_url = "https://api.gdeltproject.org/api/v2/doc"
    domains = frozenset({Domain.GEOPOLITICS})

    #: GDELT allows ~1 request / 5 s; keep the default lookback modest to stay fast.
    timespan = "1week"

    #: Minimum spacing between real calls (GDELT policy) and back-off after an HTTP 429.
    min_interval_seconds = 5.5
    rate_limited_pause_seconds = 60.0

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        **kw: Any,
    ) -> None:
        super().__init__(client, **kw)
        # Retrying within seconds would break GDELT's 1 request / 5 s policy (HTTP 429). It is a
        # best-effort media source: a slow answer is reported as a connector failure instead.
        self.max_retries = 0
        self._clock = clock
        self._next_call_at = 0.0

    async def search_articles(self, text: str, *, limit: int = 5) -> list[dict[str, Any]]:
        terms = _gdelt_query(text)
        if not terms:
            return []
        params = {
            "query": terms,
            "mode": "artlist",
            "format": "json",
            "maxrecords": limit,
            "sort": "datedesc",
            "timespan": self.timespan,
        }
        cached = self.cache.get(self._cache_key("GET", self._url("/doc"), params))
        if cached is None:
            # Respect GDELT's rate limit locally instead of being blocked (HTTP 429).
            now = self._clock()
            if now < self._next_call_at:
                wait = int(self._next_call_at - now) + 1
                raise ConnectorUnavailableError(
                    f"{self.source_id}: limite de consultas do GDELT; tente em ~{wait}s"
                )
            self._next_call_at = now + self.min_interval_seconds
        try:
            raw = await self._request("/doc", params, kind="text")
        except ConnectorUnavailableError:
            self._next_call_at = self._clock() + self.rate_limited_pause_seconds
            raise
        # On rate limiting or invalid queries GDELT answers HTTP 200 with a plain-text message.
        stripped = (raw or "").strip()
        if not stripped:
            return []
        if not stripped.startswith("{"):
            raise ConnectorUnavailableError(f"{self.source_id}: {truncate(stripped, 160)}")
        try:
            import json

            payload = json.loads(stripped)
        except ValueError as exc:
            raise ConnectorHTTPError(f"{self.source_id}: invalid JSON response", 200) from exc
        return payload.get("articles", []) if isinstance(payload, dict) else []

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        text = query.text_en
        if not text:
            return []
        return [
            self._evidence(
                title=(article.get("title") or "").strip() or article.get("url", ""),
                url=article.get("url", ""),
                excerpt=(
                    f"Reportagem de {article.get('domain')} "
                    f"({article.get('sourcecountry') or 'país n/d'}, {article.get('language')})."
                ),
                venue=article.get("domain"),
                published_at=_gdelt_date(article.get("seendate")),
                data={
                    "source_type": "news_media",
                    "source_country": article.get("sourcecountry"),
                    "language": article.get("language"),
                },
            )
            for article in await self.search_articles(text, limit=query.max_results)
            if article.get("url")
        ]


def _gdelt_query(text: str) -> str:
    """GDELT rejects words shorter than 3 chars and most punctuation; terms are AND-ed."""
    words = [w for w in re.findall(r"[\w\-]+", text) if len(w) > 2]
    return " ".join(words[:4])


def _gdelt_date(value: str | None) -> date | None:
    if value and len(value) >= 8 and value[:8].isdigit():
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        except ValueError:
            return None
    return None
