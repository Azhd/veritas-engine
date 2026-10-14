"""Health and science primary sources.

* PubMed / NCBI E-utilities - peer-reviewed literature (esearch -> esummary -> efetch abstracts)
* WHO Global Health Observatory (GHO) OData API - official global health indicators
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx
from defusedxml import ElementTree
from pydantic import SecretStr

from app.connectors.base import BaseGovConnector, truncate
from app.core.config import Settings
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}
#: Publication types that carry the highest level of evidence; flagged for the verdict engine.
HIGH_EVIDENCE_TYPES = frozenset(
    {"Meta-Analysis", "Systematic Review", "Randomized Controlled Trial", "Practice Guideline"}
)


def parse_pubmed_date(value: str | None) -> date | None:
    """PubMed dates look like '2022 Jun 21', '2021 Jul' or '2019'."""
    if not value:
        return None
    match = re.match(r"(\d{4})(?:\s+([A-Za-z]{3}))?(?:\s+(\d{1,2}))?", value.strip())
    if not match:
        return None
    year = int(match.group(1))
    month = _MONTHS.get((match.group(2) or "").lower(), 1)
    day = int(match.group(3)) if match.group(3) else 1
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1)


class PubMedConnector(BaseGovConnector):
    source_id = "science.pubmed"
    country = Country.GLOBAL
    publisher = "PubMed - National Library of Medicine (NCBI/NIH)"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    domains = frozenset({Domain.HEALTH_SCIENCE})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        api_key: SecretStr | None = None,
        email: str | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(client, **kw)
        self._api_key = api_key
        self._email = email

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> PubMedConnector:
        return cls(client, api_key=settings.ncbi_api_key, email=settings.ncbi_email, **common)

    def _common_params(self) -> dict[str, str]:
        params = {"tool": "veritas-engine"}
        if self._email:
            params["email"] = self._email
        if self._api_key and self._api_key.get_secret_value():
            params["api_key"] = self._api_key.get_secret_value()
        return params

    async def search_ids(self, term: str, *, limit: int = 5) -> list[str]:
        payload = await self._get_json(
            "/esearch.fcgi",
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": limit,
                "sort": "relevance",
                **self._common_params(),
            },
        )
        result = payload.get("esearchresult", {}) if isinstance(payload, dict) else {}
        return [str(pmid) for pmid in result.get("idlist", [])]

    async def summaries(self, pmids: list[str]) -> list[dict[str, Any]]:
        if not pmids:
            return []
        payload = await self._get_json(
            "/esummary.fcgi",
            {"db": "pubmed", "id": ",".join(pmids), "retmode": "json", **self._common_params()},
        )
        result = payload.get("result", {}) if isinstance(payload, dict) else {}
        return [
            result[pmid] for pmid in result.get("uids", []) if isinstance(result.get(pmid), dict)
        ]

    async def abstracts(self, pmids: list[str]) -> dict[str, str]:
        if not pmids:
            return {}
        xml = await self._request(
            "/efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(pmids),
                "rettype": "abstract",
                "retmode": "xml",
                **self._common_params(),
            },
            kind="text",
        )
        return parse_abstracts(xml)

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        term = query.text_en
        if not term:
            return []
        pmids = await self.search_ids(term, limit=query.max_results)
        summaries = await self.summaries(pmids)
        try:
            abstracts = await self.abstracts(pmids)
        except Exception:  # abstracts are a nice-to-have; metadata alone is still evidence
            abstracts = {}
        evidence = []
        for item in summaries:
            pmid = str(item.get("uid"))
            ids = {a.get("idtype"): a.get("value") for a in item.get("articleids", [])}
            pubtypes = item.get("pubtype") or []
            identifiers = {"pmid": pmid}
            if ids.get("doi"):
                identifiers["doi"] = ids["doi"]
            if ids.get("pmc"):
                identifiers["pmcid"] = ids["pmc"]
            authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
            evidence.append(
                self._evidence(
                    title=item.get("title") or f"PubMed {pmid}",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    excerpt=truncate(abstracts.get(pmid) or "; ".join(pubtypes), 900),
                    authors=authors[:8] + (["et al."] if len(authors) > 8 else []),
                    venue=item.get("fulljournalname") or item.get("source"),
                    published_at=parse_pubmed_date(item.get("pubdate")),
                    identifiers=identifiers,
                    data={
                        "publication_types": pubtypes,
                        "high_level_evidence": bool(HIGH_EVIDENCE_TYPES & set(pubtypes)),
                        "retracted": "Retracted Publication" in pubtypes,
                    },
                )
            )
        return evidence


def parse_abstracts(xml: str) -> dict[str, str]:
    """Extract ``{pmid: abstract}`` from an efetch PubmedArticleSet document."""
    if not xml or not xml.strip():
        return {}
    root = ElementTree.fromstring(xml.encode("utf-8"))
    abstracts: dict[str, str] = {}
    for article in root.iter("PubmedArticle"):
        pmid = article.findtext(".//PMID")
        parts = []
        for node in article.iter("AbstractText"):
            text = "".join(node.itertext()).strip()
            label = node.get("Label")
            if text:
                parts.append(f"{label}: {text}" if label else text)
        if pmid and parts:
            abstracts[pmid] = " ".join(parts)
    return abstracts


# =====================================================================================
# WHO Global Health Observatory
# =====================================================================================
WHO_COUNTRY_CODES = {"BR": "BRA", "FR": "FRA"}
_ODATA_UNSAFE = re.compile(r"[^\w\s\-]", re.UNICODE)


class WhoGhoConnector(BaseGovConnector):
    source_id = "health.who_gho"
    country = Country.GLOBAL
    publisher = "Organização Mundial da Saúde (OMS/WHO) - Global Health Observatory"
    base_url = "https://ghoapi.azureedge.net/api"
    domains = frozenset({Domain.HEALTH_SCIENCE})

    max_indicators = 2

    async def find_indicators(self, term: str, *, limit: int = 3) -> list[dict[str, str]]:
        safe = _ODATA_UNSAFE.sub(" ", term).strip().lower()
        if not safe:
            return []
        payload = await self._get_json(
            "/Indicator",
            {"$filter": f"contains(tolower(IndicatorName),'{safe}')", "$top": limit},
        )
        return payload.get("value", []) if isinstance(payload, dict) else []

    async def indicator_values(
        self, code: str, spatial: str, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        safe_code = re.sub(r"[^\w]", "", code)
        payload = await self._get_json(
            f"/{safe_code}",
            {
                "$filter": f"SpatialDim eq '{spatial}'",
                "$orderby": "TimeDim desc",
                "$top": limit,
            },
        )
        return payload.get("value", []) if isinstance(payload, dict) else []

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = [t for t in [*query.topics_en, *query.keywords_en] if t] or query.keywords
        spatials = [WHO_COUNTRY_CODES[c] for c in query.countries if c in WHO_COUNTRY_CODES]
        spatials = spatials or ["GLOBAL"]
        evidence: list[Evidence] = []
        seen: set[str] = set()
        for term in terms[:3]:
            for indicator in await self.find_indicators(term):
                code = indicator.get("IndicatorCode", "")
                if not code or code in seen or len(seen) >= self.max_indicators:
                    continue
                seen.add(code)
                for spatial in spatials:
                    rows = _preferred_rows(await self.indicator_values(code, spatial))
                    if not rows:
                        continue
                    series = "; ".join(
                        f"{r.get('TimeDim')}: {r.get('Value') or r.get('NumericValue')}"
                        for r in rows[:6]
                    )
                    evidence.append(
                        self._evidence(
                            title=f"{indicator.get('IndicatorName')} - {spatial}",
                            url=f"{self.base_url}/{code}?$filter=SpatialDim%20eq%20'{spatial}'",
                            excerpt=series,
                            published_at=_year_date(rows[0].get("TimeDim")),
                            identifiers={"who_indicator": code, "spatial": spatial},
                            data={
                                "series": {
                                    str(r.get("TimeDim")): r.get("NumericValue") for r in rows[:6]
                                }
                            },
                        )
                    )
        return evidence[: query.max_results]


def _preferred_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer totals (both sexes / no breakdown) and one value per year."""
    totals = [r for r in rows if r.get("Dim1") in (None, "SEX_BTSX", "BOTHSEXES")] or rows
    by_year: dict[Any, dict[str, Any]] = {}
    for row in totals:
        by_year.setdefault(row.get("TimeDim"), row)
    return list(by_year.values())


def _year_date(value: Any) -> date | None:
    try:
        return date(int(value), 1, 1)
    except (TypeError, ValueError):
        return None
