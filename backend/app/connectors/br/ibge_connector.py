"""IBGE - Serviço de Dados (servicodados.ibge.gov.br).

* v1: localidades (``/api/v1/localidades``);
* v3: SIDRA aggregates (``/api/v3/agregados``), used for economic and population indicators.

Note: the former v1 live population projection (``/api/v1/projecoes/populacao``) now returns 404,
so population figures come from SIDRA table 6579 (official annual estimates).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.connectors.base import BaseGovConnector
from app.schemas.evidence import Country, Evidence, EvidenceQuery

PeriodKind = Literal["monthly", "quarterly", "yearly"]


@dataclass(frozen=True, slots=True)
class IbgeIndicator:
    key: str
    label: str
    agregado: int
    variavel: int
    periodos: str  # SIDRA syntax, e.g. "-12" = last 12 periods
    period_kind: PeriodKind
    triggers: tuple[str, ...]

    @property
    def sidra_url(self) -> str:
        return f"https://sidra.ibge.gov.br/tabela/{self.agregado}"


#: Curated catalog of high-signal indicators frequently cited in public debate.
INDICATORS: tuple[IbgeIndicator, ...] = (
    IbgeIndicator(
        key="ipca_12m",
        label="IPCA - variação acumulada em 12 meses (%)",
        agregado=1737,
        variavel=2265,
        periodos="-12",
        period_kind="monthly",
        triggers=("inflacao", "ipca", "precos", "custo de vida"),
    ),
    IbgeIndicator(
        key="desocupacao",
        label="Taxa de desocupação - PNAD Contínua trimestral (%)",
        agregado=4099,
        variavel=4099,
        periodos="-4",
        period_kind="quarterly",
        triggers=("desemprego", "desocupacao", "desempregados", "emprego"),
    ),
    IbgeIndicator(
        key="populacao",
        label="População residente estimada (pessoas)",
        agregado=6579,
        variavel=9324,
        periodos="-3",
        period_kind="yearly",
        triggers=("populacao", "habitantes", "demografia", "demografic"),
    ),
)


class IbgeSeriesPoint(BaseModel):
    localidade: str
    periodo: str
    valor: float | None


class IbgeConnector(BaseGovConnector):
    source_id = "br.ibge"
    country = Country.BR
    publisher = "IBGE - Instituto Brasileiro de Geografia e Estatística"
    base_url = "https://servicodados.ibge.gov.br/api"

    async def list_estados(self) -> list[dict[str, Any]]:
        payload = await self._get_json("/v1/localidades/estados", {"orderBy": "nome"})
        return payload if isinstance(payload, list) else []

    async def get_aggregate_series(
        self,
        agregado: int,
        variavel: int,
        periodos: str = "-12",
        localidades: str = "N1[all]",
    ) -> list[IbgeSeriesPoint]:
        payload = await self._get_json(
            f"/v3/agregados/{int(agregado)}/periodos/{periodos}/variaveis/{int(variavel)}",
            {"localidades": localidades},
        )
        points: list[IbgeSeriesPoint] = []
        for variable in payload if isinstance(payload, list) else []:
            for resultado in variable.get("resultados", []):
                for serie in resultado.get("series", []):
                    loc = serie.get("localidade", {}).get("nome", "")
                    for periodo, valor in (serie.get("serie") or {}).items():
                        points.append(
                            IbgeSeriesPoint(localidade=loc, periodo=periodo, valor=_to_float(valor))
                        )
        return points

    async def get_indicator(self, indicator: IbgeIndicator) -> list[IbgeSeriesPoint]:
        return await self.get_aggregate_series(
            indicator.agregado, indicator.variavel, indicator.periodos
        )

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        haystack = _normalize(" ".join([*query.keywords, *query.topics]))
        evidence: list[Evidence] = []
        for indicator in INDICATORS:
            if not _matches(haystack, indicator.triggers):
                continue
            points = await self.get_indicator(indicator)
            if not points:
                continue
            series_text = "; ".join(
                f"{format_period(p.periodo, indicator.period_kind)}: {_fmt_value(p.valor)}"
                for p in points
            )
            evidence.append(
                Evidence(
                    connector=self.source_id,
                    country=self.country,
                    publisher=self.publisher,
                    title=f"{indicator.label} - {points[0].localidade or 'Brasil'}",
                    url=indicator.sidra_url,
                    excerpt=series_text,
                    data={
                        "indicator": indicator.key,
                        "agregado": indicator.agregado,
                        "variavel": indicator.variavel,
                        "period_kind": indicator.period_kind,
                        "series": {p.periodo: p.valor for p in points},
                    },
                )
            )
        return evidence[: query.max_results]


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def _matches(haystack: str, triggers: tuple[str, ...]) -> bool:
    return any(re.search(rf"\b{re.escape(t)}", haystack) for t in triggers)


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None  # IBGE uses markers like "-" or "..." for missing values


def _fmt_value(value: float | None) -> str:
    if value is None:
        return "n/d"
    if value.is_integer() and abs(value) >= 1000:
        return f"{int(value):,}".replace(",", ".")
    return f"{value:g}"


def format_period(periodo: str, kind: PeriodKind) -> str:
    """SIDRA period codes: 202605 (monthly) -> 05/2026; 202601 (quarterly) -> 1º tri/2026."""
    if kind == "monthly" and len(periodo) == 6:
        return f"{periodo[4:]}/{periodo[:4]}"
    if kind == "quarterly" and len(periodo) == 6:
        return f"{int(periodo[4:])}º tri/{periodo[:4]}"
    return periodo
