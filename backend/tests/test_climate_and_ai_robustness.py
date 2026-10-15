"""Climate connectors, AI-key test endpoint, lenient LLM parsing, vague claims, GDELT throttle."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connectors.climate_environment import (
    COPERNICUS_CSV_URL,
    CopernicusClimateConnector,
    NoaaClimateConnector,
    YearValue,
    consecutive_records,
    describe,
    record_years,
)
from app.connectors.global_geopolitics import GdeltConnector
from app.core.config import ProviderName
from app.core.errors import ConnectorUnavailableError, ProviderAuthenticationError
from app.engines.factory import ProviderFactory
from app.main import create_app
from app.schemas.evidence import Domain, EvidenceQuery
from app.schemas.fact_check import ClaimAnalysis, CountryContext, LLMVerdict, Verdict
from app.services.claim_heuristics import heuristic_analysis, is_vague
from tests.conftest import FakeLLMProvider, SleepRecorder, json_response, make_settings, mock_client

# =============================================================== climate: pure logic


def _years(values: dict[int, float]) -> list[YearValue]:
    return [YearValue(y, v) for y, v in sorted(values.items())]


def test_record_years_and_consecutive_run():
    series = _years({2014: 0.3, 2015: 0.5, 2016: 0.6, 2017: 0.55, 2023: 0.7, 2024: 0.8, 2025: 0.75})
    assert record_years(series) == [2014, 2015, 2016, 2023, 2024]
    assert consecutive_records(record_years(series)) == [2023, 2024]
    assert consecutive_records([2010, 2016, 2020]) == []


def test_describe_mentions_ranking_records_and_last_year():
    series = _years({2016: 0.6, 2023: 0.7, 2024: 0.8, 2025: 0.75})
    text, data = describe(series, "anomalia")
    assert text.startswith("Anos mais quentes: 2024: +0.80 °C; 2025: +0.75 °C")
    assert "Recordes consecutivos: 2023 e 2024." in text
    assert "2025 (último ano completo) ficou em 2º lugar." in text
    assert data["consecutive_records"] == [2023, 2024]
    assert data["last_complete_year_rank"] == 2


# =============================================================== climate: connectors (mocked)
def _copernicus_csv() -> str:
    lines = [
        "# Description: daily global mean near-surface (2m) air temperature from ERA5",
        "date,2t,clim_91-20,ano_91-20,status",
    ]
    for year, anomaly in ((2023, 0.60), (2024, 0.72), (2025, 0.59)):
        days = 366 if year == 2024 else 365
        for i in range(days):
            day = date.fromordinal(date(year, 1, 1).toordinal() + i)
            lines.append(f"{day.isoformat()},{14.3 + anomaly:.3f},14.300,{anomaly:.3f},FINAL")
    for i in range(10):
        lines.append(f"2026-01-{i + 1:02d},15.000,14.300,0.700,PRELIMINARY")
    return "\n".join(lines)


class TestCopernicus:
    async def test_annual_means_records_and_partial_year(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, text=_copernicus_csv())

        conn = CopernicusClimateConnector(mock_client(handler), sleep=SleepRecorder())
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["temperatura"], keywords_en=["global temperature record"])
        )
        assert str(seen[0].url) == COPERNICUS_CSV_URL
        item = evidence[0]
        assert item.connector == "climate.copernicus"
        assert "2025 = 14.89 °C" in item.excerpt
        assert "Recordes consecutivos: 2023 e 2024." in item.excerpt
        assert "2026 até agora (10 dias): +0.70 °C" in item.excerpt
        assert item.data["ranking_top5"]["2024"] == pytest.approx(0.72)
        assert item.data["last_complete_year_rank"] == 3  # 2025 (+0.59) < 2023 (+0.60)
        # Cached: a second query does not download the dataset again.
        await conn.search_evidence(EvidenceQuery(keywords=["aquecimento global"]))
        assert len(seen) == 1

    async def test_non_temperature_queries_are_skipped(self):
        conn = CopernicusClimateConnector(
            mock_client(lambda r: (_ for _ in ()).throw(AssertionError("no call")))
        )
        assert await conn.search_evidence(EvidenceQuery(keywords=["desmatamento amazônia"])) == []


class TestNoaa:
    async def test_annual_departures(self):
        payload = {
            "description": {"title": "Global Land and Ocean"},
            "data": {
                "2015": {"departure": 0.93},
                "2016": {"departure": 0.99},
                "2023": {"departure": 1.17},
                "2024": {"departure": 1.25},
                "2025": {"departure": 1.12},
                "note": {"departure": "ignored"},
            },
        }
        conn = NoaaClimateConnector(mock_client(lambda r: json_response(payload)))
        evidence = await conn.search_evidence(EvidenceQuery(keywords_en=["global temperature"]))
        text = evidence[0].excerpt
        assert "2024: +1.25 °C" in text
        assert "Recordes consecutivos: 2023 e 2024." in text
        assert evidence[0].data["consecutive_records"] == [2023, 2024]


# =============================================================== heuristics: climate & vague claims
def test_copernicus_claim_routes_to_climate():
    claim = (
        "O observatório europeu Copernicus (da União Europeia) divulgou relatórios confirmando "
        "recordes consecutivos de temperatura média global nos últimos anos."
    )
    analysis = heuristic_analysis(claim)
    assert analysis.domains == [Domain.CLIMATE_ENVIRONMENT]
    assert "global mean temperature" in analysis.keywords_en
    assert not is_vague(claim, analysis.domains)


@pytest.mark.parametrize(
    ("claim", "vague"),
    [
        ("Vídeos mostram que uma cidade inteira foi destruída em um ataque recente.", True),
        ("Um comboio humanitário foi atacado em Gaza ontem.", False),
        ("Um ataque em 12 de março destruiu uma ponte.", False),
        ("Vacinas causam autismo em crianças.", False),  # general claim, checkable as is
    ],
)
def test_vague_event_claims(claim, vague):
    assert is_vague(claim) is vague


# =============================================================== lenient LLM output
def test_llm_verdict_accepts_common_variations():
    verdict = LLMVerdict.model_validate(
        {
            "verdict": "true",
            "confidence_score": "85%",
            "explanation": "ok",
            "cited_evidence_ids": [1, "e2", "[E3]"],
        }
    )
    assert verdict.verdict is Verdict.VERDADEIRO
    assert verdict.confidence_score == 0.85
    assert verdict.cited_evidence_ids == ["E1", "E2", "E3"]


def test_claim_analysis_accepts_common_variations():
    analysis = ClaimAnalysis.model_validate(
        {
            "country": "Brazil",
            "domains": ["Climate_Environment", "astrology"],
            "keywords": "temperatura, recorde",
            "keywords_en": ["x"] * 12,
            "language": "Portuguese",
        }
    )
    assert analysis.country is CountryContext.BR
    assert analysis.domains == [Domain.CLIMATE_ENVIRONMENT]
    assert analysis.keywords == ["temperatura", "recorde"]
    assert len(analysis.keywords_en) == 8
    assert analysis.language == "pt"


# =============================================================== GDELT local throttle
async def test_gdelt_spaces_calls_and_pauses_after_rate_limit():
    now = [0.0]
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 2:
            return httpx.Response(429)
        return httpx.Response(200, text=json.dumps({"articles": []}))

    conn = GdeltConnector(mock_client(handler), clock=lambda: now[0], sleep=SleepRecorder())
    await conn.search_articles("ukraine ceasefire")
    with pytest.raises(ConnectorUnavailableError, match="limite"):
        await conn.search_articles("gaza convoy")  # < 5.5 s later: refused locally
    assert calls["n"] == 1
    await conn.search_articles("ukraine ceasefire")  # same query: served from cache
    assert calls["n"] == 1
    now[0] = 6
    with pytest.raises(ConnectorUnavailableError):
        await conn.search_articles("gaza convoy")  # real call -> 429
    now[0] = 30
    with pytest.raises(ConnectorUnavailableError, match="limite"):
        await conn.search_articles("sudan")  # paused after the 429
    assert calls["n"] == 2


# =============================================================== /api/v1/byok/test
class _Healthy(FakeLLMProvider):
    name = ProviderName.GROQ

    def __init__(self, credentials):
        super().__init__(credentials, outputs=["OK"])


class _Rejected(FakeLLMProvider):
    name = ProviderName.GROQ

    def __init__(self, credentials):
        super().__init__(
            credentials, outputs=[ProviderAuthenticationError("groq: API key rejected.")]
        )


@pytest.mark.parametrize(
    ("provider_cls", "ok", "message"),
    [(_Healthy, True, "Conectado"), (_Rejected, False, "API key rejected")],
)
def test_byok_connection_test(provider_cls, ok, message):
    settings = make_settings()
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.provider_factory = ProviderFactory(
            settings, registry={ProviderName.GROQ: provider_cls}
        )
        body = client.post(
            "/api/v1/byok/test", headers={"X-Provider": "groq", "X-API-Key": "gsk-secret"}
        ).json()
        assert body["ok"] is ok
        assert message in body["message"]
        assert "gsk-secret" not in json.dumps(body)
        no_key = client.post("/api/v1/byok/test").json()
        assert no_key["ok"] is False


# =============================================================== startup configuration
def test_env_example_loads_as_copied_by_run_scripts():
    """run.ps1/run.sh copy .env.example to .env: its blank values must not break startup."""
    from pathlib import Path

    from app.core.config import Settings

    settings = Settings(_env_file=Path(__file__).parents[1] / ".env.example")
    assert settings.default_provider is None
    assert settings.gemini_api_key is None
    assert settings.reliefweb_appname is None
    assert settings.cors_origins == ["http://localhost:3000"]
