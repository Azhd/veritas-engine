"""Consolidated BR/FR government connectors added in Phase 2 (Senado, Transparência, INSEE,
Légifrance) and the shared PISTE OAuth client. HTTP fully mocked."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.connectors.br_gov import SenadoConnector, TransparenciaConnector
from app.connectors.fr_gov import InseeConnector, LegifranceConnector
from app.connectors.piste import PisteAuth
from app.core.errors import ConnectorHTTPError
from app.schemas.evidence import Country, EvidenceQuery
from tests.conftest import SleepRecorder, json_response, mock_client


def _connector(cls, handler, **kwargs):
    kwargs.setdefault("sleep", SleepRecorder())
    return cls(mock_client(handler), **kwargs)


# =============================================================== Senado (processo)
SENADO_PROCESSOS = [
    {
        "codigoMateria": 145389,
        "identificacao": "PL 5108/2020",
        "ementa": "Institui o Sistema de Metas de Emprego.",
        "autoria": "Senador Fulano (PSD/BA)",
        "dataApresentacao": "2020-11-05",
        "situacaoAtual": "MATÉRIA COM A RELATORIA",
        "tramitando": "Sim",
    },
    {
        "codigoMateria": 156453,
        "identificacao": "PEC 45/2019",
        "ementa": "Altera o Sistema Tributário Nacional.",
        "dataApresentacao": "2023-03-23",
    },
]


class TestSenadoConnector:
    async def test_search_sorts_recent_first(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return json_response(SENADO_PROCESSOS)

        conn = _connector(SenadoConnector, handler)
        evidence = await conn.search_evidence(EvidenceQuery(keywords=["reforma tributária"]))
        assert seen[0].path == "/dadosabertos/processo"
        assert seen[0].params["termo"] == "reforma tributária"
        assert [e.identifiers["materia"] for e in evidence] == ["PEC 45/2019", "PL 5108/2020"]
        assert evidence[0].url.endswith("/materia/156453")
        assert evidence[1].authors == ["Senador Fulano (PSD/BA)"]
        assert evidence[1].published_at == date(2020, 11, 5)

    async def test_no_keywords_no_call(self):
        conn = _connector(SenadoConnector, lambda r: (_ for _ in ()).throw(AssertionError()))
        assert await conn.search_evidence(EvidenceQuery(people=["x"])) == []


# =============================================================== Portal da Transparência
EMENDAS = [
    {
        "codigoEmenda": "202471230001",
        "ano": 2024,
        "tipoEmenda": "Emenda Individual",
        "nomeAutor": "FULANO DE TAL",
        "numeroEmenda": "0001",
        "localidadeDoGasto": "SÃO PAULO (UF)",
        "funcao": "Saúde",
        "valorEmpenhado": "1.000.000,00",
        "valorPago": "500.000,00",
    }
]


class TestTransparenciaConnector:
    def test_disabled_without_key(self):
        conn = TransparenciaConnector(mock_client(lambda r: httpx.Response(500)))
        assert not conn.enabled
        assert "TRANSPARENCIA_API_KEY" in conn.disabled_reason

    async def test_emendas_by_author_with_key_header(self):
        seen = []

        def handler(request):
            seen.append(request)
            return json_response(EMENDAS)

        conn = _connector(TransparenciaConnector, handler, api_key=SecretStr("cgu-key"))
        assert conn.enabled
        evidence = await conn.search_evidence(EvidenceQuery(people=["Fulano de Tal"]))
        assert seen[0].headers["chave-api-dados"] == "cgu-key"
        assert seen[0].url.params["nomeAutor"] == "Fulano de Tal"
        assert "pago R$ 500.000,00" in evidence[0].excerpt
        assert evidence[0].identifiers == {"emenda": "202471230001"}
        assert await conn.search_evidence(EvidenceQuery(keywords=["sem pessoas"])) == []


# =============================================================== INSEE (Melodi)
MELODI_CATALOG = [
    {
        "identifier": "DS_CHOMAGE_TRIM",
        "title": [
            {"content": "Taux de chômage au sens du BIT", "lang": "fr"},
            {"content": "ILO unemployment rate", "lang": "en"},
        ],
        "subtitle": [{"content": "Données trimestrielles", "lang": "fr"}],
        "abstract": [{"content": "Taux de chômage trimestriel France entière.", "lang": "fr"}],
        "keyword": [{"label": [{"content": "emploi", "lang": "fr"}]}],
        "modified": "2026-08-14T12:00:00",
        "temporal": {"startPeriod": "1975-01-01T00:00:00", "endPeriod": "2026-06-30T00:00:00"},
    },
    {
        "identifier": "DD_CNA_AGREGATS",
        "title": [{"content": "Produit Intérieur Brut (PIB)", "lang": "fr"}],
        "abstract": [{"content": "Comptes nationaux annuels.", "lang": "fr"}],
    },
]


class TestInseeConnector:
    async def test_catalog_search_and_long_cache(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            assert request.url.path == "/melodi/catalog/all"
            return json_response(MELODI_CATALOG)

        conn = _connector(InseeConnector, handler)
        evidence = await conn.search_evidence(EvidenceQuery(keywords=["chômage"]))
        await conn.search_evidence(EvidenceQuery(keywords=["PIB"]))
        assert calls["n"] == 1
        item = evidence[0]
        assert item.title == "Taux de chômage au sens du BIT - Données trimestrielles"
        assert item.identifiers == {"insee_dataset": "DS_CHOMAGE_TRIM"}
        assert "Période couverte: 1975–2026" in item.excerpt
        assert item.country is Country.FR
        assert item.published_at == date(2026, 8, 14)
        assert item.data["data_api"].endswith("/melodi/data/DS_CHOMAGE_TRIM")

    async def test_accent_insensitive_matching(self):
        conn = _connector(InseeConnector, lambda r: json_response(MELODI_CATALOG))
        found = await conn.search_datasets(["chomage"])
        assert [d.identifier for d in found] == ["DS_CHOMAGE_TRIM"]


# =============================================================== Légifrance + PISTE OAuth
LEGIFRANCE_RESULT = {
    "results": [
        {
            "titles": [
                {
                    "id": "LEGITEXT000045",
                    "cid": "JORFTEXT000045",
                    "title": "LOI n° 2023-<b>270</b> du 14 avril 2023",
                }
            ],
            "nature": "LOI",
            "date": 1681430400000,
            "nor": "PRSX2300089L",
            "sections": [{"extracts": [{"values": ["âge légal de <b>départ</b>"]}]}],
        }
    ]
}


def _legifrance(api_handler, token_status: int = 200):
    tokens = {"n": 0}

    def handler(request):
        if request.url.host == "oauth.piste.gouv.fr":
            tokens["n"] += 1
            if token_status != 200:
                return httpx.Response(token_status, text="client_secret=secret invalid")
            return json_response({"access_token": f"tok-{tokens['n']}", "expires_in": 120})
        return api_handler(request)

    client = mock_client(handler)
    now = [0.0]
    auth = PisteAuth(client, SecretStr("id"), SecretStr("secret"), clock=lambda: now[0])
    return LegifranceConnector(client, auth=auth, sleep=SleepRecorder()), tokens, now


class TestLegifranceAndPiste:
    def test_disabled_without_credentials(self):
        client = mock_client(lambda r: httpx.Response(500))
        conn = LegifranceConnector(client, auth=PisteAuth(client, None, None))
        assert not conn.enabled and "PISTE" in conn.disabled_reason

    async def test_search_posts_body_and_maps_results(self):
        bodies = []

        def api(request):
            bodies.append(json.loads(request.content))
            assert request.method == "POST"
            assert request.headers["Authorization"] == "Bearer tok-1"
            return json_response(LEGIFRANCE_RESULT)

        conn, _, _ = _legifrance(api)
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["retraites"], legal_references=["loi 2023-270"])
        )
        body = bodies[0]
        assert body["fond"] == "LODA_DATE"
        assert body["recherche"]["champs"][0]["criteres"][0]["valeur"] == "loi 2023-270 retraites"
        item = evidence[0]
        assert item.title == "LOI n° 2023-270 du 14 avril 2023"
        assert item.url == "https://www.legifrance.gouv.fr/loda/id/JORFTEXT000045"
        assert item.excerpt == "âge légal de départ"
        assert item.identifiers == {"cid": "JORFTEXT000045", "nor": "PRSX2300089L"}
        assert item.published_at == date(2023, 4, 14)

    async def test_token_reused_then_refreshed_after_expiry(self):
        conn, tokens, now = _legifrance(lambda r: json_response({"results": []}))
        await conn.search_texts("a")
        await conn.search_texts("b")
        assert tokens["n"] == 1
        now[0] = 61  # 120 s token minus the 60 s safety margin
        await conn.search_texts("c")
        assert tokens["n"] == 2

    async def test_token_rejection_never_echoes_secret(self):
        conn, _, _ = _legifrance(lambda r: json_response({}), token_status=401)
        with pytest.raises(ConnectorHTTPError) as exc_info:
            await conn.search_texts("a")
        assert "secret" not in str(exc_info.value)
        assert exc_info.value.status == 401
