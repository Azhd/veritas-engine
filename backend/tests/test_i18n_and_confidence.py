"""Language pages (/pt/, /en/, /fr/), reply language end to end, and the confidence display."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_media_check_service
from app.main import create_app
from app.schemas.fact_check import MediaFactCheckReport
from app.schemas.forensics import MediaForensicsReport, MediaKind
from app.services.claim_heuristics import heuristic_analysis, heuristic_language
from app.services.fact_checker import FactCheckService
from app.web_pages import SUPPORTED_LANGUAGES, load_translations, render_app_page
from tests.conftest import FakeLLMProvider, fake_credentials, make_settings

WEB_DIR = Path(__file__).resolve().parent.parent / "app" / "web"
ENGINE_KEYS = {"lang", "html_lang", "i18n_json", "current_pt", "current_en", "current_fr"}


@pytest.fixture
def web():
    with TestClient(create_app(make_settings())) as client:
        yield client


# =============================================================== pages
def test_chooser_links_the_three_language_pages(web):
    html = web.get("/").text
    for lang in SUPPORTED_LANGUAGES:
        assert f'href="/{lang}/"' in html
    assert "/static/home.js" in html


@pytest.mark.parametrize(
    ("lang", "html_lang", "title"),
    [
        ("pt", "pt-BR", "Verifique antes de compartilhar"),
        ("en", "en", "Check before you share"),
        ("fr", "fr", "Vérifiez avant de partager"),
    ],
)
def test_each_language_is_a_complete_page(web, lang, html_lang, title):
    response = web.get(f"/{lang}/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    html = response.text
    assert f'<html lang="{html_lang}" data-lang="{lang}">' in html
    assert title in html
    assert "{{" not in html  # every placeholder was filled
    # the current language is marked in the switcher, the others are plain links
    assert re.search(rf'href="/{lang}/"[^>]*aria-current="page"', html)
    assert html.count('aria-current="page"') == 1
    embedded = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, re.S)
    data = json.loads(embedded.group(1))
    assert data["meta"]["lang"] == lang and data["strings"]["submit"]


def test_language_path_without_slash_redirects(web):
    response = web.get("/en", follow_redirects=False)
    assert response.status_code in (307, 308)
    assert response.headers["location"].endswith("/en/")


def test_dictionaries_have_the_same_keys_and_placeholders():
    base = load_translations("pt")
    for lang in ("en", "fr"):
        other = load_translations(lang)
        assert set(other["strings"]) == set(base["strings"]), lang
        assert set(other["provider_steps"]) == set(base["provider_steps"]), lang
        assert other["examples"], lang
        for key, text in base["strings"].items():
            # "{pct}" etc. must survive translation, or app.js shows a raw placeholder
            assert set(re.findall(r"\{(\w+)\}", other["strings"][key])) == set(
                re.findall(r"\{(\w+)\}", text)
            ), f"{lang}:{key}"


def test_every_text_used_by_the_page_exists_in_the_dictionary():
    strings = set(load_translations("pt")["strings"])
    script = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    used = set(re.findall(r'\bt\("(\w+)"', script))
    # keys of NOTE_RULES (server messages translated on the page)
    used |= set(re.findall(r'"((?:note|warn|missing|err)_\w+)"', script))
    assert used and used <= strings, sorted(used - strings)
    template = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    placeholders = set(re.findall(r"\{\{(\w+)\}\}", template)) - ENGINE_KEYS
    assert placeholders <= strings, sorted(placeholders - strings)


def test_dictionary_cannot_break_out_of_the_script_tag(monkeypatch):
    data = json.loads(json.dumps(load_translations("en")))
    data["strings"]["page_title"] = "</script><script>alert(1)</script>"
    monkeypatch.setattr("app.web_pages.load_translations", lambda lang: data)
    render_app_page.cache_clear()
    try:
        html = render_app_page("en")
    finally:
        render_app_page.cache_clear()
    assert "<script>alert(1)" not in html
    assert "&lt;/script&gt;" in html  # escaped in the <title>
    assert "\\u003c/script>" in html  # escaped in the embedded JSON


# =============================================================== reply language
async def test_verdict_prompt_asks_for_the_page_language():
    llm = FakeLLMProvider(
        fake_credentials(),
        outputs=[
            '{"language": "pt", "domains": []}',
            '{"verdict": "INCONCLUSIVO", "confidence_score": 0.3, '
            '"explanation": "Not enough.", "cited_evidence_ids": []}',
        ],
    )
    report = await FactCheckService([]).check_text("Vacinas causam autismo.", llm, language="en")
    assert report.ai_used
    assert "Idioma da resposta: inglês (English)" in llm.calls[1]["prompt"]


@pytest.mark.parametrize(
    ("language", "start"),
    [
        ("en", "Citizen mode"),
        ("fr", "Mode citoyen"),
        ("pt", "Modo cidadão"),
        (None, "Modo cidadão"),
    ],
)
async def test_citizen_explanation_follows_the_reader(language, start):
    report = await FactCheckService([]).check_text(
        "Vacinas causam autismo.", None, language=language
    )
    assert report.explanation.startswith(start)


def test_media_route_forwards_the_language():
    received: dict = {}

    class RecordingService:
        async def check(self, llm, **kwargs):
            received.update(kwargs)
            return MediaFactCheckReport(
                forensics=MediaForensicsReport(kind=MediaKind.IMAGE, size_bytes=1, sha256="0" * 64),
                checks=[],
                ai_used=False,
                provider="nenhum",
                model="nenhum",
            )

    app = create_app(make_settings())
    app.dependency_overrides[get_media_check_service] = RecordingService
    with TestClient(app) as client:
        ok = client.post(
            "/api/v1/fact-check/media", data={"url": "https://x.example/a.mp4", "language": "fr"}
        )
        bad = client.post(
            "/api/v1/fact-check/media", data={"url": "https://x.example/a.mp4", "language": "de"}
        )
    assert ok.status_code == 200 and received["language"] == "fr"
    assert bad.status_code == 422


# =============================================================== English claims without AI
@pytest.mark.parametrize(
    ("claim", "hint", "expected"),
    [
        ("Vaccines cause autism in children.", None, "en"),
        ("The unemployment rate has doubled since 2020.", None, "en"),
        ("Vacinas causam autismo em crianças.", "en", "pt"),
        ("Le taux de chômage a doublé depuis 2020.", None, "fr"),
        ("Ivermectin cures COVID-19.", "en", "en"),  # no function words: the page decides
        ("Ivermectin cures COVID-19.", None, "pt"),
    ],
)
def test_claim_language_detection(claim, hint, expected):
    assert heuristic_language(claim, hint) == expected


def test_english_claim_queries_international_sources_with_its_own_words():
    analysis = heuristic_analysis("Russia and Ukraine signed a ceasefire this month.")
    assert analysis.language == "en"
    assert "geopolitics" in [d.value for d in analysis.domains]
    assert {"ceasefire", "ukraine", "russia"} <= set(analysis.keywords_en)
    climate = heuristic_analysis("Global warming made 2024 the hottest year on record.")
    assert "climate_environment" in [d.value for d in climate.domains]
