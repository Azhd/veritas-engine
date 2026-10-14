"""Integration tests: POST /api/v1/fact-check/text end-to-end (HTTP + BYOK + connectors mocked)."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors.br.camara_connector import CamaraConnector
from app.connectors.br.ibge_connector import IbgeConnector
from app.connectors.fr.data_gouv_connector import DataGouvConnector
from app.core.config import ProviderName
from app.core.errors import ProviderAuthenticationError
from app.engines.factory import ProviderFactory
from app.main import create_app
from app.schemas.fact_check import CountryContext
from app.services.fact_checker import FactCheckService, heuristic_country, heuristic_keywords
from tests.conftest import FakeLLMProvider, SleepRecorder, json_response, make_settings
from tests.test_gov_connectors import CAMARA_PROPOSICOES, DATA_GOUV_DATASETS, IBGE_IPCA

ENDPOINT = "/api/v1/fact-check/text"
HEADERS = {"X-Provider": "openai", "X-API-Key": "sk-user-secret-123"}


class ScriptedProvider(FakeLLMProvider):
    """Provider class registered in the factory; outputs are scripted per test."""

    script: ClassVar[list[Any]] = []
    instances: ClassVar[list[ScriptedProvider]] = []

    def __init__(self, credentials):
        super().__init__(credentials, outputs=list(ScriptedProvider.script))
        ScriptedProvider.instances.append(self)


def analysis(country: str = "BR", keywords=None, people=None, topics=None, language="pt") -> str:
    return json.dumps(
        {
            "country": country,
            "keywords": keywords or ["reforma tributária"],
            "people": people or [],
            "topics": topics or [],
            "language": language,
        }
    )


def verdict(v: str = "VERDADEIRO", score: float = 0.9, cited=("E1",), text="Ok [E1]") -> str:
    return json.dumps(
        {
            "verdict": v,
            "confidence_score": score,
            "explanation": text,
            "cited_evidence_ids": list(cited),
        }
    )


class Upstream:
    """Fake government APIs routed by host; records hits."""

    def __init__(self, failing_hosts: set[str] | None = None) -> None:
        self.failing_hosts = failing_hosts or set()
        self.hits: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.hits.append(host)
        if host in self.failing_hosts:
            return httpx.Response(503)
        if host == "dadosabertos.camara.leg.br":
            return json_response(CAMARA_PROPOSICOES)
        if host == "servicodados.ibge.gov.br":
            return json_response(IBGE_IPCA)
        if host == "www.data.gouv.fr":
            return json_response(DATA_GOUV_DATASETS)
        return httpx.Response(404)


@pytest.fixture
def upstream() -> Upstream:
    return Upstream()


@pytest.fixture
def client(upstream):
    ScriptedProvider.script = []
    ScriptedProvider.instances = []
    settings = make_settings(connector_max_retries=1)
    app = create_app(settings)
    http = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    with TestClient(app) as test_client:
        connectors = [
            cls(http, max_retries=1, backoff_base_seconds=0, sleep=SleepRecorder())
            for cls in (CamaraConnector, IbgeConnector, DataGouvConnector)
        ]
        app.state.fact_check_service = FactCheckService(connectors)
        app.state.provider_factory = ProviderFactory(
            settings, registry={ProviderName.OPENAI: ScriptedProvider}
        )
        yield test_client


# =============================================================== happy paths
def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_swagger_and_openapi_available(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert ENDPOINT in paths


def test_full_pipeline_br_claim(client, upstream):
    ScriptedProvider.script = [
        analysis("BR", keywords=["reforma tributária"], topics=["inflação"]),
        verdict("VERDADEIRO", 0.87, cited=["E1", "[e2]"], text="A PEC 45/2019 existe [E1]."),
    ]
    response = client.post(
        ENDPOINT, json={"claim": "A reforma tributária foi aprovada pela Câmara."}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["verdict"] == "VERDADEIRO"
    assert body["confidence_score"] == 0.87
    assert body["country_context"] == "BR"
    assert body["provider"] == "openai"
    assert set(body["connectors_queried"]) == {"br.camara", "br.ibge"}
    assert "www.data.gouv.fr" not in upstream.hits  # FR connector not queried for BR claim

    sources = body["primary_sources"]
    assert [s["evidence_id"] for s in sources] == ["E1", "E2"]
    assert all(s["cited"] for s in sources)
    assert sources[0]["url"].startswith("https://www.camara.leg.br/")
    assert sources[1]["url"] == "https://sidra.ibge.gov.br/tabela/1737"

    # The verdict prompt is grounded on the retrieved evidence.
    llm = ScriptedProvider.instances[0]
    verdict_prompt = llm.calls[1]["prompt"]
    assert "[E1] Proposição PEC 45/2019" in verdict_prompt
    assert "Sistema Tributário Nacional" in verdict_prompt
    assert llm.closed, "provider must be disposed after the request"


def test_fr_claim_queries_only_fr_connectors(client, upstream):
    ScriptedProvider.script = [
        analysis("FR", keywords=["chômage"], language="fr"),
        verdict("ENGANOSO", 0.6, cited=["E1"], text="Les données INSEE [E1]..."),
    ]
    response = client.post(
        ENDPOINT, json={"claim": "Le chômage a doublé en France."}, headers=HEADERS
    )
    body = response.json()
    assert body["verdict"] == "ENGANOSO"
    assert body["connectors_queried"] == ["fr.data_gouv"]
    assert set(upstream.hits) == {"www.data.gouv.fr"}
    assert body["primary_sources"][0]["publisher"] == "INSEE via data.gouv.fr"


def test_country_override_from_request(client, upstream):
    ScriptedProvider.script = [analysis("BR", keywords=["chômage"]), verdict(cited=["E1"])]
    response = client.post(
        ENDPOINT, json={"claim": "Le chômage a doublé.", "country": "FR"}, headers=HEADERS
    )
    assert response.json()["country_context"] == "FR"
    assert set(upstream.hits) == {"www.data.gouv.fr"}


# =============================================================== resilience & auditability
def test_connector_failure_is_reported_not_fatal(client, upstream):
    upstream.failing_hosts = {"dadosabertos.camara.leg.br"}
    ScriptedProvider.script = [
        analysis("BR", keywords=["inflação"], topics=["inflação"]),
        verdict("FALSO", 0.8, cited=["E1"]),
    ]
    response = client.post(
        ENDPOINT, json={"claim": "A inflação do Brasil é de 20% ao ano."}, headers=HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "FALSO"
    failures = body["connector_failures"]
    assert failures[0]["connector"] == "br.camara"
    assert "unavailable" in failures[0]["error"]
    assert body["primary_sources"][0]["connector"] == "br.ibge"


def test_assertive_verdict_without_citations_is_downgraded(client):
    ScriptedProvider.script = [analysis("BR"), verdict("VERDADEIRO", 0.95, cited=["E99"])]
    body = client.post(
        ENDPOINT, json={"claim": "A reforma tributária foi aprovada."}, headers=HEADERS
    ).json()
    assert body["verdict"] == "INCONCLUSIVO"
    assert body["confidence_score"] == 0.5
    assert any("E99" in note for note in body["notes"])
    assert not any(s["cited"] for s in body["primary_sources"])


def test_no_evidence_leads_to_sem_dados(client, upstream):
    upstream.failing_hosts = {"dadosabertos.camara.leg.br", "servicodados.ibge.gov.br"}
    ScriptedProvider.script = [
        analysis("BR", topics=["inflação"]),
        verdict("FALSO", 0.9, cited=[]),
    ]
    body = client.post(ENDPOINT, json={"claim": "Algo sem dados."}, headers=HEADERS).json()
    assert body["verdict"] == "SEM_DADOS_SUFICIENTES"
    assert body["primary_sources"] == []
    assert len(body["connector_failures"]) == 2


def test_invalid_triage_output_falls_back_to_heuristics(client):
    ScriptedProvider.script = ["not json", "still not json", verdict(cited=["E1"])]
    body = client.post(
        ENDPOINT,
        json={"claim": "O Brasil aprovou a reforma tributária na Câmara dos Deputados."},
        headers=HEADERS,
    ).json()
    assert body["country_context"] == "BR"
    assert body["keywords"]
    assert any("heurística" in note for note in body["notes"])


# =============================================================== BYOK over HTTP
def test_missing_provider_header_returns_400(client):
    response = client.post(ENDPOINT, json={"claim": "Uma alegação qualquer."})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_configuration_error"


def test_missing_key_returns_400(client):
    response = client.post(
        ENDPOINT, json={"claim": "Uma alegação qualquer."}, headers={"X-Provider": "openai"}
    )
    assert response.status_code == 400
    assert "X-API-Key" in response.json()["error"]["message"]


def test_provider_auth_error_returns_401_without_leaking_key(client):
    ScriptedProvider.script = [ProviderAuthenticationError("openai: API key rejected.")]
    response = client.post(ENDPOINT, json={"claim": "Uma alegação qualquer."}, headers=HEADERS)
    assert response.status_code == 401
    assert "sk-user-secret-123" not in response.text


def test_key_is_passed_per_request_and_not_echoed(client):
    for key in ("sk-alice", "sk-bob"):
        ScriptedProvider.script = [analysis("BR"), verdict(cited=["E1"])]
        response = client.post(
            ENDPOINT,
            json={"claim": "A reforma tributária foi aprovada."},
            headers={"X-Provider": "openai", "X-API-Key": key, "X-Model": "gpt-test"},
        )
        assert response.status_code == 200
        assert key not in response.text
        assert response.json()["model"] == "gpt-test"
    keys = [p.credentials.secret() for p in ScriptedProvider.instances]
    assert keys == ["sk-alice", "sk-bob"]


@pytest.mark.parametrize("claim", ["", "abc", "    x    ", "a" * 5001])
def test_claim_validation(client, claim):
    response = client.post(ENDPOINT, json={"claim": claim}, headers=HEADERS)
    assert response.status_code == 422


def test_byok_discovery_endpoint(client):
    body = client.get("/api/v1/byok/providers").json()
    assert body["headers"] == ["X-Provider", "X-API-Key", "X-Endpoint-URL", "X-Model"]
    assert [p["name"] for p in body["providers"]] == ["openai"]
    assert body["providers"][0]["server_key_available"] is False


# =============================================================== heuristics
@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("O IBGE divulgou que a população do Brasil caiu", CountryContext.BR),
        ("L'INSEE annonce une baisse du chômage en France", CountryContext.FR),
        ("Macron e Lula assinaram um acordo", CountryContext.AMBOS),
        ("Les impôts ont augmenté pour les retraités", CountryContext.FR),
        ("Os impostos não aumentaram para os aposentados", CountryContext.BR),
        ("12345 67890", CountryContext.DESCONHECIDO),
    ],
)
def test_heuristic_country(claim, expected):
    assert heuristic_country(claim) is expected


def test_heuristic_keywords_drop_stopwords():
    keywords = heuristic_keywords("A inflação no Brasil passou de 10% em 2026 segundo o governo")
    assert "inflação" in keywords
    assert "para" not in keywords and "2026" not in keywords


# =============================================================== developer experience (Swagger)
def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/docs"


def test_openapi_exposes_byok_headers_as_authorize_schemes(client):
    spec = client.get("/openapi.json").json()
    schemes = spec["components"]["securitySchemes"]
    assert {s["name"] for s in schemes.values()} == {
        "X-Provider",
        "X-API-Key",
        "X-Endpoint-URL",
        "X-Model",
    }
    assert all(s["type"] == "apiKey" and s["in"] == "header" for s in schemes.values())
    operation = spec["paths"][ENDPOINT]["post"]
    assert len(operation["security"]) == 4
    examples = operation["requestBody"]["content"]["application/json"]["examples"]
    assert {"br_inflacao", "fr_chomage"} <= set(examples)
    # Connector routes stay public: no security requirement.
    assert "security" not in spec["paths"]["/api/v1/connectors/search"]["post"]


def test_swagger_ui_settings(client):
    html = client.get("/docs").text
    assert '"tryItOutEnabled": true' in html
    assert '"defaultModelsExpandDepth": -1' in html
    assert '"persistAuthorization": false' in html
    assert "swagger-ui-dist@5.17.14/swagger-ui.css" in html
    assert '<meta name="color-scheme" content="light">' in html


# =============================================================== keyless connector routes
def test_list_connectors(client):
    body = client.get("/api/v1/connectors").json()
    assert [c["id"] for c in body] == ["br.camara", "br.ibge", "fr.data_gouv"]


def test_connector_search_needs_no_llm_key(client, upstream):
    response = client.post(
        "/api/v1/connectors/search",
        json={"keywords": ["inflação"], "country": "BR", "topics": ["inflação"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["connectors_queried"] == ["br.camara", "br.ibge"]
    assert [e["connector"] for e in body["evidence"]] == ["br.camara", "br.ibge"]
    assert "www.data.gouv.fr" not in upstream.hits
    assert ScriptedProvider.instances == []


def test_connector_search_reports_failures(client, upstream):
    upstream.failing_hosts = {"www.data.gouv.fr"}
    body = client.post("/api/v1/connectors/search", json={"keywords": ["chômage"]}).json()
    assert body["connectors_queried"] == ["br.camara", "br.ibge", "fr.data_gouv"]
    assert body["connector_failures"][0]["connector"] == "fr.data_gouv"


def test_connector_search_requires_keywords(client):
    response = client.post("/api/v1/connectors/search", json={"keywords": []})
    assert response.status_code == 422
