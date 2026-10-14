"""Câmara dos Deputados - Dados Abertos API v2.

Docs: https://dadosabertos.camara.leg.br/swagger/api.html
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.connectors.base import BaseGovConnector, truncate
from app.schemas.evidence import Country, Evidence, EvidenceQuery

PROPOSICAO_WEB_URL = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={id}"
DEPUTADO_WEB_URL = "https://www.camara.leg.br/deputados/{id}"


class _CamaraModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CamaraProposicao(_CamaraModel):
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


class CamaraDeputado(_CamaraModel):
    id: int
    nome: str
    sigla_partido: str | None = Field(default=None, alias="siglaPartido")
    sigla_uf: str | None = Field(default=None, alias="siglaUf")


class CamaraDiscurso(_CamaraModel):
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
                    Evidence(
                        connector=self.source_id,
                        country=self.country,
                        publisher=self.publisher,
                        title=f"Proposição {prop.label}",
                        url=prop.web_url,
                        excerpt=truncate(prop.ementa),
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
                    Evidence(
                        connector=self.source_id,
                        country=self.country,
                        publisher=self.publisher,
                        title=(
                            f"Discurso de {dep.nome} ({dep.sigla_partido}-{dep.sigla_uf}) "
                            f"em {(disc.data_hora_inicio or '')[:10]}"
                        ),
                        url=disc.url_texto or DEPUTADO_WEB_URL.format(id=dep.id),
                        excerpt=truncate(disc.sumario or disc.transcricao),
                        data={"deputado_id": dep.id, "tipo": disc.tipo_discurso},
                    )
                )
        return evidence


def _dados(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("dados"), list):
        return payload["dados"]
    return []
