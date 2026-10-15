"""Detects the media tools available on this machine (TASK 3.1).

Veritas must keep working on a plain Windows install: every tool is optional and the report says
what is missing and how to enable it. Resolution order for FFmpeg: the system binary, then the
binary bundled in the ``imageio-ffmpeg`` wheel (``requirements-media.txt``).
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
import shutil
import subprocess
from functools import lru_cache

from app.schemas.forensics import MediaCapabilities, ToolStatus

logger = logging.getLogger(__name__)

FULL_HINT = "Instale a perícia completa: .\\run.ps1 -Full (Windows) ou ./run.sh --full"
WHISPER_HINT = (
    "Opcional: .\\run.ps1 -Whisper para transcrever offline. Sem ele, o Veritas usa o Whisper "
    "gratuito do Groq (mesma chave) ou o Gemini."
)


def _package_version(dist: str) -> str | None:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def _binary_version(path: str, flag: str) -> str | None:
    try:
        out = subprocess.run(
            [path, flag], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    first = out.strip().splitlines()[0] if out.strip() else ""
    return first[:80] or None


def find_ffmpeg() -> tuple[str | None, str | None]:
    """(path, source) of an FFmpeg executable, or (None, None)."""
    system = shutil.which("ffmpeg")
    if system:
        return system, "system"
    if importlib.util.find_spec("imageio_ffmpeg") is not None:
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe(), "python"
        except Exception:  # broken wheel / unsupported platform
            return None, None
    return None, None


def find_exiftool() -> str | None:
    return shutil.which("exiftool")


def _c2pa_status() -> ToolStatus:
    if importlib.util.find_spec("c2pa") is None:
        return ToolStatus(name="c2pa", available=False, hint=FULL_HINT)
    try:
        import c2pa  # noqa: F401  (loads the native library)
    except Exception as exc:  # DLL missing for this platform
        return ToolStatus(
            name="c2pa", available=False, hint=f"c2pa-python não carregou ({type(exc).__name__})"
        )
    return ToolStatus(
        name="c2pa", available=True, source="python", version=_package_version("c2pa-python")
    )


def _python_tool(name: str, module: str, dist: str, hint: str) -> ToolStatus:
    if importlib.util.find_spec(module) is None:
        return ToolStatus(name=name, available=False, hint=hint)
    return ToolStatus(name=name, available=True, source="python", version=_package_version(dist))


@lru_cache(maxsize=1)
def detect_capabilities() -> MediaCapabilities:
    ffmpeg_path, ffmpeg_source = find_ffmpeg()
    exiftool_path = find_exiftool()
    caps = MediaCapabilities(
        ffmpeg=ToolStatus(
            name="ffmpeg",
            available=ffmpeg_path is not None,
            source=ffmpeg_source,
            version=_binary_version(ffmpeg_path, "-version") if ffmpeg_path else None,
            hint=None if ffmpeg_path else FULL_HINT,
        ),
        exiftool=ToolStatus(
            name="exiftool",
            available=exiftool_path is not None,
            source="system" if exiftool_path else None,
            version=_binary_version(exiftool_path, "-ver") if exiftool_path else None,
            hint=None
            if exiftool_path
            else "Opcional: imagens já são lidas com Pillow; o ExifTool cobre vídeo e áudio.",
        ),
        image_metadata=_python_tool(
            "pillow", "PIL", "Pillow", "pip install Pillow (já incluído no requirements.txt)"
        ),
        yt_dlp=_python_tool(
            "yt-dlp", "yt_dlp", "yt-dlp", "pip install yt-dlp (já incluído no requirements.txt)"
        ),
        c2pa=_c2pa_status(),
        whisper_local=_python_tool(
            "faster-whisper", "faster_whisper", "faster-whisper", WHISPER_HINT
        ),
    )
    for tool in (caps.ffmpeg, caps.exiftool, caps.image_metadata, caps.yt_dlp, caps.c2pa):
        if tool.available:
            logger.info("media tool %s: %s (%s)", tool.name, tool.source, tool.version or "?")
        else:
            logger.warning("media tool %s unavailable: %s", tool.name, tool.hint)
    return caps


def ffmpeg_path() -> str | None:
    return find_ffmpeg()[0]
