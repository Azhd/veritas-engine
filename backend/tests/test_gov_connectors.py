"""Government connectors: resilience (timeout/retry/backoff), caching and Pydantic parsing."""

from __future__ import annotations

import httpx
import pytest

from app.connectors.base import TTLCache
from app.connectors.br_gov import CamaraConnector, IbgeConnector, format_period
from app.connectors.fr_gov import DataGouvConnector
from app.connectors.registry import build_connectors
from app.core.errors import ConnectorHTTPError, ConnectorUnavailableError
from app.schemas.evidence import Country, EvidenceQuery
from tests.conftest import SleepRecorder, json_response, make_settings, mock_client

CAMARA_PROPOSICOES = {
    "dados": [
        {
            "id": 2345678,
            "uri": "https://dadosabertos.camara.leg.br/api/v2/proposicoes/2345678",
            "siglaTipo": "PEC",
            "codTipo": 136,
            "numero": 45,
            "ano": 2019,
            "ementa": "Altera o Sistema Tributário Nacional e dá outras providências.",
        }
    ],
    "links": [],
}
CAMARA_DEPUTADOS = {
    "dados": [{"id": 204554, "nome": "Fulano de Tal", "siglaPartido": "XYZ", "siglaUf": "SP"}]
}
CAMARA_DISCURSOS = {
    "dados": [
        {
            "dataHoraInicio": "2026-05-10T14:00",
            "tipoDiscurso": "BREVES COMUNICAÇÕES",
            "sumario": "Defende a reforma tributária.",
            "transcricao": "Sr. Presidente...",
            "urlTexto": "https://www.camara.leg.br/notas/123",
        }
    ]
}
IBGE_IPCA = [
    {
        "id": "2265",
        "variavel": "IPCA - Variação acumulada em 12 meses",
        "unidade": "%",
        "resultados": [
            {
                "classificacoes": [],
                "series": [
                    {
                        "localidade": {"id": "1", "nivel": {"id": "N1"}, "nome": "Brasil"},
                        "serie": {"202607": "4.12", "202608": "4,30", "202609": "..."},
                    }
                ],
            }
        ],
    }
]
IBGE_POPULACAO = [
    {
        "id": "9324",
        "variavel": "População residente estimada",
        "unidade": "Pessoas",
        "resultados": [
            {
                "classificacoes": [],
                "series": [
                    {
                        "localidade": {"id": "1", "nivel": {"id": "N1"}, "nome": "Brasil"},
                        "serie": {"2025": "213421037", "2026": "214211951"},
                    }
                ],
            }
        ],
    }
]
DATA_GOUV_DATASETS = {
    "data": [
        {
            "id": "abc123",
            "title": "Taux de chômage localisé",
            "slug": "taux-de-chomage",
            "description": "Taux de chômage par zone d'emploi, publié par l'INSEE.",
            "page": "https://www.data.gouv.fr/fr/datasets/taux-de-chomage/",
            "last_modified": "2026-09-01T00:00:00",
            "organization": {"name": "INSEE"},
            "resources": [
                {"id": "r1", "title": "CSV", "url": "https://x/chomage.csv", "format": "csv"}
            ],
        }
    ],
    "total": 1,
}


def _connector(cls, handler, **kwargs):
    kwargs.setdefault("sleep", SleepRecorder())
    return cls(mock_client(handler), **kwargs)


# =============================================================== TTL cache
class TestTTLCache:
    def test_expiry_and_lru_eviction(self):
        now = [0.0]
        cache = TTLCache(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.get("a") == 1  # "a" becomes most recently used
        cache.set("c", 3)  # evicts "b"
        assert cache.get("b") is None
        assert cache.get("a") == 1 and cache.get("c") == 3
        now[0] = 11
        assert cache.get("a") is None
        assert len(cache) == 1  # expired "a" purged on access

    def test_zero_ttl_disables_cache(self):
        cache = TTLCache(ttl_seconds=0)
        cache.set("a", 1)
        assert cache.get("a") is None


# =============================================================== base resilience
class TestResilience:
    async def test_retries_5xx_with_exponential_backoff_then_succeeds(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503)
            return json_response(DATA_GOUV_DATASETS)

        sleep = SleepRecorder()
        conn = _connector(DataGouvConnector, handler, backoff_base_seconds=0.5, sleep=sleep)
        datasets = await conn.search_datasets("chômage")
        assert calls["n"] == 3
        assert sleep.delays == [0.5, 1.0]
        assert datasets[0].title == "Taux de chômage localisé"

    async def test_retries_timeouts_and_gives_up(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            raise httpx.ReadTimeout("slow", request=request)

        sleep = SleepRecorder()
        conn = _connector(CamaraConnector, handler, max_retries=2, sleep=sleep)
        with pytest.raises(ConnectorUnavailableError, match="timeout"):
            await conn.search_proposicoes("reforma")
        assert calls["n"] == 3
        assert sleep.delays == [0.5, 1.0]

    async def test_backoff_is_capped(self):
        sleep = SleepRecorder()
        conn = _connector(
            IbgeConnector,
            lambda r: httpx.Response(502),
            max_retries=4,
            backoff_base_seconds=1,
            backoff_max_seconds=3,
            sleep=sleep,
        )
        with pytest.raises(ConnectorUnavailableError):
            await conn.list_estados()
        assert sleep.delays == [1, 2, 3, 3]

    async def test_honors_retry_after_on_429(self):
        responses = [
            httpx.Response(429, headers={"Retry-After": "2"}),
            json_response(CAMARA_PROPOSICOES),
        ]
        sleep = SleepRecorder()
        conn = _connector(CamaraConnector, lambda r: responses.pop(0), sleep=sleep)
        await conn.search_proposicoes("reforma")
        assert sleep.delays == [2.0]

    async def test_client_errors_are_not_retried(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(404)

        conn = _connector(CamaraConnector, handler)
        with pytest.raises(ConnectorHTTPError) as exc_info:
            await conn.get_proposicao(1)
        assert exc_info.value.status == 404
        assert calls["n"] == 1

    async def test_invalid_json_raises(self):
        conn = _connector(DataGouvConnector, lambda r: httpx.Response(200, content=b"<html>"))
        with pytest.raises(ConnectorHTTPError, match="invalid JSON"):
            await conn.search_datasets("x")

    async def test_responses_are_cached(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return json_response(DATA_GOUV_DATASETS)

        conn = _connector(DataGouvConnector, handler)
        await conn.search_datasets("chômage", limit=3)
        await conn.search_datasets("chômage", limit=3)
        assert calls["n"] == 1
        await conn.search_datasets("chômage", limit=4)  # different params -> new request
        assert calls["n"] == 2

    async def test_errors_are_not_cached(self):
        responses = [httpx.Response(404), json_response(DATA_GOUV_DATASETS)]
        conn = _connector(DataGouvConnector, lambda r: responses.pop(0))
        with pytest.raises(ConnectorHTTPError):
            await conn.search_datasets("x")
        assert len(await conn.search_datasets("x")) == 1

    async def test_timeout_is_passed_to_requests(self):
        seen = {}

        def handler(request):
            seen.update(request.extensions["timeout"])
            return json_response({"dados": []})

        conn = _connector(CamaraConnector, handler, timeout_seconds=8.0)
        await conn.search_proposicoes("x")
        assert seen["read"] == 8.0 and seen["connect"] == 8.0


# =============================================================== Câmara
class TestCamaraConnector:
    async def test_search_proposicoes_params_and_parsing(self):
        seen: list[httpx.URL] = []

        def handler(request):
            seen.append(request.url)
            return json_response(CAMARA_PROPOSICOES)

        conn = _connector(CamaraConnector, handler)
        props = await conn.search_proposicoes("reforma tributária", limit=3)
        assert props[0].label == "PEC 45/2019"
        assert props[0].web_url.endswith("idProposicao=2345678")
        url = seen[0]
        assert url.host == "dadosabertos.camara.leg.br"
        assert url.path == "/api/v2/proposicoes"
        assert url.params["keywords"] == "reforma tributária"
        assert url.params["itens"] == "3"
        assert "dataApresentacaoInicio" in url.params

    async def test_search_evidence_includes_speeches_for_people(self):
        def handler(request):
            path = request.url.path
            if path.endswith("/proposicoes"):
                return json_response(CAMARA_PROPOSICOES)
            if path.endswith("/deputados"):
                assert request.url.params["nome"] == "Fulano"
                return json_response(CAMARA_DEPUTADOS)
            if path.endswith("/204554/discursos"):
                return json_response(CAMARA_DISCURSOS)
            return httpx.Response(404)

        conn = _connector(CamaraConnector, handler)
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["reforma", "tributária"], people=["Fulano"])
        )
        assert [e.connector for e in evidence] == ["br.camara", "br.camara"]
        assert evidence[0].title == "Proposição PEC 45/2019"
        assert "Fulano de Tal (XYZ-SP)" in evidence[1].title
        assert evidence[1].url == "https://www.camara.leg.br/notas/123"
        assert all(e.country is Country.BR for e in evidence)

    async def test_unexpected_payload_shape_yields_no_results(self):
        conn = _connector(CamaraConnector, lambda r: json_response({"unexpected": True}))
        assert await conn.search_proposicoes("x") == []


# =============================================================== IBGE
class TestIbgeConnector:
    async def test_aggregate_series_parsing(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return json_response(IBGE_IPCA)

        conn = _connector(IbgeConnector, handler)
        points = await conn.get_aggregate_series(1737, 2265, "-3")
        assert seen[0].path == "/api/v3/agregados/1737/periodos/-3/variaveis/2265"
        assert seen[0].params["localidades"] == "N1[all]"
        assert [(p.periodo, p.valor) for p in points] == [
            ("202607", 4.12),
            ("202608", 4.30),
            ("202609", None),
        ]

    @pytest.mark.parametrize(
        ("periodo", "kind", "expected"),
        [
            ("202605", "monthly", "05/2026"),
            ("202601", "quarterly", "1º tri/2026"),
            ("2026", "yearly", "2026"),
        ],
    )
    def test_period_formatting(self, periodo, kind, expected):
        assert format_period(periodo, kind) == expected

    async def test_search_evidence_matches_topics(self):
        def handler(request):
            if "/v3/agregados/1737/" in request.url.path:
                return json_response(IBGE_IPCA)
            if "/v3/agregados/6579/" in request.url.path:
                return json_response(IBGE_POPULACAO)
            return httpx.Response(500)

        conn = _connector(IbgeConnector, handler)
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["Inflação"], topics=["população"])
        )
        assert [e.data["indicator"] for e in evidence] == ["ipca_12m", "populacao"]
        assert evidence[0].url == "https://sidra.ibge.gov.br/tabela/1737"
        assert "07/2026: 4.12" in evidence[0].excerpt
        assert "09/2026: n/d" in evidence[0].excerpt
        assert "2026: 214.211.951" in evidence[1].excerpt

    async def test_search_evidence_without_matching_topic_makes_no_calls(self):
        def handler(request):
            raise AssertionError("no HTTP call expected")

        conn = _connector(IbgeConnector, handler)
        assert await conn.search_evidence(EvidenceQuery(keywords=["futebol"])) == []


# =============================================================== data.gouv.fr
class TestDataGouvConnector:
    async def test_search_evidence(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return json_response(DATA_GOUV_DATASETS)

        conn = _connector(DataGouvConnector, handler)
        evidence = await conn.search_evidence(EvidenceQuery(keywords=["chômage", "taux"]))
        assert seen[0].path == "/api/1/datasets/"
        assert seen[0].params["q"] == "chômage taux"
        item = evidence[0]
        assert item.country is Country.FR
        assert item.publisher == "INSEE via data.gouv.fr"
        assert item.url == "https://www.data.gouv.fr/fr/datasets/taux-de-chomage/"
        assert item.data["resources"][0]["format"] == "csv"

    async def test_empty_keywords_skip_network(self):
        conn = _connector(DataGouvConnector, lambda r: (_ for _ in ()).throw(AssertionError()))
        assert await conn.search_evidence(EvidenceQuery()) == []

    async def test_get_dataset_validates_model(self):
        payload = DATA_GOUV_DATASETS["data"][0] | {"page": None}
        conn = _connector(DataGouvConnector, lambda r: json_response(payload))
        dataset = await conn.get_dataset("abc123")
        assert dataset.web_url == "https://www.data.gouv.fr/fr/datasets/taux-de-chomage/"


# =============================================================== registry
async def test_registry_shares_client_and_cache():
    settings = make_settings(connector_timeout_seconds=5, connector_max_retries=1)
    connectors, client = build_connectors(settings)
    try:
        ids = [c.source_id for c in connectors]
        assert len(ids) == len(set(ids)) == 23
        assert {"br.camara", "br.senado", "br.ibge", "fr.data_gouv", "fr.insee"} <= set(ids)
        assert len({id(c.cache) for c in connectors}) == 1
        assert all(c.timeout_seconds == 5 for c in connectors)
        retries = {c.source_id: c.max_retries for c in connectors}
        assert retries.pop("geo.gdelt") == 0  # GDELT policy: 1 request / 5 s, never retried
        assert set(retries.values()) == {1}
        disabled = {c.source_id for c in connectors if not c.enabled}
        # Only sources that need credentials are disabled by default (zero-cost first).
        assert disabled == {
            "br.transparencia",
            "fr.legifrance",
            "fr.judilibre",
            "geo.reliefweb",
            "factcheck.google",
        }
    finally:
        await client.aclose()


async def test_registry_enables_credentialed_sources_when_configured():
    settings = make_settings(
        reliefweb_appname="veritas-approved",
        transparencia_api_key="cgu-key",
        piste_client_id="id",
        piste_client_secret="secret",
        google_factcheck_api_key="g-key",
    )
    connectors, client = build_connectors(settings)
    try:
        assert all(c.enabled for c in connectors)
        legifrance = next(c for c in connectors if c.source_id == "fr.legifrance")
        judilibre = next(c for c in connectors if c.source_id == "fr.judilibre")
        assert legifrance._auth is judilibre._auth  # one shared PISTE token cache
    finally:
        await client.aclose()
