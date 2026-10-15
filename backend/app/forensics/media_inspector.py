"""Media forensics orchestrator (TASK 3.2).

Ingests an uploaded file or a link (direct image/audio/video or a page handled by ``yt-dlp``),
then extracts what a fact-checker needs: a SHA-256 fingerprint (chain of custody), sanitized
metadata (EXIF), a 16 kHz mono WAV for transcription and a few small keyframes.

Every external tool is optional (see ``tools.py``): what cannot be done is listed in
``capabilities_missing`` instead of failing. Temporary files are always deleted.

Security: links are only fetched when they resolve to public addresses (no SSRF into the
server's network) and downloads are capped by size and duration.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import re
import shutil
import socket
import subprocess
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import Settings
from app.core.errors import VeritasError
from app.forensics import tools
from app.schemas.forensics import (
    C2paReport,
    ExifSummary,
    Keyframe,
    MediaCapabilities,
    MediaForensicsReport,
    MediaKind,
    Transcript,
)

logger = logging.getLogger(__name__)

CHUNK = 1024 * 1024
MAX_REDIRECTS = 3
FFMPEG_TIMEOUT_SECONDS = 120
DIRECT_MEDIA_EXT = re.compile(
    r"\.(jpe?g|png|webp|gif|heic|mp3|m4a|wav|ogg|opus|mp4|mov|webm|mkv)$", re.IGNORECASE
)


class MediaError(VeritasError):
    status_code = 400
    code = "media_error"


class MediaTooLargeError(MediaError):
    status_code = 413
    code = "media_too_large"


class UnsafeUrlError(MediaError):
    code = "unsafe_url"


# ---------------------------------------------------------------- file type sniffing
_SIGNATURES: tuple[tuple[bytes, int, MediaKind, str], ...] = (
    (b"\xff\xd8\xff", 0, MediaKind.IMAGE, "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", 0, MediaKind.IMAGE, "image/png"),
    (b"GIF8", 0, MediaKind.IMAGE, "image/gif"),
    (b"ID3", 0, MediaKind.AUDIO, "audio/mpeg"),
    (b"OggS", 0, MediaKind.AUDIO, "audio/ogg"),
    (b"fLaC", 0, MediaKind.AUDIO, "audio/flac"),
    (b"\x1aE\xdf\xa3", 0, MediaKind.VIDEO, "video/webm"),
)


def sniff(head: bytes, declared_mime: str | None = None) -> tuple[MediaKind, str | None]:
    """Detect the media type from the first bytes (never trust the file name alone)."""
    for magic, offset, kind, mime in _SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return kind, mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return MediaKind.IMAGE, "image/webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return MediaKind.AUDIO, "audio/wav"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            return MediaKind.AUDIO, "audio/mp4"
        if brand in (b"heic", b"heix", b"mif1"):
            return MediaKind.IMAGE, "image/heic"
        return MediaKind.VIDEO, "video/mp4"
    if head[:2] == b"\xff\xfb" or head[:2] == b"\xff\xf3":
        return MediaKind.AUDIO, "audio/mpeg"
    if declared_mime:
        major = declared_mime.split("/")[0]
        if major in ("image", "audio", "video"):
            return MediaKind(major), declared_mime
    return MediaKind.UNKNOWN, declared_mime


# ---------------------------------------------------------------- SSRF guard
def assert_public_url(url: str) -> None:
    """Reject links that point to the server's own network (localhost, LAN, cloud metadata)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeUrlError("O link precisa começar com http:// ou https://.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise MediaError("Não foi possível encontrar esse endereço.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise UnsafeUrlError("Esse link aponta para uma rede interna e não pode ser aberto.")


class ProvenanceChecker(Protocol):
    def inspect(self, path: Path, mime_type: str | None) -> C2paReport: ...


class Transcriber(Protocol):
    async def transcribe(self, audio: Path, duration: float | None) -> Transcript: ...


# ---------------------------------------------------------------- ingested file
@dataclass
class IngestedMedia:
    path: Path
    size_bytes: int
    sha256: str
    kind: MediaKind
    mime_type: str | None
    filename: str | None = None
    source_url: str | None = None
    title: str | None = None


class MediaInspector:
    def __init__(
        self,
        settings: Settings,
        capabilities: Callable[[], MediaCapabilities] = tools.detect_capabilities,
        http_client: httpx.AsyncClient | None = None,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        self.settings = settings
        self._capabilities = capabilities
        self._http = http_client
        self._run = run  # injectable for tests

    @property
    def max_bytes(self) -> int:
        return self.settings.media_max_bytes

    # ------------------------------------------------------------ workspace
    @asynccontextmanager
    async def workspace(self) -> AsyncIterator[Path]:
        base = Path(self.settings.media_tmp_dir or tempfile.gettempdir()) / "veritas-media"
        base.mkdir(parents=True, exist_ok=True)
        path = Path(tempfile.mkdtemp(prefix="job-", dir=base))
        try:
            yield path
        finally:
            await asyncio.to_thread(shutil.rmtree, path, True)

    # ------------------------------------------------------------ ingestion
    async def ingest_stream(
        self,
        chunks: AsyncIterator[bytes],
        workdir: Path,
        *,
        filename: str | None = None,
        declared_mime: str | None = None,
        source_url: str | None = None,
    ) -> IngestedMedia:
        """Write a stream to disk, enforcing the size limit and hashing on the fly."""
        target = workdir / "input.bin"
        digest = hashlib.sha256()
        size = 0
        head = b""
        with target.open("wb") as fh:
            async for chunk in chunks:
                size += len(chunk)
                if size > self.max_bytes:
                    raise MediaTooLargeError(
                        f"O arquivo passa do limite de {self.max_bytes // (1024 * 1024)} MB."
                    )
                if len(head) < 64:
                    head += chunk[: 64 - len(head)]
                digest.update(chunk)
                fh.write(chunk)
        if size == 0:
            raise MediaError("O arquivo está vazio.")
        kind, mime = sniff(head, declared_mime)
        return IngestedMedia(
            path=target,
            size_bytes=size,
            sha256=digest.hexdigest(),
            kind=kind,
            mime_type=mime,
            filename=Path(filename).name if filename else None,
            source_url=source_url,
        )

    async def ingest_url(self, url: str, workdir: Path) -> IngestedMedia:
        await asyncio.to_thread(assert_public_url, url)
        if DIRECT_MEDIA_EXT.search(urlparse(url).path):
            return await self._download_direct(url, workdir)
        if not self._capabilities().yt_dlp.available:
            raise MediaError("Baixar vídeos de links exige o yt-dlp (pip install yt-dlp).")
        return await asyncio.to_thread(self._download_with_ytdlp, url, workdir)

    async def _download_direct(self, url: str, workdir: Path) -> IngestedMedia:
        client = self._http or httpx.AsyncClient(follow_redirects=False, timeout=30)
        try:
            # Redirects are followed by hand so every hop passes the SSRF check.
            for _ in range(MAX_REDIRECTS):
                head = await client.head(url)
                if not head.is_redirect:
                    break
                url = urljoin(url, head.headers["location"])
                await asyncio.to_thread(assert_public_url, url)
            else:
                raise MediaError("O link redireciona vezes demais.")
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    raise MediaError("O link mudou de endereço durante o download.")
                if response.status_code >= 400:
                    raise MediaError(f"O link respondeu HTTP {response.status_code}.")
                declared = int(response.headers.get("content-length") or 0)
                if declared > self.max_bytes:
                    raise MediaTooLargeError("O arquivo do link passa do limite de tamanho.")
                return await self.ingest_stream(
                    response.aiter_bytes(CHUNK),
                    workdir,
                    filename=Path(urlparse(url).path).name,
                    declared_mime=response.headers.get("content-type", "").split(";")[0] or None,
                    source_url=url,
                )
        except httpx.HTTPError as exc:
            raise MediaError(f"Não foi possível baixar o link ({type(exc).__name__}).") from exc
        finally:
            if self._http is None:
                await client.aclose()

    def _download_with_ytdlp(self, url: str, workdir: Path) -> IngestedMedia:
        import yt_dlp

        max_duration = self.settings.media_max_duration_seconds

        def too_long(info: dict[str, Any], *, incomplete: bool) -> str | None:
            duration = info.get("duration")
            if duration and duration > max_duration:
                return f"vídeo com {int(duration)} s (limite {max_duration} s)"
            return None

        options = {
            "outtmpl": str(workdir / "download.%(ext)s"),
            # Smallest reasonable rendition: forensics needs audio + a few frames, not 4K.
            "format": "best[height<=480][filesize<50M]/best[height<=720]/bestaudio/best",
            "max_filesize": self.max_bytes,
            "match_filter": too_long,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 20,
            "restrictfilenames": True,
        }
        ffmpeg = tools.ffmpeg_path()
        if ffmpeg:
            options["ffmpeg_location"] = ffmpeg
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as exc:  # yt-dlp raises many error types
            message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
            raise MediaError(f"Não foi possível baixar o vídeo: {message[:200]}") from exc
        if info is None:
            raise MediaError("O vídeo passa do limite de duração ou de tamanho.")
        files = [p for p in workdir.glob("download.*") if p.is_file()]
        if not files:
            raise MediaError("O vídeo passa do limite de tamanho ou não pôde ser baixado.")
        path = files[0]
        size = path.stat().st_size
        if size > self.max_bytes:
            raise MediaTooLargeError("O vídeo passa do limite de tamanho.")
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            head = fh.read(64)
            fh.seek(0)
            for block in iter(lambda: fh.read(CHUNK), b""):
                digest.update(block)
        kind, mime = sniff(head)
        return IngestedMedia(
            path=path,
            size_bytes=size,
            sha256=digest.hexdigest(),
            kind=kind,
            mime_type=mime,
            filename=path.name,
            source_url=url,
            title=info.get("title"),
        )

    # ------------------------------------------------------------ full analysis
    async def analyse(
        self,
        media: IngestedMedia,
        workdir: Path,
        *,
        provenance: ProvenanceChecker | None = None,
        transcriber: Transcriber | None = None,
    ) -> MediaForensicsReport:
        caps = self._capabilities()
        missing: list[str] = []
        warnings: list[str] = []
        timed = media.kind in (MediaKind.AUDIO, MediaKind.VIDEO)
        if media.kind is MediaKind.UNKNOWN:
            warnings.append(
                "Tipo de arquivo não reconhecido: só a impressão digital foi calculada."
            )

        duration = None
        if timed:
            if caps.ffmpeg.available:
                duration = await run_blocking(self.probe_duration, media.path)
            else:
                missing.append(
                    "ffmpeg: duração, áudio e quadros-chave (" + (caps.ffmpeg.hint or "") + ")"
                )
        if duration and duration > self.settings.media_max_duration_seconds:
            warnings.append(
                f"Mídia com {int(duration)} s: só os primeiros "
                f"{self.settings.media_max_duration_seconds} s foram analisados."
            )

        exif = await run_blocking(self.exif, media, duration)

        keyframes: list[Keyframe] = []
        if media.kind is MediaKind.VIDEO and caps.ffmpeg.available:
            keyframes = await run_blocking(self.keyframes, media, workdir, duration)

        c2pa_report = None
        if media.kind in (MediaKind.IMAGE, MediaKind.VIDEO, MediaKind.AUDIO):
            if provenance is not None:
                c2pa_report = await run_blocking(provenance.inspect, media.path, media.mime_type)
            elif not caps.c2pa.available:
                missing.append(
                    "c2pa: detecção de imagens geradas por IA (" + (caps.c2pa.hint or "") + ")"
                )

        transcript = None
        if timed and caps.ffmpeg.available:
            audio = await run_blocking(self.extract_audio, media, workdir)
            if audio is None:
                warnings.append("A mídia não tem faixa de áudio.")
            elif transcriber is not None:
                transcript = await transcriber.transcribe(audio, duration)

        return MediaForensicsReport(
            kind=media.kind,
            filename=media.filename,
            source_url=media.source_url,
            mime_type=media.mime_type,
            size_bytes=media.size_bytes,
            sha256=media.sha256,
            exif=exif,
            c2pa=c2pa_report,
            transcript=transcript,
            keyframes=keyframes,
            capabilities_missing=missing,
            warnings=warnings,
        )

    # ------------------------------------------------------------ FFmpeg helpers
    def _ffmpeg(self, *args: str) -> subprocess.CompletedProcess:
        ffmpeg = tools.ffmpeg_path()
        if not ffmpeg:
            raise MediaError("FFmpeg indisponível.")
        return self._run(
            [ffmpeg, "-hide_banner", "-nostdin", *args],
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )

    def probe_duration(self, path: Path) -> float | None:
        """Duration in seconds parsed from ``ffmpeg -i`` (ffprobe is not bundled on pip)."""
        result = self._ffmpeg("-i", str(path))
        text = (result.stderr or b"").decode("utf-8", "replace")
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if not match:
            return None
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    def extract_audio(self, media: IngestedMedia, workdir: Path) -> Path | None:
        """16 kHz mono WAV (what Whisper expects), capped to the configured duration."""
        target = workdir / "audio.wav"
        result = self._ffmpeg(
            "-y", "-i", str(media.path), "-vn", "-ac", "1", "-ar", "16000",
            "-t", str(self.settings.media_max_duration_seconds), "-f", "wav", str(target),
        )  # fmt: skip
        if result.returncode != 0 or not target.exists() or target.stat().st_size <= 44:
            return None  # no audio track
        return target

    def keyframes(
        self, media: IngestedMedia, workdir: Path, duration: float | None
    ) -> list[Keyframe]:
        """Evenly spaced small JPEG thumbnails (enough to eyeball the video, cheap to send)."""
        count = self.settings.media_keyframes
        if not duration or duration <= 0:
            stamps = [0.0]
        else:
            step = duration / (count + 1)
            stamps = [round(step * (i + 1), 2) for i in range(count)]
        frames: list[Keyframe] = []
        for index, stamp in enumerate(stamps):
            target = workdir / f"frame-{index}.jpg"
            result = self._ffmpeg(
                "-y", "-ss", str(stamp), "-i", str(media.path), "-frames:v", "1",
                "-vf", "scale=320:-2", "-q:v", "6", str(target),
            )  # fmt: skip
            if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
                encoded = base64.b64encode(target.read_bytes()).decode("ascii")
                frames.append(
                    Keyframe(time_seconds=stamp, data_url=f"data:image/jpeg;base64,{encoded}")
                )
        return frames

    # ------------------------------------------------------------ metadata
    def exif(self, media: IngestedMedia, duration: float | None) -> ExifSummary | None:
        caps = self._capabilities()
        if caps.exiftool.available:
            summary = self._exif_with_exiftool(media.path)
        elif media.kind is MediaKind.IMAGE and caps.image_metadata.available:
            summary = exif_with_pillow(media.path)
        else:
            summary = None
        if duration is not None:
            summary = summary or ExifSummary(source="ffmpeg")
            summary.duration_seconds = round(duration, 2)
        return summary

    def _exif_with_exiftool(self, path: Path) -> ExifSummary | None:
        exiftool = tools.find_exiftool()
        if not exiftool:
            return None
        result = self._run(
            [exiftool, "-json", "-n", "-G0", str(path)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        try:
            data = json.loads(result.stdout or b"[]")[0]
        except (ValueError, IndexError):
            return None
        flat = {key.split(":", 1)[-1]: value for key, value in data.items()}
        return sanitize_metadata(flat, source="exiftool")


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", "0000:00:00 00:00:00"):
            return value
    return None


def sanitize_metadata(data: dict[str, Any], source: str) -> ExifSummary:
    """Keep only fact-checking-relevant fields; flag editing software and missing capture data."""
    make = _first(data, "Make")
    model = _first(data, "Model")
    camera = " ".join(str(v).strip() for v in (make, model) if v) or None
    captured = _first(data, "DateTimeOriginal", "CreateDate", "DateTime", "MediaCreateDate")
    software = _first(data, "Software", "CreatorTool", "ProcessingSoftware", "Encoder")
    lat = _first(data, "GPSLatitude")
    lon = _first(data, "GPSLongitude")
    gps = None
    try:
        if lat is not None and lon is not None:
            gps = {"latitude": round(float(lat), 6), "longitude": round(float(lon), 6)}
    except (TypeError, ValueError):
        gps = None
    warnings = []
    if software and re.search(
        r"photoshop|gimp|lightroom|snapseed|canva|picsart|firefly|midjourney|dall|stable diffusion|"
        r"facetune|capcut",
        str(software),
        re.IGNORECASE,
    ):
        warnings.append(f"Arquivo processado por software de edição/geração: {software}.")
    if not captured and not camera:
        warnings.append(
            "Sem data de captura nem câmera: comum em prints e em imagens repassadas por "
            "aplicativos (que apagam os metadados). Não prova edição, mas reduz a rastreabilidade."
        )
    width = _first(data, "ImageWidth", "ExifImageWidth")
    height = _first(data, "ImageHeight", "ExifImageHeight")
    return ExifSummary(
        camera=camera,
        captured_at=str(captured) if captured else None,
        software=str(software) if software else None,
        gps=gps,
        width=int(width) if isinstance(width, int | float) else None,
        height=int(height) if isinstance(height, int | float) else None,
        source=source,
        warnings=warnings,
    )


def exif_with_pillow(path: Path) -> ExifSummary | None:
    try:
        from PIL import ExifTags, Image
    except ImportError:
        return None
    try:
        with Image.open(path) as image:
            raw = image.getexif()
            data: dict[str, Any] = {ExifTags.TAGS.get(k, str(k)): v for k, v in raw.items()}
            exif_ifd = raw.get_ifd(ExifTags.IFD.Exif)
            data.update({ExifTags.TAGS.get(k, str(k)): v for k, v in exif_ifd.items()})
            gps_ifd = raw.get_ifd(ExifTags.IFD.GPSInfo)
            if gps_ifd:
                lat = _dms_to_decimal(gps_ifd.get(2), gps_ifd.get(1))
                lon = _dms_to_decimal(gps_ifd.get(4), gps_ifd.get(3))
                if lat is not None and lon is not None:
                    data["GPSLatitude"], data["GPSLongitude"] = lat, lon
            data["ImageWidth"], data["ImageHeight"] = image.size
    except Exception:  # corrupt or unsupported image
        return None
    return sanitize_metadata(data, source="pillow")


def _dms_to_decimal(dms: Any, ref: Any) -> float | None:
    try:
        degrees, minutes, seconds = (float(x) for x in dms)
    except (TypeError, ValueError):
        return None
    value = degrees + minutes / 60 + seconds / 3600
    return -value if str(ref).upper() in ("S", "W") else value


async def run_blocking(func: Callable[..., Any], *args: Any) -> Any:
    """Run FFmpeg/ExifTool work off the event loop (Windows-safe, unlike asyncio subprocess)."""
    return await asyncio.to_thread(func, *args)
