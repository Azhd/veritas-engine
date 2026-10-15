"""Crossref: the official DOI registry, with retraction notices (incl. Retraction Watch).

"A study proved that..." is a common disinformation pattern, and many such studies were later
retracted (e.g. the 1998 Lancet MMR/autism paper, retracted in 2010). Crossref records the
retraction notices that publishers and the Retraction Watch database attach to articles. Free,
no key; requests go one at a time (Crossref limits concurrent calls).
"""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Any

from app.connectors.base import BaseGovConnector, truncate
from app.connectors.br_gov import normalize
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

#: Words that cite research (normalized PT/EN/FR): only then is Crossref consulted.
STUDY_WORDS = (
    "estudo", "pesquisa", "artigo", "revista", "cientist", "cientific", "publicad", "doi",
    "etude", "article", "revue", "chercheur", "scientifi", "publie", "study", "studies",
    "research", "journal", "paper", "scientist", "published", "lancet", "nature", "science",
    "retrat", "retract", "fraude", "fraud",
)  # fmt: skip
_UPDATE_LABELS = {
    "retraction": "retratação",
    "withdrawal": "retirada",
    "expression_of_concern": "manifestação de preocupação",
    "correction": "correção",
}


def cites_research(query: EvidenceQuery) -> bool:
    text = f" {normalize(' '.join([*query.keywords, *query.keywords_en, *query.topics]))} "
    return any(word in text for word in STUDY_WORDS)


class CrossrefRetractionsConnector(BaseGovConnector):
    source_id = "science.crossref"
    country = Country.GLOBAL
    publisher = "Crossref - registro oficial de DOIs (avisos de retratação, incl. Retraction Watch)"
    base_url = "https://api.crossref.org"
    domains = frozenset({Domain.HEALTH_SCIENCE, Domain.CLIMATE_ENVIRONMENT})

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = [t for t in query.keywords_en if t] or query.keywords
        if not terms or not cites_research(query):
            return []
        payload = await self._get_json(
            "/works",
            {
                "query.bibliographic": " ".join(terms[:6]),
                "filter": "update-type:retraction",
                "rows": MAX_NOTICES,
                "select": "DOI,title,container-title,issued,update-to,URL",
            },
        )
        items = ((payload or {}).get("message") or {}).get("items", []) if payload else []
        stems = _stems(terms)
        evidence: list[Evidence] = []
        lookups = 0
        for item in items:  # one at a time: Crossref limits concurrent requests
            notice = self._notice(item)
            if notice is None:
                continue
            # Notices are often titled just "Statement of retraction": judge the relevance by
            # the title of the retracted article itself.
            original = _first_title(item)
            if not _relevant(original, stems):
                if lookups >= MAX_LOOKUPS:
                    continue
                lookups += 1
                original = await self._title_of(notice.identifiers["retracted_doi"])
                if not _relevant(original, stems):
                    continue
            if original:
                notice.title = truncate(f"Artigo retratado: {original}", 300)
            evidence.append(notice)
            if len(evidence) >= query.max_results:
                break
        return evidence

    async def _title_of(self, doi: str) -> str:
        if not doi:
            return ""
        try:
            payload = await self._get_json(f"/works/{doi}", {"select": "title"})
        except Exception:  # a missing title only drops this notice
            return ""
        return _clean((((payload or {}).get("message") or {}).get("title") or [""])[0])

    def _notice(self, item: dict[str, Any]) -> Evidence | None:
        updates = [u for u in item.get("update-to") or [] if u.get("type") in _UPDATE_LABELS]
        if not updates:
            return None
        update = updates[0]
        retracted_doi = str(update.get("DOI", ""))
        sources = sorted({str(u.get("source", "")) for u in updates if u.get("source")})
        source_text = " e ".join(
            "Retraction Watch" if s == "retraction-watch" else "editora" for s in sources
        )
        day = _date_parts(update.get("updated")) or _date_parts(item.get("issued"))
        journal = (item.get("container-title") or [""])[0]
        title = _clean((item.get("title") or ["Aviso de retratação"])[0])
        kind = _UPDATE_LABELS[str(update.get("type"))]
        return self._evidence(
            title=truncate(title, 300),
            url=item.get("URL") or f"https://doi.org/{item.get('DOI')}",
            excerpt=_notice_text(kind, journal, day, retracted_doi, source_text),
            venue=journal or None,
            published_at=day,
            identifiers={"doi": str(item.get("DOI", "")), "retracted_doi": retracted_doi},
            data={
                "update_type": update.get("type"),
                "retracted": update.get("type") == "retraction",
            },
        )


#: Retraction notices fetched per claim, and extra lookups of retracted titles (one at a time).
MAX_NOTICES = 20
MAX_LOOKUPS = 6


def _stems(terms: list[str]) -> list[str]:
    """First five letters of each distinct word: 'vaccines' and 'vaccine' share 'vacci'."""
    words = {w for t in terms for w in normalize(t).split() if len(w) >= 4}
    # "study", "proved"... are in every claim of this kind: they say nothing about the subject
    generic = (*STUDY_WORDS, "prove", "prouv", "provo", "demon", "mostr", "show")
    return sorted({w[:5] for w in words if not w.startswith(generic)})


def _relevant(title: str, stems: list[str]) -> bool:
    text = normalize(title or "")
    hits = sum(stem in text for stem in stems)
    return bool(text) and hits >= min(2, len(stems))


def _clean(title: str) -> str:
    """Crossref titles may carry (double-)escaped markup: "&amp;lt;i&amp;gt;Gamma..."."""
    text = html.unescape(html.unescape(title or ""))
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def _first_title(item: dict[str, Any]) -> str:
    title = _clean((item.get("title") or [""])[0])
    # "RETRACTED: <original title>" carries the original title already
    return title.split(":", 1)[1].strip() if title.upper().startswith("RETRACTED:") else ""


def _notice_text(kind: str, journal: str, day: date | None, doi: str, source: str) -> str:
    parts = [f"Aviso de {kind}"]
    if journal:
        parts.append(f" na revista {journal}")
    if day:
        parts.append(f" em {day:%d/%m/%Y}")
    parts.append(f": o artigo DOI {doi} foi oficialmente marcado")
    if source:
        parts.append(f" (fonte: {source})")
    parts.append(". Um estudo retratado não sustenta nenhuma alegação.")
    return "".join(parts)


def _date_parts(value: Any) -> date | None:
    try:
        parts = (value or {}).get("date-parts", [[]])[0]
        return date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 1,
                    int(parts[2]) if len(parts) > 2 else 1)  # fmt: skip
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
