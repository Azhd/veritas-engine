"""Phase 3 - media forensics: tool detection, EXIF, C2PA, transcription and the media route."""

from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient

from app.forensics import tools
from app.main import create_app
from tests.conftest import make_settings

# =============================================================== 3.1 tool detection


@pytest.fixture(autouse=True)
def _fresh_capabilities():
    tools.detect_capabilities.cache_clear()
    yield
    tools.detect_capabilities.cache_clear()


def test_system_ffmpeg_wins_over_bundled(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: f"/usr/bin/{name}")
    path, source = tools.find_ffmpeg()
    assert (path, source) == ("/usr/bin/ffmpeg", "system")


def test_bundled_ffmpeg_used_when_system_missing(monkeypatch):
    if importlib.util.find_spec("imageio_ffmpeg") is None:
        pytest.skip("imageio-ffmpeg (requirements-media.txt) not installed")
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    path, source = tools.find_ffmpeg()
    assert source == "python" and path


def test_capabilities_degrade_gracefully_on_bare_windows(monkeypatch):
    """Nothing installed: every missing tool is reported with a hint, nothing raises."""
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    real_find_spec = importlib.util.find_spec
    missing = {"imageio_ffmpeg", "c2pa", "faster_whisper", "yt_dlp", "PIL"}
    monkeypatch.setattr(
        tools.importlib.util,
        "find_spec",
        lambda name, *a: None if name in missing else real_find_spec(name, *a),
    )
    caps = tools.detect_capabilities()
    assert not caps.ffmpeg.available and "run.ps1 -Full" in caps.ffmpeg.hint
    assert not caps.c2pa.available and caps.c2pa.hint
    assert not caps.yt_dlp.available and not caps.image_metadata.available
    assert not caps.can_extract_audio and not caps.can_download

    app = create_app(make_settings())
    with TestClient(app) as client:
        body = client.get("/api/v1/media/capabilities").json()
    assert body["ready_for"] == []
    assert any(item.startswith("ffmpeg:") for item in body["missing"])


def test_capabilities_route_lists_ready_features(monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(tools, "_binary_version", lambda path, flag: "test 1.0")
    app = create_app(make_settings())
    with TestClient(app) as client:
        body = client.get("/api/v1/media/capabilities").json()
    caps = body["capabilities"]
    assert caps["ffmpeg"] == {
        "name": "ffmpeg",
        "available": True,
        "source": "system",
        "version": "test 1.0",
        "hint": None,
    }
    assert caps["exiftool"]["available"] is True
    assert "extrair áudio" in body["ready_for"]
