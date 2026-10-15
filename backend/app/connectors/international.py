"""Official international statistics: World Bank (all countries) and Eurostat (EU).

IBGE and INSEE only cover Brazil and France; claims about other countries ("unemployment in
Germany", "Argentina's inflation") had no official numbers. Both sources are free, keyless and
answer in well under a second.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.connectors.base import BaseGovConnector
from app.connectors.br_gov import normalize
from app.connectors.countries import EU_MEMBERS, countries_in, mentions_eu
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str  # Portuguese, like the other connectors
    triggers: tuple[str, ...]  # normalized substrings (PT/EN/FR)
    unit: str = ""


#: What a claim can be about, with the words that announce it.
INDICATORS: tuple[Indicator, ...] = (
    Indicator("unemployment", "Taxa de desemprego", (
        "desemprego", "desocupacao", "chomage", "unemployment", "jobless"), "%"),
    Indicator("inflation", "Inflação anual", (
        "inflacao", "inflation", "custo de vida", "cout de la vie", "cost of living"), "%"),
    Indicator("population", "População", (
        "populacao", "habitante", "population", "inhabitant", "habitant"), "pessoas"),
    Indicator("gdp_growth", "Crescimento real do PIB", (
        "crescimento", "croissance", "growth", "recessao", "recession"), "%"),
    Indicator("gdp", "PIB", ("pib", "gdp", "produto interno", "produit interieur"), ""),
    Indicator("life_expectancy", "Expectativa de vida ao nascer", (
        "expectativa de vida", "esperance de vie", "life expectancy"), "anos"),
    Indicator("poverty", "Pobreza extrema (abaixo de US$ 3/dia)", (
        "pobreza", "pauvrete", "poverty", "miseria", "extreme poor"), "%"),
)  # fmt: skip


def indicators_for(query: EvidenceQuery) -> list[Indicator]:
    text = f" {normalize(' '.join([*query.keywords, *query.keywords_en, *query.topics]))} "
    found = [i for i in INDICATORS if any(t in text for t in i.triggers)]
    # "crescimento do PIB" is growth, not the GDP level
    if any(i.key == "gdp_growth" for i in found):
        found = [i for i in found if i.key != "gdp"]
    return found[:2]


def claim_countries(query: EvidenceQuery) -> list[str]:
    """Countries named in the claim; else the single country of its context (BR or FR)."""
    named = countries_in(" ".join([*query.keywords, *query.keywords_en, *query.topics]))
    if named:
        return named
    return list(query.countries) if len(query.countries) == 1 else []


def _billions(value: float, currency: str) -> str:
    """1234.56 -> 'US$ 1.234,6 bi' (Brazilian number format, like the other sources)."""
    text = f"{value:,.1f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{currency} {text} bi"


def _series_text(points: list[tuple[str, float]], unit: str) -> str:
    def fmt(value: float) -> str:
        if unit == "pessoas":
            return f"{value:,.0f}".replace(",", ".")
        if unit == "%":
            return f"{value:.1f}%".replace(".", ",")
        if unit == "anos":
            return f"{value:.1f} anos".replace(".", ",")
        return f"{value:,.0f}".replace(",", ".")

    return "; ".join(f"{period}: {fmt(value)}" for period, value in points)


# ====================================================================== World Bank
WORLD_BANK_CODES = {
    "unemployment": "SL.UEM.TOTL.ZS",
    "inflation": "FP.CPI.TOTL.ZG",
    "population": "SP.POP.TOTL",
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",
    "gdp": "NY.GDP.MKTP.CD",
    "life_expectancy": "SP.DYN.LE00.IN",
    "poverty": "SI.POV.DDAY",
}


class WorldBankConnector(BaseGovConnector):
    source_id = "intl.worldbank"
    country = Country.GLOBAL
    publisher = "Banco Mundial - World Development Indicators (dados oficiais dos países)"
    base_url = "https://api.worldbank.org/v2"
    domains = frozenset({Domain.ECONOMY_STATISTICS, Domain.HEALTH_SCIENCE})

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        indicators = indicators_for(query)
        countries = claim_countries(query)
        if not indicators or not countries:
            return []
        evidence = []
        for indicator in indicators:
            code = WORLD_BANK_CODES[indicator.key]
            payload = await self._get_json(
                f"/country/{';'.join(countries)}/indicator/{code}",
                {"format": "json", "mrv": 6, "per_page": 60},
            )
            rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
            by_country: dict[str, list[dict[str, Any]]] = {}
            for row in rows or []:
                if row.get("value") is not None:
                    by_country.setdefault(row["country"]["id"], []).append(row)
            for iso, items in by_country.items():
                items.sort(key=lambda r: r["date"], reverse=True)
                points = [(r["date"], float(r["value"])) for r in items[:5]]
                name = items[0]["country"]["value"]
                unit = indicator.unit if indicator.key != "gdp" else ""
                if indicator.key == "gdp":
                    excerpt = "; ".join(f"{p}: {_billions(v / 1e9, 'US$')}" for p, v in points)
                else:
                    excerpt = _series_text(points, unit)
                evidence.append(
                    self._evidence(
                        title=f"{indicator.label} - {name} ({items[0]['indicator']['value']})",
                        url=f"https://data.worldbank.org/indicator/{code}?locations={iso}",
                        excerpt=excerpt,
                        published_at=date(int(points[0][0]), 12, 31),
                        identifiers={"wb_indicator": code, "country": iso},
                        data={"series": dict(points), "unit": unit or "USD"},
                    )
                )
        return evidence[: query.max_results]


# ====================================================================== Eurostat
#: dataset, filters and unit label for each indicator (EU countries and EU27 aggregate).
EUROSTAT_DATASETS: dict[str, tuple[str, dict[str, str]]] = {
    "unemployment": ("une_rt_a", {"age": "Y15-74", "unit": "PC_ACT", "sex": "T"}),
    "inflation": ("prc_hicp_aind", {"coicop": "CP00", "unit": "RCH_A_AVG"}),
    "population": ("tps00001", {}),
    "gdp_growth": ("tec00115", {"unit": "CLV_PCH_PRE", "na_item": "B1GQ"}),
    "gdp": ("nama_10_gdp", {"unit": "CP_MEUR", "na_item": "B1GQ"}),
    "life_expectancy": ("demo_mlexpec", {"sex": "T", "age": "Y_LT1"}),
}
#: Eurostat writes Greece as EL.
_EUROSTAT_GEO = {"GR": "EL"}
EU_AGGREGATE = "EU27_2020"


class EurostatConnector(BaseGovConnector):
    source_id = "eu.eurostat"
    country = Country.EU
    publisher = "Eurostat - Serviço de estatística oficial da União Europeia"
    base_url = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
    domains = frozenset({Domain.ECONOMY_STATISTICS, Domain.HEALTH_SCIENCE})

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        indicators = [i for i in indicators_for(query) if i.key in EUROSTAT_DATASETS]
        text = " ".join([*query.keywords, *query.keywords_en, *query.topics])
        geos = [iso for iso in claim_countries(query) if iso in EU_MEMBERS]
        if mentions_eu(text):
            geos.append(EU_AGGREGATE)
        if not indicators or not geos:
            return []
        evidence = []
        for indicator in indicators:
            dataset, filters = EUROSTAT_DATASETS[indicator.key]
            for geo in geos[:2]:
                code = _EUROSTAT_GEO.get(geo, geo)
                payload = await self._get_json(
                    f"/{dataset}", {"geo": code, "lang": "en", "lastTimePeriod": 5, **filters}
                )
                points = _jsonstat_points(payload)
                if not points:
                    continue
                unit = indicator.unit
                if indicator.key == "gdp":  # Eurostat gives million euro
                    excerpt = "; ".join(f"{p}: {_billions(v / 1000, '€')}" for p, v in points)
                else:
                    excerpt = _series_text(points, unit)
                label = (payload or {}).get("label", dataset)
                name = "União Europeia (27)" if geo == EU_AGGREGATE else geo
                evidence.append(
                    self._evidence(
                        title=f"{indicator.label} - {name} (Eurostat: {label})",
                        url=f"https://ec.europa.eu/eurostat/databrowser/view/{dataset}/default/table",
                        excerpt=excerpt,
                        published_at=_period_end(points[0][0]),
                        identifiers={"eurostat_dataset": dataset, "geo": code},
                        data={"series": dict(points), "unit": unit or "EUR"},
                    )
                )
        return evidence[: query.max_results]


def _jsonstat_points(payload: Any) -> list[tuple[str, float]]:
    """Newest-first (period, value) pairs of a single-series JSON-stat answer."""
    if not isinstance(payload, dict):
        return []
    values = payload.get("value") or {}
    index = (((payload.get("dimension") or {}).get("time") or {}).get("category") or {}).get(
        "index"
    ) or {}
    points = [(period, float(values[str(pos)])) for period, pos in index.items()
              if str(pos) in values]  # fmt: skip
    return sorted(points, key=lambda p: p[0], reverse=True)


def _period_end(period: str) -> date | None:
    try:
        return date(int(period[:4]), 12, 31)
    except ValueError:
        return None
