"""Climate primary sources (keyless).

* Copernicus Climate Change Service (C3S / ECMWF) - ERA5 daily global mean near-surface air
  temperature published by "Climate Pulse" (CSV, 1940 to ~3 days ago).
* NOAA NCEI "Climate at a Glance" - annual global land+ocean temperature departures (JSON).

Both are reduced to what claims usually cite: annual means, the ranking of the warmest years and
whether recent years set consecutive records.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.connectors.base import BaseGovConnector
from app.connectors.br_gov import normalize
from app.core.config import Settings
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

COPERNICUS_CSV_URL = (
    "https://sites.ecmwf.int/data/climatepulse/data/series/era5_daily_series_2t_global.csv"
)
COPERNICUS_PAGE = "https://pulse.climate.copernicus.eu/"
NOAA_URL = (
    "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series/"
    "globe/land_ocean/12/12/1850-{year}/data.json"
)
NOAA_PAGE = "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series"

#: The temperature series only answer temperature questions (not e.g. deforestation claims).
TEMPERATURE_TRIGGERS = (
    "temperatur", "aquec", "rechauff", "warming", "calor", "chaleur", "heat", "quente",
    "chaud", "hot", "recorde", "record", "clima", "climat", "climate", "el nino", "1,5",
    "1.5", "graus", "degre", "copernicus", "noaa", "nasa",
)  # fmt: skip


def mentions_temperature(query: EvidenceQuery) -> bool:
    text = f" {normalize(' '.join([*query.keywords, *query.keywords_en, *query.topics]))} "
    return any(trigger in text for trigger in TEMPERATURE_TRIGGERS)


@dataclass(frozen=True, slots=True)
class YearValue:
    year: int
    value: float  # mean temperature (°C) or anomaly (°C)
    days: int = 365


def record_years(years: list[YearValue]) -> list[int]:
    """Years that beat every earlier year of the series (chronological)."""
    records: list[int] = []
    best = float("-inf")
    for item in years:
        if item.value > best:
            records.append(item.year)
            best = item.value
    return records


def consecutive_records(records: list[int]) -> list[int]:
    """The latest run of back-to-back record years (e.g. [2023, 2024]); empty if none."""
    run: list[int] = []
    for year in reversed(records):
        if not run or run[-1] - year == 1:
            run.append(year)
        elif len(run) >= 2:
            break
        else:
            run = [year]
    return sorted(run) if len(run) >= 2 else []


def describe(years: list[YearValue], unit_label: str) -> tuple[str, dict[str, Any]]:
    ranking = sorted(years, key=lambda y: y.value, reverse=True)
    top = ranking[:5]
    records = record_years(years)
    last = years[-1]
    recent = [y for y in records if y >= last.year - 15]
    consecutive = consecutive_records(records)
    parts = [
        "Anos mais quentes: "
        + "; ".join(f"{y.year}: {y.value:+.2f} °C" for y in top)
        + f" ({unit_label})."
    ]
    if recent:
        parts.append(f"Anos que bateram recorde recentemente: {', '.join(map(str, recent))}.")
    if consecutive:
        parts.append(f"Recordes consecutivos: {' e '.join(map(str, consecutive))}.")
    position = [y.year for y in ranking].index(last.year) + 1
    parts.append(
        f"{last.year} foi o ano mais quente da série."
        if position == 1
        else f"{last.year} (último ano completo) ficou em {position}º lugar."
    )
    data = {
        "ranking_top5": {str(y.year): round(y.value, 3) for y in top},
        "record_years_recent": recent,
        "consecutive_records": consecutive,
        "last_complete_year": last.year,
        "last_complete_year_rank": position,
    }
    return " ".join(parts), data


class CopernicusClimateConnector(BaseGovConnector):
    source_id = "climate.copernicus"
    country = Country.GLOBAL
    publisher = "Copernicus Climate Change Service (C3S) / ECMWF - União Europeia"
    base_url = "https://sites.ecmwf.int"
    domains = frozenset({Domain.CLIMATE_ENVIRONMENT})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        dataset_timeout_seconds: float = 30.0,
        dataset_ttl_seconds: float = 21_600.0,
        **kw: Any,
    ) -> None:
        super().__init__(client, **kw)
        self.dataset_timeout_seconds = dataset_timeout_seconds
        self.dataset_ttl_seconds = dataset_ttl_seconds

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> CopernicusClimateConnector:
        return cls(
            client,
            dataset_timeout_seconds=settings.dataset_timeout_seconds,
            # Daily series: refresh a few times per day at most.
            dataset_ttl_seconds=min(settings.dataset_cache_ttl_seconds, 21_600.0),
            **common,
        )

    async def warm_up(self) -> None:
        await self.daily_series()

    async def daily_series(self) -> list[tuple[date, float, float]]:
        """(day, global mean 2 m temperature °C, anomaly vs 1991-2020 °C)."""
        text = await self._request(
            COPERNICUS_CSV_URL,
            kind="text",
            request_timeout=self.dataset_timeout_seconds,
            cache_ttl=self.dataset_ttl_seconds,
        )
        lines = [line for line in text.splitlines() if line and not line.startswith("#")]
        rows: list[tuple[date, float, float]] = []
        for row in csv.DictReader(io.StringIO("\n".join(lines))):
            try:
                rows.append(
                    (date.fromisoformat(row["date"]), float(row["2t"]), float(row["ano_91-20"]))
                )
            except (KeyError, ValueError):
                continue
        return rows

    async def annual(self) -> tuple[list[YearValue], list[YearValue], tuple[int, int, float]]:
        """Complete-year means (absolute and anomaly) plus the current partial year."""
        sums: dict[int, list[float]] = {}
        for day, temp, anomaly in await self.daily_series():
            acc = sums.setdefault(day.year, [0.0, 0.0, 0])
            acc[0] += temp
            acc[1] += anomaly
            acc[2] += 1
        complete = sorted(y for y, acc in sums.items() if acc[2] >= 365)
        absolute = [YearValue(y, sums[y][0] / sums[y][2], int(sums[y][2])) for y in complete]
        anomaly = [YearValue(y, sums[y][1] / sums[y][2], int(sums[y][2])) for y in complete]
        partial_year = max(sums) if sums and max(sums) not in complete else 0
        partial = (0, 0, 0.0)
        if partial_year:
            days = int(sums[partial_year][2])
            partial = (partial_year, days, sums[partial_year][1] / days)
        return absolute, anomaly, partial

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        if not mentions_temperature(query):
            return []
        absolute, anomaly, (p_year, p_days, p_anomaly) = await self.annual()
        if not anomaly:
            return []
        summary, data = describe(anomaly, "anomalia vs. 1991-2020")
        last = absolute[-1]
        excerpt = (
            f"Média global anual da temperatura do ar (ERA5): {last.year} = {last.value:.2f} °C. "
            f"{summary}"
        )
        if p_year:
            excerpt += (
                f" {p_year} até agora ({p_days} dias): {p_anomaly:+.2f} °C acima da média "
                "1991-2020."
            )
        data.update({"absolute_last_year_c": round(last.value, 3), "partial_year": p_year or None})
        return [
            self._evidence(
                title="Copernicus (ERA5): temperatura média global por ano",
                url=COPERNICUS_PAGE,
                excerpt=excerpt,
                venue="Copernicus Climate Pulse",
                published_at=date(last.year, 12, 31),
                identifiers={"dataset": "ERA5 2t global daily"},
                data=data,
            )
        ]


class NoaaClimateConnector(BaseGovConnector):
    source_id = "climate.noaa"
    country = Country.GLOBAL
    publisher = "NOAA National Centers for Environmental Information (EUA)"
    base_url = "https://www.ncei.noaa.gov"
    domains = frozenset({Domain.CLIMATE_ENVIRONMENT})

    async def annual(self) -> list[YearValue]:
        payload = await self._get_json(NOAA_URL.format(year=date.today().year))
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        years = []
        for year, item in data.items():
            if re.fullmatch(r"\d{4}", year) and isinstance(item, dict):
                try:
                    years.append(YearValue(int(year), float(item["departure"])))
                except (KeyError, TypeError, ValueError):
                    continue
        return sorted(years, key=lambda y: y.year)

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        if not mentions_temperature(query):
            return []
        years = await self.annual()
        if not years:
            return []
        summary, data = describe(years, "anomalia vs. média do século XX")
        return [
            self._evidence(
                title="NOAA: anomalia da temperatura global (terra + oceano) por ano",
                url=NOAA_PAGE,
                excerpt=summary,
                venue="NOAA Climate at a Glance",
                published_at=date(years[-1].year, 12, 31),
                identifiers={"series": "global land_ocean annual"},
                data=data,
            )
        ]
