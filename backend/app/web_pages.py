"""Citizen web app pages: one page per language (``/pt/``, ``/en/``, ``/fr/``) and the chooser.

``web/index.html`` is a template with ``{{key}}`` placeholders filled from
``web/i18n/<lang>.json``. The same dictionary is embedded in the page for ``app.js``, so each
language is a complete page on first paint (no flash of another language, no extra request).
"""

from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

WEB_DIR = Path(__file__).parent / "web"
I18N_DIR = WEB_DIR / "i18n"
SUPPORTED_LANGUAGES = ("pt", "en", "fr")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


@lru_cache
def load_translations(lang: str) -> dict[str, Any]:
    if lang not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language: {lang}")
    return json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))


@lru_cache
def render_app_page(lang: str) -> str:
    data = load_translations(lang)
    values = {key: html.escape(text) for key, text in data["strings"].items()}
    values["lang"] = lang
    values["html_lang"] = data["meta"]["html_lang"]
    for code in SUPPORTED_LANGUAGES:
        values[f"current_{code}"] = 'aria-current="page"' if code == lang else ""
    # "<" escaped so no string in the dictionary can close the <script> element.
    values["i18n_json"] = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    def fill(match: re.Match[str]) -> str:
        return values[match.group(1)]  # KeyError = missing translation, caught by the tests

    template = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return _PLACEHOLDER.sub(fill, template)
