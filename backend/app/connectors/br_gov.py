"""Brazilian government primary sources.

* Câmara dos Deputados - Dados Abertos API v2 (proposições, deputados, discursos)
* Senado Federal - Dados Abertos (processos legislativos)
* IBGE - Serviço de Dados (v1 localidades, v3 agregados SIDRA)
* Portal da Transparência (CGU) - emendas parlamentares (requires a free API key)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.connectors.base import BaseGovConnector, truncate
from app.core.config import Settings
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery


def normalize(text: str) -> str:
    """Lowercase and strip accents (for keyword matching)."""
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def parse_br_date(value: str | None) -> date | None:
    """Accept ISO (2026-05-10, 2026-05-10T14:00) and Brazilian (10/05/2026) dates."""
    if not value:
        return None
    value = value.strip()
    try:
        if re.match(r"^\d{2}/\d{2}/\d{4}", value):
            day, month, year = value[:10].split("/")
            return date(int(year), int(month), int(day))
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


# =====================================================================================
# Câmara dos Deputados
# =====================================================================================
PROPOSICAO_WEB_URL = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id}"
DEPUTADO_WEB_URL = "https://www.camara.leg.br/deputados/{id}"


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CamaraProposicao(_ApiModel):
    id: int
    uri: str | None = None
    sigla_tipo: str = Field(alias="siglaTipo")
    numero: int
    ano: int
    ementa: str = ""

    @property
    def label(self) -> str:
        return f"{self.sigla_tipo} {self.numero}/{self.ano}"

    @property
    def web_url(self) -> str:
        return PROPOSICAO_WEB_URL.format(id=self.id)


class CamaraDeputado(_ApiModel):
    id: int
    nome: str
    sigla_partido: str | None = Field(default=None, alias="siglaPartido")
    sigla_uf: str | None = Field(default=None, alias="siglaUf")


class CamaraDiscurso(_ApiModel):
    data_hora_inicio: str | None = Field(default=None, alias="dataHoraInicio")
    tipo_discurso: str | None = Field(default=None, alias="tipoDiscurso")
    sumario: str | None = None
    transcricao: str | None = None
    keywords: str | None = None
    url_texto: str | None = Field(default=None, alias="urlTexto")


class CamaraConnector(BaseGovConnector):
    source_id = "br.camara"
    country = Country.BR
    publisher = "Câmara dos Deputados"
    base_url = "https://dadosabertos.camara.leg.br/api/v2"
    domains = frozenset({Domain.POLITICS_LEGISLATION})

    #: The API only returns recent items when no date filter is given; widen the window.
    proposicoes_lookback_years = 6
    discursos_lookback_days = 365

    async def search_proposicoes(
        self, keywords: str, *, limit: int = 5, since: date | None = None
    ) -> list[CamaraProposicao]:
        since = since or date.today() - timedelta(days=365 * self.proposicoes_lookback_years)
        payload = await self._get_json(
            "/proposicoes",
            {
                "keywords": keywords,
                "dataApresentacaoInicio": since.isoformat(),
                "ordem": "DESC",
                "ordenarPor": "id",
                "itens": limit,
            },
        )
        return [CamaraProposicao.model_validate(item) for item in _dados(payload)]

    async def get_proposicao(self, proposicao_id: int) -> dict[str, Any]:
        payload = await self._get_json(f"/proposicoes/{int(proposicao_id)}")
        return payload.get("dados", {}) if isinstance(payload, dict) else {}

    async def search_deputados(self, nome: str, *, limit: int = 3) -> list[CamaraDeputado]:
        payload = await self._get_json(
            "/deputados", {"nome": nome, "ordem": "ASC", "ordenarPor": "nome", "itens": limit}
        )
        return [CamaraDeputado.model_validate(item) for item in _dados(payload)]

    async def get_discursos(
        self,
        deputado_id: int,
        *,
        since: date | None = None,
        until: date | None = None,
        limit: int = 5,
    ) -> list[CamaraDiscurso]:
        since = since or date.today() - timedelta(days=self.discursos_lookback_days)
        payload = await self._get_json(
            f"/deputados/{int(deputado_id)}/discursos",
            {
                "dataInicio": since.isoformat(),
                "dataFim": (until or date.today()).isoformat(),
                "ordenarPor": "dataHoraInicio",
                "ordem": "DESC",
                "itens": limit,
            },
        )
        return [CamaraDiscurso.model_validate(item) for item in _dados(payload)]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        evidence: list[Evidence] = []
        if query.keywords:
            for prop in await self.search_proposicoes(query.text, limit=query.max_results):
                evidence.append(
                    self._evidence(
                        title=f"Proposição {prop.label}",
                        url=prop.web_url,
                        excerpt=truncate(prop.ementa),
                        identifiers={"proposicao": prop.label, "id_camara": str(prop.id)},
                        data={"id": prop.id, "tipo": prop.sigla_tipo, "ano": prop.ano},
                    )
                )
        # Speeches are only fetched for explicitly named people (bounded fan-out).
        for name in query.people[:2]:
            deputados = await self.search_deputados(name, limit=1)
            if not deputados:
                continue
            dep = deputados[0]
            for disc in await self.get_discursos(dep.id, limit=min(query.max_results, 3)):
                evidence.append(
                    self._evidence(
                        title=(
                            f"Discurso de {dep.nome} ({dep.sigla_partido}-{dep.sigla_uf}) "
                            f"em {(disc.data_hora_inicio or '')[:10]}"
                        ),
                        url=disc.url_texto or DEPUTADO_WEB_URL.format(id=dep.id),
                        excerpt=truncate(disc.sumario or disc.transcricao),
                        authors=[dep.nome],
                        published_at=parse_br_date(disc.data_hora_inicio),
                        data={"deputado_id": dep.id, "tipo": disc.tipo_discurso},
                    )
                )
        return evidence


def _dados(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("dados"), list):
        return payload["dados"]
    return []


# =====================================================================================
# Senado Federal
# =====================================================================================
SENADO_MATERIA_URL = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}"
LEGISLATIVE_TYPES = frozenset({"PEC", "PL", "PLP", "PLS", "PLC", "PLV", "MPV", "PDL", "PRS"})


class SenadoProcesso(_ApiModel):
    id: int | None = None
    codigo_materia: int | None = Field(default=None, alias="codigoMateria")
    identificacao: str
    ementa: str = ""
    autoria: str | None = None
    data_apresentacao: str | None = Field(default=None, alias="dataApresentacao")
    situacao_atual: str | None = Field(default=None, alias="situacaoAtual")
    tramitando: str | None = None
    url_documento: str | None = Field(default=None, alias="urlDocumento")

    @property
    def web_url(self) -> str:
        if self.codigo_materia:
            return SENADO_MATERIA_URL.format(codigo=self.codigo_materia)
        return self.url_documento or "https://www25.senado.leg.br/web/atividade/materias"


class SenadoConnector(BaseGovConnector):
    """Senado Federal - ``/dadosabertos/processo`` (replaces the decommissioned
    ``/materia/pesquisa/lista`` service)."""

    source_id = "br.senado"
    country = Country.BR
    publisher = "Senado Federal"
    base_url = "https://legis.senado.leg.br/dadosabertos"
    domains = frozenset({Domain.POLITICS_LEGISLATION})

    async def search_processos(self, termo: str, *, limit: int = 5) -> list[SenadoProcesso]:
        payload = await self._get_json("/processo", {"termo": termo})
        items = payload if isinstance(payload, list) else []
        processos = [SenadoProcesso.model_validate(item) for item in items]
        # Bills and constitutional amendments first; procedural requests (REQ...) last.
        processos.sort(key=lambda p: p.data_apresentacao or "", reverse=True)
        processos.sort(key=lambda p: p.identificacao.split(" ")[0] not in LEGISLATIVE_TYPES)
        return processos[:limit]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        if not query.keywords:
            return []
        return [
            self._evidence(
                title=f"Matéria {proc.identificacao} (Senado)",
                url=proc.web_url,
                excerpt=truncate(proc.ementa),
                authors=[proc.autoria] if proc.autoria else [],
                published_at=parse_br_date(proc.data_apresentacao),
                identifiers={"materia": proc.identificacao},
                data={"situacao": proc.situacao_atual, "tramitando": proc.tramitando},
            )
            for proc in await self.search_processos(query.text, limit=query.max_results)
        ]


# =====================================================================================
# IBGE
# =====================================================================================
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
#: (The v1 live population projection endpoint now returns 404, so population comes from
#: SIDRA table 6579 - official annual estimates.)
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
    domains = frozenset({Domain.ECONOMY_STATISTICS})

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
        haystack = normalize(" ".join([*query.keywords, *query.topics]))
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
                self._evidence(
                    title=f"{indicator.label} - {points[0].localidade or 'Brasil'}",
                    url=indicator.sidra_url,
                    excerpt=series_text,
                    identifiers={"sidra_tabela": str(indicator.agregado)},
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


# =====================================================================================
# Portal da Transparência (CGU)
# =====================================================================================
TRANSPARENCIA_EMENDAS_URL = "https://portaldatransparencia.gov.br/emendas/consulta"


class TransparenciaEmenda(_ApiModel):
    codigo_emenda: str | None = Field(default=None, alias="codigoEmenda")
    ano: int | None = None
    tipo_emenda: str | None = Field(default=None, alias="tipoEmenda")
    nome_autor: str | None = Field(default=None, alias="nomeAutor")
    numero_emenda: str | None = Field(default=None, alias="numeroEmenda")
    localidade_do_gasto: str | None = Field(default=None, alias="localidadeDoGasto")
    funcao: str | None = None
    subfuncao: str | None = None
    valor_empenhado: str | None = Field(default=None, alias="valorEmpenhado")
    valor_pago: str | None = Field(default=None, alias="valorPago")


class TransparenciaConnector(BaseGovConnector):
    """Parliamentary amendments (emendas) by author. Requires ``VERITAS_TRANSPARENCIA_API_KEY``."""

    source_id = "br.transparencia"
    country = Country.BR
    publisher = "Portal da Transparência - Controladoria-Geral da União (CGU)"
    base_url = "https://api.portaldatransparencia.gov.br/api-de-dados"
    domains = frozenset({Domain.POLITICS_LEGISLATION, Domain.ECONOMY_STATISTICS})

    def __init__(
        self, client: httpx.AsyncClient | None = None, *, api_key: SecretStr | None = None, **kw
    ) -> None:
        super().__init__(client, **kw)
        self._api_key = api_key

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> TransparenciaConnector:
        return cls(client, api_key=settings.transparencia_api_key, **common)

    @property
    def disabled_reason(self) -> str | None:
        if not self._api_key or not self._api_key.get_secret_value():
            return "requires VERITAS_TRANSPARENCIA_API_KEY (free CGU key)"
        return None

    async def _auth_headers(self) -> dict[str, str]:
        return {"chave-api-dados": self._api_key.get_secret_value()} if self._api_key else {}

    async def search_emendas(
        self, nome_autor: str, *, ano: int | None = None, limit: int = 5
    ) -> list[TransparenciaEmenda]:
        payload = await self._get_json(
            "/emendas", {"nomeAutor": nome_autor, "ano": ano or date.today().year, "pagina": 1}
        )
        items = payload if isinstance(payload, list) else []
        return [TransparenciaEmenda.model_validate(item) for item in items[:limit]]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        evidence: list[Evidence] = []
        for name in query.people[:2]:
            for em in await self.search_emendas(name, limit=query.max_results):
                evidence.append(
                    self._evidence(
                        title=f"Emenda {em.numero_emenda or em.codigo_emenda} ({em.ano}) - "
                        f"{em.nome_autor}",
                        url=TRANSPARENCIA_EMENDAS_URL,
                        excerpt=(
                            f"{em.tipo_emenda or 'Emenda'}; função {em.funcao or 'n/d'}; "
                            f"local {em.localidade_do_gasto or 'n/d'}; empenhado R$ "
                            f"{em.valor_empenhado or 'n/d'}; pago R$ {em.valor_pago or 'n/d'}."
                        ),
                        authors=[em.nome_autor] if em.nome_autor else [],
                        identifiers={"emenda": str(em.codigo_emenda or em.numero_emenda)},
                        data=em.model_dump(),
                    )
                )
        return evidence
