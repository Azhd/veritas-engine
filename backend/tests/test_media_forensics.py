"""Phase 3 - media forensics: tool detection, EXIF, C2PA, transcription and the media route."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import ProviderName
from app.core.errors import ProviderRateLimitError
from app.engines.base import TranscriptionResult
from app.engines.providers.gemini_provider import GeminiProvider
from app.engines.providers.groq_provider import GroqProvider
from app.engines.providers.openai_provider import OpenAIProvider
from app.forensics import tools
from app.forensics.audio_transcriber import (
    LocalWhisperTranscriber,
    NoTranscriber,
    ProviderTranscriber,
    build_transcriber,
    extract_timed_claims,
)
from app.forensics.c2pa_validator import C2paValidator, interpret_manifest_store
from app.forensics.media_inspector import (
    MediaError,
    MediaInspector,
    MediaTooLargeError,
    UnsafeUrlError,
    assert_public_url,
    exif_with_pillow,
    sanitize_metadata,
    sniff,
)
from app.main import create_app
from app.schemas.forensics import (
    C2paVerdict,
    MediaCapabilities,
    MediaKind,
    ToolStatus,
    Transcript,
    TranscriptSegment,
)
from tests.conftest import FakeLLMProvider, fake_credentials, make_settings


def _sdk_status_error(sdk, cls_name: str, status: int) -> Exception:
    request = httpx.Request("POST", "https://api.example/v1")
    return getattr(sdk, cls_name)(
        "boom", response=httpx.Response(status, request=request), body=None
    )


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


# =============================================================== 3.2 media inspector
async def _chunks(data: bytes, size: int = 1024):
    for i in range(0, len(data), size):
        yield data[i : i + size]


@pytest.mark.parametrize(
    ("head", "kind", "mime"),
    [
        (b"\xff\xd8\xff\xe0" + b"\0" * 20, MediaKind.IMAGE, "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n" + b"\0" * 20, MediaKind.IMAGE, "image/png"),
        (b"RIFF\0\0\0\0WEBPVP8 ", MediaKind.IMAGE, "image/webp"),
        (b"RIFF\0\0\0\0WAVEfmt ", MediaKind.AUDIO, "audio/wav"),
        (b"\0\0\0\x20ftypisom\0\0", MediaKind.VIDEO, "video/mp4"),
        (b"\0\0\0\x20ftypM4A \0\0", MediaKind.AUDIO, "audio/mp4"),
        (b"ID3\x04\0\0", MediaKind.AUDIO, "audio/mpeg"),
        (b"OggS\0\x02", MediaKind.AUDIO, "audio/ogg"),
        (b"\x1aE\xdf\xa3\x01", MediaKind.VIDEO, "video/webm"),
    ],
)
def test_sniff_by_content_not_name(head, kind, mime):
    assert sniff(head) == (kind, mime)


def test_sniff_falls_back_to_declared_type():
    assert sniff(b"????????", "video/quicktime") == (MediaKind.VIDEO, "video/quicktime")
    assert sniff(b"????????", "application/pdf") == (MediaKind.UNKNOWN, "application/pdf")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8000/healthz",
        "http://192.168.0.1/",
        "http://10.0.0.5/x.mp4",
        "http://169.254.169.254/latest/meta-data/",
        "ftp://example.com/file",
        "file:///etc/passwd",
    ],
)
def test_ssrf_guard_blocks_internal_targets(url):
    with pytest.raises(MediaError):
        assert_public_url(url)


def test_ssrf_guard_allows_public_hosts(monkeypatch):
    monkeypatch.setattr(
        "app.forensics.media_inspector.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.215.14", 443))],
    )
    assert_public_url("https://example.com/video.mp4")


def test_ssrf_guard_blocks_dns_pointing_inside(monkeypatch):
    monkeypatch.setattr(
        "app.forensics.media_inspector.socket.getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 443))],
    )
    with pytest.raises(UnsafeUrlError):
        assert_public_url("https://evil.example/rebind")


async def test_ingest_enforces_size_limit_and_hashes():
    inspector = MediaInspector(make_settings(media_max_bytes=2048))
    async with inspector.workspace() as workdir:
        media = await inspector.ingest_stream(
            _chunks(b"\xff\xd8\xff" + b"x" * 1000), workdir, filename="../../evil/photo.jpg"
        )
        assert media.size_bytes == 1003 and media.kind is MediaKind.IMAGE
        assert media.filename == "photo.jpg"  # path components stripped
        assert len(media.sha256) == 64
        with pytest.raises(MediaTooLargeError):
            await inspector.ingest_stream(_chunks(b"x" * 5000), workdir)
        with pytest.raises(MediaError, match="vazio"):
            await inspector.ingest_stream(_chunks(b""), workdir)
    assert not workdir.exists()  # always cleaned up


def _photo_with_exif(path: Path, software: str | None = None) -> Path:
    from PIL import Image

    image = Image.new("RGB", (120, 80))
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = "Canon", "EOS R6"
    if software:
        exif[0x0131] = software
    exif.get_ifd(0x8769)[0x9003] = "2026:09:01 14:30:00"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "S", (23.0, 33.0, 0.0), "W", (46.0, 38.0, 0.0)
    image.save(path, exif=exif)
    return path


def test_exif_with_pillow_reads_camera_date_gps_and_flags_editors(tmp_path):
    summary = exif_with_pillow(_photo_with_exif(tmp_path / "a.jpg", "Adobe Photoshop 25.0"))
    assert summary.camera == "Canon EOS R6"
    assert summary.captured_at == "2026:09:01 14:30:00"
    assert summary.gps == {"latitude": -23.55, "longitude": -46.633333}
    assert (summary.width, summary.height) == (120, 80)
    assert any("Photoshop" in w for w in summary.warnings)


def test_metadata_without_capture_info_is_flagged_not_accused():
    summary = sanitize_metadata({"ImageWidth": 1080, "ImageHeight": 1920}, source="pillow")
    assert summary.camera is None and summary.captured_at is None
    assert "Não prova edição" in summary.warnings[0]


class _FakeFfmpeg:
    """Stands in for subprocess.run: answers like FFmpeg and creates the requested outputs."""

    def __init__(self, duration: str = "00:00:12.50", audio: bool = True):
        self.duration = duration
        self.audio = audio
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        target = Path(args[-1])
        if args[-2:-1] == ["wav"]:
            if self.audio:
                target.write_bytes(b"RIFF" + b"\0" * 100)
                return subprocess.CompletedProcess(args, 0, b"", b"")
            return subprocess.CompletedProcess(args, 1, b"", b"no audio stream")
        if str(target).endswith(".jpg"):
            target.write_bytes(b"\xff\xd8\xff fake jpeg")
            return subprocess.CompletedProcess(args, 0, b"", b"")
        stderr = f"Input #0, mov,mp4\n  Duration: {self.duration}, start: 0.0".encode()
        return subprocess.CompletedProcess(args, 1, b"", stderr)


def _caps(**available):
    def status(name):
        return ToolStatus(name=name, available=available.get(name, False), hint=f"hint {name}")

    return lambda: MediaCapabilities(
        ffmpeg=status("ffmpeg"),
        exiftool=status("exiftool"),
        image_metadata=status("pillow"),
        yt_dlp=status("yt-dlp"),
        c2pa=status("c2pa"),
        whisper_local=status("faster-whisper"),
    )


async def test_video_analysis_audio_keyframes_and_transcriber(monkeypatch):
    monkeypatch.setattr(tools, "ffmpeg_path", lambda: "ffmpeg")
    fake = _FakeFfmpeg()
    seen = {}

    class FakeTranscriber:
        async def transcribe(self, audio, duration):
            seen["audio"], seen["duration"] = audio.name, duration
            return Transcript(engine="fake")

    inspector = MediaInspector(
        make_settings(media_keyframes=3), capabilities=_caps(ffmpeg=True), run=fake
    )
    async with inspector.workspace() as workdir:
        media = await inspector.ingest_stream(_chunks(b"\0\0\0\x20ftypisom" + b"v" * 500), workdir)
        report = await inspector.analyse(media, workdir, transcriber=FakeTranscriber())
    assert report.kind is MediaKind.VIDEO
    assert report.exif.duration_seconds == 12.5
    assert [k.time_seconds for k in report.keyframes] == [3.12, 6.25, 9.38]
    assert report.keyframes[0].data_url.startswith("data:image/jpeg;base64,")
    assert seen == {"audio": "audio.wav", "duration": 12.5}
    assert report.transcript.engine == "fake"
    wav_call = next(c for c in fake.calls if "wav" in c)
    start = wav_call.index("-ac")
    assert wav_call[start : start + 4] == ["-ac", "1", "-ar", "16000"]
    assert "c2pa" in " ".join(report.capabilities_missing)


async def test_video_without_ffmpeg_degrades_gracefully():
    inspector = MediaInspector(make_settings(), capabilities=_caps())
    async with inspector.workspace() as workdir:
        media = await inspector.ingest_stream(_chunks(b"\0\0\0\x20ftypisom" + b"v" * 500), workdir)
        report = await inspector.analyse(media, workdir)
    assert report.keyframes == [] and report.transcript is None
    assert any(m.startswith("ffmpeg:") for m in report.capabilities_missing)


async def test_audio_without_sound_track_is_reported(monkeypatch):
    monkeypatch.setattr(tools, "ffmpeg_path", lambda: "ffmpeg")
    inspector = MediaInspector(
        make_settings(), capabilities=_caps(ffmpeg=True), run=_FakeFfmpeg(audio=False)
    )
    async with inspector.workspace() as workdir:
        media = await inspector.ingest_stream(_chunks(b"\0\0\0\x20ftypisom" + b"v" * 64), workdir)
        report = await inspector.analyse(media, workdir)
    assert "não tem faixa de áudio" in " ".join(report.warnings)


# =============================================================== 3.3 C2PA
needs_c2pa = pytest.mark.skipif(
    importlib.util.find_spec("c2pa") is None, reason="c2pa-python (requirements-media.txt)"
)


@needs_c2pa
@pytest.mark.parametrize(
    ("generator", "source_type", "edits", "verdict"),
    [
        ("DALL-E 3 (test)", "trainedAlgorithmicMedia", (), C2paVerdict.AI_GENERATED),
        ("Photoshop (test)", "compositeWithTrainedAlgorithmicMedia", (), C2paVerdict.AI_EDITED),
        ("Leica Camera (test)", "digitalCapture", (), C2paVerdict.CAMERA_CAPTURE),
        ("Leica Camera (test)", "digitalCapture", ("c2pa.cropped",), C2paVerdict.EDITED),
    ],
)
def test_c2pa_signed_fixtures(tmp_path, generator, source_type, edits, verdict):
    from tests.c2pa_fixtures import signed_jpeg

    path = signed_jpeg(
        tmp_path / "x.jpg", generator=generator, source_type=source_type, edits=edits
    )
    report = C2paValidator().inspect(path)
    assert report.verdict is verdict
    assert report.signed_by == "Veritas Test Org"
    assert "lista de confiança" in report.summary  # the test CA is (correctly) untrusted


@needs_c2pa
def test_c2pa_unsigned_and_tampered(tmp_path):
    from PIL import Image

    from tests.c2pa_fixtures import signed_jpeg

    Image.new("RGB", (16, 16)).save(tmp_path / "plain.jpg")
    unsigned = C2paValidator().inspect(tmp_path / "plain.jpg")
    assert unsigned.verdict is C2paVerdict.NO_MANIFEST
    assert "não prova" in unsigned.summary

    signed = signed_jpeg(tmp_path / "cam.jpg", generator="Cam", source_type="digitalCapture")
    data = bytearray(signed.read_bytes())
    data[data.rfind(b"\xff\xda") + 40] ^= 0xFF
    (tmp_path / "tampered.jpg").write_bytes(bytes(data))
    tampered = C2paValidator().inspect(tmp_path / "tampered.jpg")
    assert tampered.verdict is C2paVerdict.INVALID_SIGNATURE
    assert "alterada depois de assinada" in tampered.summary


def test_c2pa_interpretation_without_the_native_library():
    store = {
        "active_manifest": "m1",
        "manifests": {
            "m1": {
                "claim_generator": "Adobe_Firefly/1.0 c2pa-rs/0.9",
                "signature_info": {"issuer": "Adobe Inc."},
                "assertions": [{"label": "c2pa.actions", "data": {"actions": []}}],
            }
        },
        "validation_status": [],
    }
    report = interpret_manifest_store(store)
    assert report.verdict is C2paVerdict.AI_GENERATED  # known AI tool, no source type declared
    assert report.ai_tool == "Adobe_Firefly"
    assert "Assinado por Adobe Inc." in report.summary
    assert "lista de confiança" not in report.summary


# =============================================================== 3.4 transcription
class _GroqAudioClient:
    """Mimics groq/openai ``audio.transcriptions.create`` (verbose_json)."""

    def __init__(self, fail_first_with=None):
        self.calls = []
        self.fail_first_with = fail_first_with
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_first_with is not None and len(self.calls) == 1:
            raise self.fail_first_with
        return SimpleNamespace(
            language="portuguese",
            text="Olá. A inflação passou de 10%.",
            segments=[
                {"start": 0.0, "end": 1.2, "text": " Olá. "},
                {"start": 61.5, "end": 64.0, "text": " A inflação passou de 10%."},
            ],
        )


async def test_groq_whisper_request_and_segments():
    client = _GroqAudioClient()
    provider = GroqProvider(fake_credentials(provider=ProviderName.GROQ), client=client)
    assert provider.supports_audio
    result = await provider.transcribe_audio(b"mp3", "audio.mp3", "audio/mpeg")
    call = client.calls[0]
    assert call["model"] == "whisper-large-v3-turbo"
    assert call["response_format"] == "verbose_json"
    assert call["timestamp_granularities"] == ["segment"]
    assert call["file"] == ("audio.mp3", b"mp3", "audio/mpeg")
    assert result.segments == [(0.0, 1.2, "Olá."), (61.5, 64.0, "A inflação passou de 10%.")]
    assert result.model == "whisper-large-v3-turbo"


async def test_groq_whisper_falls_back_to_next_model():
    not_found = _sdk_status_error(groq, "NotFoundError", 404)
    client = _GroqAudioClient(fail_first_with=not_found)
    provider = GroqProvider(fake_credentials(provider=ProviderName.GROQ), client=client)
    result = await provider.transcribe_audio(b"mp3", "a.mp3", "audio/mpeg")
    assert [c["model"] for c in client.calls] == ["whisper-large-v3-turbo", "whisper-large-v3"]
    assert result.model == "whisper-large-v3"


def test_custom_openai_endpoints_do_not_claim_audio():
    provider = OpenAIProvider(
        fake_credentials(endpoint_url="http://localhost:8000/v1"), client=MagicMock()
    )
    assert provider.supports_audio is False


async def test_gemini_transcription_parses_json_segments():
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(
        return_value=SimpleNamespace(
            text='{"language": "pt", "segments": [{"start": 3, "end": 9.5, "text": "Bom dia"}]}'
        )
    )
    provider = GeminiProvider(fake_credentials(provider=ProviderName.GEMINI), client=client)
    result = await provider.transcribe_audio(b"mp3", "a.mp3", "audio/mpeg")
    assert result.segments == [(3.0, 9.5, "Bom dia")]
    contents = client.aio.models.generate_content.await_args.kwargs["contents"]
    assert contents[0].inline_data.mime_type == "audio/mpeg"


class _AudioProvider(FakeLLMProvider):
    name = ProviderName.GROQ
    supports_audio = True

    def __init__(self, segments=None, error=None):
        super().__init__(fake_credentials(provider=ProviderName.GROQ))
        self.segments = segments or [(1.0, 4.0, "Texto")]
        self.error = error
        self.received = None

    async def transcribe_audio(self, audio, filename, mime_type, language=None):
        self.received = (filename, mime_type)
        if self.error:
            raise self.error
        return TranscriptionResult(segments=self.segments, language="pt", model="whisper-x")


async def test_provider_transcriber_compresses_and_maps_segments(tmp_path, monkeypatch):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 100)
    monkeypatch.setattr(
        "app.forensics.audio_transcriber.compress_for_upload",
        lambda path: (path.with_suffix(".mp3").write_bytes(b"ID3"), path.with_suffix(".mp3"))[1],
    )
    provider = _AudioProvider(segments=[(5.0, 2.0, "fim antes do início"), (8.0, 9.0, "ok")])
    transcript = await ProviderTranscriber(provider).transcribe(wav, 10.0)
    assert provider.received == ("audio.mp3", "audio/mpeg")
    assert transcript.engine == "groq_whisper"
    assert [(s.start_time, s.end_time) for s in transcript.segments] == [(5.0, 5.0), (8.0, 9.0)]
    assert transcript.segments[1].label == "00:08"


async def test_provider_transcriber_failure_becomes_a_note(tmp_path):
    wav = tmp_path / "audio.wav"
    wav.write_bytes(b"RIFF")
    provider = _AudioProvider(error=ProviderRateLimitError("groq: rate limit or quota exceeded."))
    transcript = await ProviderTranscriber(provider).transcribe(wav, 3.0)
    assert transcript.segments == [] and "rate limit" in transcript.note


def test_transcriber_selection_is_free_tier_first():
    caps_none = _caps()()
    caps_local = _caps(**{"faster-whisper": True})()
    settings = make_settings()
    assert isinstance(build_transcriber(_AudioProvider(), settings, caps_none), ProviderTranscriber)
    no_audio = FakeLLMProvider(fake_credentials())  # e.g. Claude/Ollama: no audio input
    assert isinstance(build_transcriber(no_audio, settings, caps_local), LocalWhisperTranscriber)
    fallback = build_transcriber(None, settings, caps_none)
    assert isinstance(fallback, NoTranscriber) and "Groq" in fallback.note


async def test_timed_claims_with_ai_and_heuristic_fallback():
    transcript = Transcript(
        engine="t",
        segments=[
            TranscriptSegment(start_time=0, end_time=2, text="Boa noite a todos."),
            TranscriptSegment(
                start_time=83, end_time=90, text="A inflação do Brasil passou de 10% este ano."
            ),
        ],
    )
    heuristic = await extract_timed_claims(transcript, None)
    assert [(c.label, c.claim) for c in heuristic] == [
        ("01:23", "A inflação do Brasil passou de 10% este ano.")
    ]
    llm = FakeLLMProvider(
        fake_credentials(),
        [
            '{"claims": [{"start_time": 83, "claim": "A inflação no Brasil passou de 10% '
            'em 2026.", "quote": "passou de 10%"}]}'
        ],
    )
    claims = await extract_timed_claims(transcript, llm)
    assert claims[0].claim == "A inflação no Brasil passou de 10% em 2026."
    assert "[83.0s] A inflação" in llm.calls[0]["prompt"]
    assert await extract_timed_claims(Transcript(engine="t"), llm) == []
