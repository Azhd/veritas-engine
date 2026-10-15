"""Public knowledge bases (not official sources): Wikidata for who holds which office.

No government API answers "who is the president of Ukraine?", so claims like "Macron is the
president of Ukraine" had no evidence at all. Wikidata (Wikimedia, free, no key) holds current
heads of state and government and the positions people held, with start and end dates.

It is a collaborative base, not an official source: every item says so in its publisher, and
each statement carries whether Wikidata backs it with a reference. The orchestrator caps the
confidence of verdicts that rest only on unreferenced non-official statements.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.connectors.base import BaseGovConnector
from app.connectors.br_gov import normalize
from app.connectors.countries import countries_in as iso_countries_in
from app.connectors.countries import country_names_in, wikidata_id
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIDATA_PAGE = "https://www.wikidata.org/wiki/{qid}"
#: Connector ids that are public knowledge bases, not official sources.
UNOFFICIAL_SOURCES = frozenset({"kb.wikidata"})

#: Words that make a claim about an office (normalized, matched as substrings of " text ").
OFFICE_WORDS = (
    "presiden", "ministr", "minister", "chancel", " rei ", " roi ", " king", "queen", "rainha",
    "reine", "governador", "gouverneur", "governor", "prefeito", " maire", "mayor",
    "chefe de estado", "chef de l'etat", "head of state", "premier", "primeiro-ministro",
    "senador", "senateur", "senator", "deputad", "depute", " papa ", " pape", " pope",
    "secretario-geral", "secretaire general", "secretary-general", "chef du gouvernement",
    "chefe de governo", "head of government", "lider", "leader", "dirigeant", "governo",
    "gouvernement", "government", "eleito", "elu ", "elected",
)  # fmt: skip

_LANGUAGES = {"pt": "pt,mul,en,fr", "fr": "fr,mul,en,pt", "en": "en,mul,fr,pt"}
_ROLE_LABELS = {"head_of_state": "Chefe de Estado", "head_of_government": "Chefe de governo"}


def countries_in(text: str) -> list[str]:
    """Wikidata ids of the countries named in ``text`` (see ``app.connectors.countries``)."""
    return [wikidata_id(iso) for iso in iso_countries_in(text)]


def is_about_office(text: str) -> bool:
    padded = f" {normalize(text)} "
    return any(word in padded for word in OFFICE_WORDS)


def _day(value: str | None) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _br(day: date | None) -> str:
    return day.strftime("%d/%m/%Y") if day else "?"


class WikidataConnector(BaseGovConnector):
    source_id = "kb.wikidata"
    country = Country.GLOBAL
    publisher = "Wikidata (base de conhecimento pública e colaborativa, não oficial)"
    base_url = WIKIDATA_API
    domains = frozenset({Domain.POLITICS_LEGISLATION, Domain.GEOPOLITICS})

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = [*query.people, *query.keywords, *query.keywords_en, *query.topics]
        text = " ".join(terms)
        if not (query.people or is_about_office(text)):
            return []  # only claims about who holds an office
        languages = _LANGUAGES.get(query.language, _LANGUAGES["pt"])
        countries = countries_in(text)
        country_words = country_names_in(text)
        candidates = [
            t
            for t in dict.fromkeys([*query.people, *query.keywords])
            if len(t) >= 4 and normalize(t) not in country_words and not is_about_office(t)
        ][:3]
        evidence: list[Evidence] = []
        if countries:
            evidence.extend(await self._leaders(countries, languages))
        people = await self._find_people(candidates, query.language)
        if people:
            evidence.extend(await self._positions(people, languages))
        return evidence[: query.max_results]

    # ------------------------------------------------------------------ lookups
    async def _find_people(self, terms: list[str], language: str) -> list[str]:
        """Wikidata ids of the search results that are people (the 'human' class)."""
        found: list[str] = []
        for term in terms:
            payload = await self._request(
                WIKIDATA_API,
                {
                    "action": "wbsearchentities",
                    "search": term,
                    "language": language if language in _LANGUAGES else "pt",
                    "uselang": language if language in _LANGUAGES else "pt",
                    "type": "item",
                    "limit": 7,
                    "format": "json",
                },
            )
            found.extend(item["id"] for item in (payload or {}).get("search", []) if "id" in item)
        if not found:
            return []
        ids = " ".join(f"wd:{qid}" for qid in dict.fromkeys(found))
        rows = await self._sparql(
            f"SELECT ?item WHERE {{ VALUES ?item {{ {ids} }} ?item wdt:P31 wd:Q5 . }}"
        )
        humans = {row["item"].rsplit("/", 1)[-1] for row in rows}
        # keep the search order (most relevant first), at most two people
        return [qid for qid in dict.fromkeys(found) if qid in humans][:2]

    async def _leaders(self, countries: list[str], languages: str) -> list[Evidence]:
        ids = " ".join(f"wd:{qid}" for qid in countries)
        rows = await self._sparql(
            "SELECT ?country ?countryLabel ?role ?person ?personLabel ?start ?referenced WHERE {\n"
            f"  VALUES ?country {{ {ids} }}\n"
            '  { ?country p:P35 ?st . ?st ps:P35 ?person . BIND("head_of_state" AS ?role) }\n'
            "  UNION { ?country p:P6 ?st . ?st ps:P6 ?person .\n"
            '          BIND("head_of_government" AS ?role) }\n'
            "  FILTER NOT EXISTS { ?st pq:P582 ?end }\n"
            "  OPTIONAL { ?st pq:P580 ?start }\n"
            "  BIND(EXISTS { ?st prov:wasDerivedFrom ?ref } AS ?referenced)\n"
            f'  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{languages}". }}\n'
            "}"
        )
        by_country: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_country.setdefault(row["country"].rsplit("/", 1)[-1], []).append(row)
        evidence = []
        for qid in countries:
            items = sorted(by_country.get(qid, []), key=lambda r: r["role"] != "head_of_state")
            if not items:
                continue
            name = items[0].get("countryLabel", qid)
            parts, holders = [], []
            for row in items:
                start = _day(row.get("start"))
                referenced = row.get("referenced") == "true"
                ref_note = "com referência" if referenced else "sem referência no Wikidata"
                parts.append(
                    f"{_ROLE_LABELS[row['role']]}: {row.get('personLabel', '?')} "
                    f"(desde {_br(start)}; {ref_note})"
                )
                holders.append(
                    {
                        "role": row["role"],
                        "person": row.get("personLabel"),
                        "person_id": row["person"].rsplit("/", 1)[-1],
                        "start": start.isoformat() if start else None,
                        "referenced": referenced,
                    }
                )
            evidence.append(
                self._evidence(
                    title=f"{name}: chefe de Estado e de governo atuais",
                    url=WIKIDATA_PAGE.format(qid=qid),
                    excerpt=". ".join(parts) + ". Fonte pública colaborativa, não oficial.",
                    identifiers={"wikidata": qid},
                    data={
                        "official": False,
                        "referenced": all(h["referenced"] for h in holders),
                        "holders": holders,
                    },
                )
            )
        return evidence

    async def _positions(self, people: list[str], languages: str) -> list[Evidence]:
        ids = " ".join(f"wd:{qid}" for qid in people)
        rows = await self._sparql(
            "SELECT ?person ?personLabel ?position ?positionLabel ?start ?end ?referenced WHERE {\n"
            f"  VALUES ?person {{ {ids} }}\n"
            "  ?person p:P39 ?st . ?st ps:P39 ?position .\n"
            "  OPTIONAL { ?st pq:P580 ?start } OPTIONAL { ?st pq:P582 ?end }\n"
            "  BIND(EXISTS { ?st prov:wasDerivedFrom ?ref } AS ?referenced)\n"
            f'  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{languages}". }}\n'
            "} LIMIT 60"
        )
        by_person: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_person.setdefault(row["person"].rsplit("/", 1)[-1], []).append(row)
        evidence = []
        for qid in people:
            items = by_person.get(qid, [])
            if not items:
                continue
            name = items[0].get("personLabel", qid)
            positions = []
            for row in items:
                start, end = _day(row.get("start")), _day(row.get("end"))
                positions.append(
                    {
                        "position": row.get("positionLabel"),
                        "start": start.isoformat() if start else None,
                        "end": end.isoformat() if end else None,
                        "current": end is None,
                        "referenced": row.get("referenced") == "true",
                    }
                )
            # current offices first, then the most recent ones
            current = [p for p in positions if p["current"]]
            past = sorted((p for p in positions if not p["current"]),
                          key=lambda p: p["start"] or "", reverse=True)  # fmt: skip
            lines = [f"{p['position']} (desde {_br(_day(p['start']))}, atual)" for p in current] + [
                f"{p['position']} ({_br(_day(p['start']))} a {_br(_day(p['end']))})"
                for p in past[:5]
            ]
            evidence.append(
                self._evidence(
                    title=f"{name}: cargos ocupados",
                    url=WIKIDATA_PAGE.format(qid=qid),
                    excerpt="Cargos: "
                    + "; ".join(lines)
                    + ". Fonte pública colaborativa, não oficial.",
                    identifiers={"wikidata": qid},
                    data={
                        "official": False,
                        "referenced": any(p["referenced"] for p in current),
                        "positions": [*current, *past[:5]],
                    },
                )
            )
        return evidence

    async def _sparql(self, query: str) -> list[dict[str, str]]:
        payload = await self._request(
            WIKIDATA_SPARQL,
            {"query": query},
            headers={"Accept": "application/sparql-results+json"},
        )
        bindings = ((payload or {}).get("results") or {}).get("bindings", [])
        return [{k: v.get("value", "") for k, v in row.items()} for row in bindings]
