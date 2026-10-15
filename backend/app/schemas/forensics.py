"""Schemas for media forensics (Phase 3): capabilities, EXIF, C2PA, transcript and the report."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ToolStatus(BaseModel):
    name: str
    available: bool
    source: str | None = Field(
        default=None, description="'system' (installed on the OS) or 'python' (pip package)."
    )
    version: str | None = None
    hint: str | None = Field(default=None, description="How to enable it when missing.")


class MediaCapabilities(BaseModel):
    """What this server can do with media right now (graceful degradation on bare metal)."""

    ffmpeg: ToolStatus
    exiftool: ToolStatus
    image_metadata: ToolStatus
    yt_dlp: ToolStatus
    c2pa: ToolStatus
    whisper_local: ToolStatus

    @property
    def can_extract_audio(self) -> bool:
        return self.ffmpeg.available

    @property
    def can_download(self) -> bool:
        return self.yt_dlp.available


class MediaKind(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


class ExifSummary(BaseModel):
    """Sanitized metadata: only fields useful to a fact-checker, never the raw dump."""

    camera: str | None = None
    captured_at: str | None = None
    software: str | None = Field(default=None, description="Editing/creation software, if any.")
    gps: dict[str, float] | None = Field(default=None, description="Latitude/longitude, if any.")
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    source: str | None = Field(default=None, description="'exiftool' or 'pillow'.")
    warnings: list[str] = Field(default_factory=list)


class C2paVerdict(StrEnum):
    AI_GENERATED = "AI_GENERATED"
    AI_EDITED = "AI_EDITED"
    CAMERA_CAPTURE = "CAMERA_CAPTURE"
    EDITED = "EDITED"
    SIGNED_UNKNOWN = "SIGNED_UNKNOWN"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    NO_MANIFEST = "NO_MANIFEST"
    UNAVAILABLE = "UNAVAILABLE"


class C2paReport(BaseModel):
    verdict: C2paVerdict
    summary: str
    signed_by: str | None = None
    claim_generator: str | None = None
    ai_tool: str | None = None
    actions: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)


class TranscriptSegment(BaseModel):
    start_time: float = Field(ge=0, description="Seconds from the start of the media.")
    end_time: float = Field(ge=0)
    text: str

    @property
    def label(self) -> str:
        minutes, seconds = divmod(int(self.start_time), 60)
        return f"{minutes:02d}:{seconds:02d}"


class Transcript(BaseModel):
    engine: str = Field(description="groq_whisper | gemini | whisper_local | none")
    language: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    note: str | None = None

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments).strip()


class Keyframe(BaseModel):
    time_seconds: float
    data_url: str = Field(description="Small JPEG thumbnail as a data: URL.")


class MediaForensicsReport(BaseModel):
    kind: MediaKind
    filename: str | None = None
    source_url: str | None = None
    mime_type: str | None = None
    size_bytes: int
    sha256: str = Field(description="Fingerprint of the analysed file (chain of custody).")
    exif: ExifSummary | None = None
    c2pa: C2paReport | None = None
    transcript: Transcript | None = None
    keyframes: list[Keyframe] = Field(default_factory=list)
    capabilities_missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    analysed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
