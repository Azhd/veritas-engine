"""Google Fact Check Tools: checks already published by professional fact-checkers.

The API aggregates ClaimReview markup of fact-checking organisations (AFP Factuel, Les
Décodeurs, Lupa, Aos Fatos, Agência Lupa, PolitiFact...). It needs a free Google API key on the
server (``VERITAS_GOOGLE_FACTCHECK_API_KEY``); without it the source is simply disabled. The key
goes in a header, never in the URL, so it cannot leak into logs or error messages.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from pydantic import SecretStr

from app.connectors.base import BaseGovConnector, truncate
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

_ALL_DOMAINS = frozenset(Domain)


class GoogleFactCheckConnector(BaseGovConnector):
    source_id = "factcheck.google"
    country = Country.GLOBAL
    publisher = "Google Fact Check Tools (checagens publicadas por agências de checagem)"
    base_url = "https://factchecktools.googleapis.com/v1alpha1"
    domains = _ALL_DOMAINS  # a fact-check can exist about any subject

    def __init__(
        self, client: httpx.AsyncClient | None = None, *, api_key: SecretStr | None = None, **kw
    ) -> None:
        super().__init__(client, **kw)
        self._api_key = api_key

    @classmethod
    def from_settings(
        cls, settings, client, extras=None, **common: Any
    ) -> GoogleFactCheckConnector:
        return cls(client, api_key=settings.google_factcheck_api_key, **common)

    @property
    def disabled_reason(self) -> str | None:
        if not self._api_key or not self._api_key.get_secret_value():
            return "requires VERITAS_GOOGLE_FACTCHECK_API_KEY (free Google Cloud key)"
        return None

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = query.keywords[:5] or query.keywords_en[:5]
        if not terms or self._api_key is None:
            return []
        payload = await self._request(
            "/claims:search",
            {"query": " ".join(terms), "languageCode": query.language, "pageSize": 5},
            headers={"X-Goog-Api-Key": self._api_key.get_secret_value()},
        )
        evidence: list[Evidence] = []
        for claim in (payload or {}).get("claims", []) if isinstance(payload, dict) else []:
            for review in claim.get("claimReview", [])[:1]:
                publisher = (review.get("publisher") or {}).get("name") or "agência de checagem"
                rating = review.get("textualRating") or "sem classificação"
                day = _day(review.get("reviewDate")) or _day(claim.get("claimDate"))
                evidence.append(
                    self._evidence(
                        title=truncate(review.get("title") or claim.get("text") or "Checagem", 300),
                        url=review.get("url") or "https://toolbox.google.com/factcheck/explorer",
                        excerpt=_review_text(publisher, rating, claim),
                        venue=publisher,
                        published_at=day,
                        identifiers={"factcheck_publisher": publisher},
                        data={"rating": rating, "language": review.get("languageCode")},
                    )
                )
        return evidence[: query.max_results]


def _review_text(publisher: str, rating: str, claim: dict[str, Any]) -> str:
    text = f"Checagem de {publisher}: classificação “{rating}”."
    if claim.get("text"):
        text += f" Afirmação checada: “{truncate(claim['text'], 280)}”"
        if claim.get("claimant"):
            text += f" (autor: {claim['claimant']})"
        text += "."
    return text


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None
