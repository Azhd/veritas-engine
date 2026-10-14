"""data.gouv.fr - public API v1.

Docs: https://doc.data.gouv.fr/api/reference/
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.connectors.base import BaseGovConnector, truncate
from app.schemas.evidence import Country, Evidence, EvidenceQuery


class _GouvModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class DataGouvResource(_GouvModel):
    id: str
    title: str | None = None
    url: str | None = None
    format: str | None = None


class DataGouvOrganization(_GouvModel):
    name: str | None = None


class DataGouvDataset(_GouvModel):
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
            data: dict[str, Any] = {
                "dataset_id": ds.id,
                "last_modified": ds.last_modified,
                "resources": [
                    {"title": r.title, "format": r.format, "url": r.url} for r in ds.resources[:3]
                ],
            }
            evidence.append(
                Evidence(
                    connector=self.source_id,
                    country=self.country,
                    publisher=f"{org} via data.gouv.fr" if org else self.publisher,
                    title=ds.title,
                    url=ds.web_url,
                    excerpt=truncate(ds.description),
                    data=data,
                )
            )
        return evidence
