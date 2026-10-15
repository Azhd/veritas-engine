"""Web memory: Internet Archive / Wayback Machine.

For each suspicious URL the connector answers, with archived evidence:
    * was it archived, and when was the first (original) capture?
    * how many *distinct* versions exist (CDX ``collapse=digest``) -> content was edited later;
    * did the ``<title>`` change between the first and the latest capture?
    * does the latest capture show a removal (HTTP 404/410) or a redirect away?

APIs: Availability API (``archive.org/wayback/available``) and CDX server
(``web.archive.org/cdx/search/cdx``). Both are free and keyless.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse

from app.connectors.base import BaseGovConnector
from app.core.errors import ConnectorError
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

WAYBACK_SNAPSHOT_URL = "https://web.archive.org/web/{timestamp}/{url}"
WAYBACK_RAW_URL = "https://web.archive.org/web/{timestamp}id_/{url}"
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_REMOVED_STATUS = frozenset({"404", "410", "451"})
_REDIRECT_STATUS = frozenset({"301", "302", "303", "307", "308"})
#: Maximum CDX rows inspected per URL (news articles rarely have more distinct versions).
CDX_LIMIT = 50


@dataclass(frozen=True, slots=True)
class Capture:
    timestamp: str
    original: str
    status: str
    digest: str

    @property
    def day(self) -> date | None:
        try:
            return date(int(self.timestamp[:4]), int(self.timestamp[4:6]), int(self.timestamp[6:8]))
        except (ValueError, IndexError):
            return None

    @property
    def snapshot_url(self) -> str:
        return WAYBACK_SNAPSHOT_URL.format(timestamp=self.timestamp, url=self.original)


@dataclass(frozen=True, slots=True)
class ArchiveHistory:
    url: str
    captures: list[Capture]
    first_title: str | None = None
    last_title: str | None = None
    #: True when the page has more distinct versions than ``CDX_LIMIT`` (counts are a minimum).
    truncated: bool = False

    @property
    def first(self) -> Capture | None:
        return self.captures[0] if self.captures else None

    @property
    def last(self) -> Capture | None:
        return self.captures[-1] if self.captures else None

    @property
    def ok_captures(self) -> list[Capture]:
        return [c for c in self.captures if c.status == "200"]

    @property
    def distinct_versions(self) -> int:
        return len({c.digest for c in self.ok_captures})

    @property
    def content_changed(self) -> bool:
        return self.distinct_versions > 1

    @property
    def title_changed(self) -> bool:
        return bool(self.first_title and self.last_title and self.first_title != self.last_title)

    @property
    def removed(self) -> bool:
        """Was available (200) at some point and the latest capture shows removal/redirect."""
        last = self.last
        return bool(
            last
            and self.ok_captures
            and last.status in (_REMOVED_STATUS | _REDIRECT_STATUS)
            and last.timestamp > self.ok_captures[0].timestamp
        )


def normalize_url(url: str) -> str | None:
    url = url.strip().strip("<>()[]\"'.,;")
    if not url:
        return None
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "http://" + url
    parsed = urlparse(url)
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return url


def extract_title(document: str) -> str | None:
    match = _TITLE_RE.search(document or "")
    if not match:
        return None
    title = " ".join(html.unescape(match.group(1)).split())
    return title or None


class WaybackConnector(BaseGovConnector):
    source_id = "web.wayback"
    country = Country.GLOBAL
    publisher = "Internet Archive - Wayback Machine"
    base_url = "https://web.archive.org"
    domains = frozenset({Domain.WEB_HISTORY})

    max_urls = 3

    async def availability(self, url: str, timestamp: str | None = None) -> dict[str, Any] | None:
        payload = await self._get_json(
            "https://archive.org/wayback/available", {"url": url, "timestamp": timestamp}
        )
        snapshots = payload.get("archived_snapshots", {}) if isinstance(payload, dict) else {}
        closest = snapshots.get("closest")
        return closest if isinstance(closest, dict) and closest.get("available") else None

    async def captures(self, url: str) -> list[Capture]:
        """Oldest-first distinct states of the page (bounded by ``CDX_LIMIT``)."""
        return await self._cdx(
            url,
            # Collapse consecutive identical captures: each row is a new state of the page.
            {"collapse": "digest", "limit": CDX_LIMIT},
        )

    async def latest_capture(self, url: str) -> Capture | None:
        """Most recent capture (fast path of the CDX server, ~2 s even for busy URLs)."""
        captures = await self._cdx(url, {"limit": -1, "fastLatest": "true"})
        return captures[-1] if captures else None

    async def _cdx(self, url: str, extra: dict[str, Any]) -> list[Capture]:
        payload = await self._get_json(
            "/cdx/search/cdx",
            {"url": url, "output": "json", "fl": "timestamp,original,statuscode,digest", **extra},
        )
        rows = payload if isinstance(payload, list) else []
        return [
            Capture(*(str(v) for v in row[:4]))
            for row in rows[1:]  # first row is the header
            if isinstance(row, list) and len(row) >= 4
        ]

    async def snapshot_title(self, capture: Capture) -> str | None:
        try:
            raw = await self._request(
                WAYBACK_RAW_URL.format(timestamp=capture.timestamp, url=capture.original),
                kind="text",
            )
        except Exception:  # a missing title must not discard the rest of the history
            return None
        return extract_title(raw[:200_000])

    async def history(self, url: str) -> ArchiveHistory:
        captures = await self.captures(url)
        if not captures:
            return ArchiveHistory(url=url, captures=await self._availability_fallback(url))
        truncated = len(captures) >= CDX_LIMIT
        try:
            latest = await self.latest_capture(url)
        except ConnectorError:
            latest = None  # history is still useful without the newest capture
        if latest is not None and latest.timestamp > captures[-1].timestamp:
            captures.append(latest)
        ok = [c for c in captures if c.status == "200"]
        first_title = last_title = None
        if len(ok) >= 2:
            first_title = await self.snapshot_title(ok[0])
            last_title = await self.snapshot_title(ok[-1])
        return ArchiveHistory(
            url=url,
            captures=captures,
            first_title=first_title,
            last_title=last_title,
            truncated=truncated,
        )

    async def _availability_fallback(self, url: str) -> list[Capture]:
        # CDX can miss very recent captures; the availability API is the (slow) fallback.
        try:
            closest = await self.availability(url)
        except ConnectorError:
            return []
        if not closest:
            return []
        return [
            Capture(
                timestamp=str(closest.get("timestamp", "")),
                original=url,
                status=str(closest.get("status", "200")),
                digest="",
            )
        ]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        evidence = []
        urls = [u for u in (normalize_url(raw) for raw in query.urls) if u]
        for url in list(dict.fromkeys(urls))[: self.max_urls]:
            history = await self.history(url)
            first, last = history.first, history.last
            if first is None or last is None:
                evidence.append(
                    self._evidence(
                        title=f"Sem registro no Internet Archive: {url}",
                        url=f"https://web.archive.org/web/*/{url}",
                        excerpt="A URL não possui capturas arquivadas na Wayback Machine.",
                        data={"archived": False},
                    )
                )
                continue
            evidence.append(
                self._evidence(
                    title=f"Histórico no Internet Archive: {url}",
                    url=first.snapshot_url,
                    excerpt=summarize_history(history),
                    venue="Wayback Machine",
                    published_at=first.day,
                    identifiers={
                        "snapshot_first": first.timestamp,
                        "snapshot_last": last.timestamp,
                    },
                    data={
                        "archived": True,
                        "captures_inspected": len(history.captures),
                        "distinct_versions": history.distinct_versions,
                        "history_truncated": history.truncated,
                        "content_changed": history.content_changed,
                        "title_changed": history.title_changed,
                        "first_title": history.first_title,
                        "last_title": history.last_title,
                        "removed_or_redirected": history.removed,
                        "last_status": last.status,
                        "last_snapshot_url": last.snapshot_url,
                    },
                )
            )
        return evidence


def summarize_history(history: ArchiveHistory) -> str:
    first, last = history.first, history.last
    assert first is not None and last is not None
    parts = [f"Primeira captura em {_fmt(first)}; última em {_fmt(last)} (HTTP {last.status})."]
    if history.content_changed:
        prefix = "Mais de " if history.truncated else ""
        parts.append(
            f"{prefix}{history.distinct_versions} versões distintas do conteúdo: a página foi "
            "alterada depois da primeira captura."
        )
    elif history.ok_captures:
        parts.append("Conteúdo idêntico em todas as capturas válidas.")
    if history.title_changed:
        parts.append(f'Título mudou de "{history.first_title}" para "{history.last_title}".')
    if history.removed:
        parts.append("A captura mais recente indica remoção ou redirecionamento da página.")
    return " ".join(parts)


def _fmt(capture: Capture) -> str:
    day = capture.day
    return day.strftime("%d/%m/%Y") if day else capture.timestamp
