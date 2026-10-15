"""Media forensics routes (Phase 3)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from app.forensics.tools import detect_capabilities
from app.schemas.forensics import MediaCapabilities

router = APIRouter(prefix="/media", tags=["media"])


class CapabilitiesResponse(BaseModel):
    capabilities: MediaCapabilities
    ready_for: list[str]
    missing: list[str]


@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="O que este servidor consegue periciar (ferramentas de mídia disponíveis)",
)
async def media_capabilities() -> CapabilitiesResponse:
    caps = await asyncio.to_thread(detect_capabilities)
    ready = ["metadados de imagem"] if caps.image_metadata.available else []
    if caps.yt_dlp.available:
        ready.append("baixar mídia de links")
    if caps.ffmpeg.available:
        ready += ["extrair áudio", "quadros-chave de vídeo"]
    if caps.c2pa.available:
        ready.append("proveniência C2PA (detecção de IA)")
    if caps.whisper_local.available:
        ready.append("transcrição offline")
    missing = [
        f"{tool.name}: {tool.hint}"
        for tool in (caps.ffmpeg, caps.c2pa, caps.yt_dlp, caps.image_metadata)
        if not tool.available and tool.hint
    ]
    return CapabilitiesResponse(capabilities=caps, ready_for=ready, missing=missing)
