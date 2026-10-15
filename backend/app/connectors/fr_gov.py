"""French government primary sources.

* data.gouv.fr - API v1 (national open datasets)
* INSEE - Melodi catalog API (official statistics; open, no key)
* Légifrance (DILA) via PISTE - laws, decrees and codes (requires PISTE OAuth credentials)
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.connectors.base import BaseGovConnector, truncate
from app.connectors.br_gov import normalize
from app.connectors.piste import PisteAuth
from app.core.config import Settings
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, int | float):  # epoch milliseconds (Légifrance)
        try:
            from datetime import UTC, datetime

            return datetime.fromtimestamp(value / 1000, tz=UTC).date()
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


# =====================================================================================
# data.gouv.fr
# =====================================================================================
class DataGouvResource(_ApiModel):
    id: str
    title: str | None = None
    url: str | None = None
    format: str | None = None


class DataGouvOrganization(_ApiModel):
    name: str | None = None


class DataGouvDataset(_ApiModel):
    id: str
    title: str
    slug: str | None = None
    description: str | None = ""
    page: str | None = None
    last_modified: str | None = None
    organization: DataGouvOrganization | None = None
    resources: list[DataGouvResource] = Field(default_factory=list)

    @property
    def web_url(self) -> str:
        return self.page or f"https://www.data.gouv.fr/fr/datasets/{self.slug or self.id}/"


class DataGouvConnector(BaseGovConnector):
    source_id = "fr.data_gouv"
    country = Country.FR
    publisher = "data.gouv.fr (DINUM)"
    base_url = "https://www.data.gouv.fr/api/1"
    domains = frozenset({Domain.POLITICS_LEGISLATION, Domain.ECONOMY_STATISTICS})

    async def search_datasets(self, query: str, *, limit: int = 5) -> list[DataGouvDataset]:
        payload = await self._get_json("/datasets/", {"q": query, "page_size": limit})
        items = payload.get("data", []) if isinstance(payload, dict) else []
        return [DataGouvDataset.model_validate(item) for item in items]

    async def get_dataset(self, dataset_id: str) -> DataGouvDataset:
        payload = await self._get_json(f"/datasets/{dataset_id}/")
        return DataGouvDataset.model_validate(payload)

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        if not query.keywords:
            return []
        evidence: list[Evidence] = []
        for ds in await self.search_datasets(query.text, limit=query.max_results):
            org = ds.organization.name if ds.organization and ds.organization.name else None
            evidence.append(
                self._evidence(
                    publisher=f"{org} via data.gouv.fr" if org else self.publisher,
                    title=ds.title,
                    url=ds.web_url,
                    excerpt=truncate(ds.description),
                    published_at=_parse_iso_date(ds.last_modified),
                    identifiers={"dataset_id": ds.id},
                    data={
                        "dataset_id": ds.id,
                        "last_modified": ds.last_modified,
                        "resources": [
                            {"title": r.title, "format": r.format, "url": r.url}
                            for r in ds.resources[:3]
                        ],
                    },
                )
            )
        return evidence


# =====================================================================================
# INSEE (Melodi)
# =====================================================================================
INSEE_CATALOG_URL = "https://catalogue-donnees.insee.fr/fr/catalogue/recherche/{identifier}"


def _localized(values: Any, lang: str = "fr") -> str:
    """Melodi stores texts as ``[{"content": ..., "lang": ...}]``."""
    if isinstance(values, list):
        for item in values:
            if isinstance(item, dict) and item.get("lang") == lang and item.get("content"):
                return str(item["content"])
        for item in values:
            if isinstance(item, dict) and item.get("content"):
                return str(item["content"])
    return values if isinstance(values, str) else ""


class InseeDataset(BaseModel):
    identifier: str
    title: str
    subtitle: str = ""
    abstract: str = ""
    keywords: list[str] = Field(default_factory=list)
    modified: str | None = None
    temporal: dict[str, Any] = Field(default_factory=dict)

    @property
    def web_url(self) -> str:
        return INSEE_CATALOG_URL.format(identifier=self.identifier)

    @property
    def search_text(self) -> str:
        return normalize(" ".join([self.title, self.subtitle, self.abstract, *self.keywords]))


class InseeConnector(BaseGovConnector):
    """INSEE Melodi catalog (~150 official datasets), searched locally and cached."""

    source_id = "fr.insee"
    country = Country.FR
    publisher = "INSEE - Institut national de la statistique et des études économiques"
    base_url = "https://api.insee.fr/melodi"
    domains = frozenset({Domain.ECONOMY_STATISTICS})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        catalog_ttl_seconds: float = 86_400.0,
        **kw: Any,
    ) -> None:
        super().__init__(client, **kw)
        self.catalog_ttl_seconds = catalog_ttl_seconds

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> InseeConnector:
        return cls(client, catalog_ttl_seconds=settings.dataset_cache_ttl_seconds, **common)

    async def catalog(self) -> list[InseeDataset]:
        payload = await self._request("/catalog/all", cache_ttl=self.catalog_ttl_seconds)
        datasets: list[InseeDataset] = []
        for item in payload if isinstance(payload, list) else []:
            keywords = [
                _localized(k.get("label", [k]) if isinstance(k, dict) else k)
                for k in item.get("keyword") or []
            ]
            datasets.append(
                InseeDataset(
                    identifier=str(item.get("identifier", "")),
                    title=_localized(item.get("title")),
                    subtitle=_localized(item.get("subtitle")),
                    abstract=_localized(item.get("abstract")),
                    keywords=[k for k in keywords if k],
                    modified=item.get("modified"),
                    temporal=item.get("temporal") or {},
                )
            )
        return datasets

    async def search_datasets(self, terms: list[str], *, limit: int = 5) -> list[InseeDataset]:
        needles = [normalize(t) for t in terms if t.strip()]
        if not needles:
            return []
        scored = []
        for ds in await self.catalog():
            text = ds.search_text
            score = sum(text.count(n) for n in needles) + 3 * sum(
                n in normalize(ds.title) for n in needles
            )
            if score:
                scored.append((score, ds))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [ds for _, ds in scored[:limit]]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = [*query.keywords, *query.topics]
        evidence = []
        for ds in await self.search_datasets(terms, limit=query.max_results):
            period = ds.temporal
            coverage = (
                f" Période couverte: {str(period.get('startPeriod', ''))[:4]}–"
                f"{str(period.get('endPeriod', ''))[:4]}."
                if period
                else ""
            )
            evidence.append(
                self._evidence(
                    title=f"{ds.title}" + (f" - {ds.subtitle}" if ds.subtitle else ""),
                    url=ds.web_url,
                    excerpt=truncate(ds.abstract) + coverage,
                    published_at=_parse_iso_date(ds.modified),
                    identifiers={"insee_dataset": ds.identifier},
                    data={
                        "identifier": ds.identifier,
                        "data_api": f"{self.base_url}/data/{ds.identifier}",
                    },
                )
            )
        return evidence


# =====================================================================================
# Légifrance (DILA) via PISTE
# =====================================================================================
LEGIFRANCE_TEXT_URL = "https://www.legifrance.gouv.fr/loda/id/{cid}"


class LegifranceConnector(BaseGovConnector):
    """Laws and decrees in force (fonds LODA). Requires PISTE OAuth credentials."""

    source_id = "fr.legifrance"
    country = Country.FR
    publisher = "Légifrance - Direction de l'information légale et administrative (DILA)"
    base_url = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app"
    domains = frozenset({Domain.POLITICS_LEGISLATION, Domain.LEGAL_JUSTICE})

    def __init__(
        self, client: httpx.AsyncClient | None = None, *, auth: PisteAuth | None = None, **kw: Any
    ) -> None:
        super().__init__(client, **kw)
        self._auth = auth

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> LegifranceConnector:
        auth = (extras or {}).get("piste_auth") or PisteAuth(
            client,
            settings.piste_client_id,
            settings.piste_client_secret,
            sandbox=settings.piste_sandbox,
        )
        return cls(client, auth=auth, **common)

    @property
    def disabled_reason(self) -> str | None:
        if self._auth is None or not self._auth.configured:
            return "requires VERITAS_PISTE_CLIENT_ID / VERITAS_PISTE_CLIENT_SECRET"
        return None

    def _url(self, path: str) -> str:
        if self._auth is not None and self._auth.sandbox and not path.startswith("http"):
            return f"{self._auth.api_url}/dila/legifrance/lf-engine-app/{path.lstrip('/')}"
        return super()._url(path)

    async def _auth_headers(self) -> dict[str, str]:
        return await self._auth.headers() if self._auth else {}

    async def search_texts(self, terms: str, *, limit: int = 5) -> list[dict[str, Any]]:
        body = {
            "fond": "LODA_DATE",
            "recherche": {
                "champs": [
                    {
                        "typeChamp": "ALL",
                        "operateur": "ET",
                        "criteres": [
                            {
                                "typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP",
                                "valeur": terms,
                                "operateur": "ET",
                            }
                        ],
                    }
                ],
                "filtres": [{"facette": "TEXT_LEGAL_STATUS", "valeur": "VIGUEUR"}],
                "operateur": "ET",
                "pageNumber": 1,
                "pageSize": limit,
                "sort": "PERTINENCE",
                "typePagination": "DEFAUT",
            },
        }
        payload = await self._request("/search", method="POST", json_body=body)
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return results[:limit]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = " ".join([*query.legal_references, *query.keywords][:4])
        if not terms:
            return []
        evidence = []
        for result in await self.search_texts(terms, limit=query.max_results):
            titles = result.get("titles") or [{}]
            first = titles[0] if isinstance(titles[0], dict) else {}
            cid = first.get("cid") or first.get("id") or result.get("id") or ""
            title = _strip_markup(first.get("title") or result.get("title") or "Texte Légifrance")
            sections = result.get("sections") or []
            snippet = ""
            if sections and isinstance(sections[0], dict):
                extracts = sections[0].get("extracts") or []
                if extracts and isinstance(extracts[0], dict):
                    snippet = " ".join(extracts[0].get("values") or [])
            evidence.append(
                self._evidence(
                    title=title,
                    url=LEGIFRANCE_TEXT_URL.format(cid=cid)
                    if cid
                    else "https://www.legifrance.gouv.fr",
                    excerpt=truncate(_strip_markup(snippet)),
                    venue="Journal officiel de la République française",
                    published_at=_parse_iso_date(result.get("date") or first.get("date")),
                    identifiers={
                        k: v for k, v in {"cid": cid, "nor": result.get("nor")}.items() if v
                    },
                    data={"nature": result.get("nature"), "etat": result.get("etat")},
                )
            )
        return evidence


def _strip_markup(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()
