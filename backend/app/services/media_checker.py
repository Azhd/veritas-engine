"""Media fact-checking pipeline (TASK 3.5).

file or link -> forensics (fingerprint, metadata, C2PA, keyframes) -> transcript with timestamps
-> checkable claims ("aos 01:23 ...") -> each claim checked against primary sources with the same
engine as text claims. Works without any AI key (citizen mode), just with less depth.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import UploadFile

from app.core.config import Settings
from app.engines.base import BaseLLMProvider
from app.forensics.audio_transcriber import build_transcriber, extract_timed_claims
from app.forensics.c2pa_validator import C2paValidator
from app.forensics.media_inspector import CHUNK, MediaError, MediaInspector
from app.forensics.tools import detect_capabilities
from app.schemas.fact_check import CountryContext, MediaFactCheckReport, TimedCheck
from app.services.fact_checker import FactCheckService

logger = logging.getLogger(__name__)

MAX_CLAIMS = 3


async def _upload_chunks(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(CHUNK):
        yield chunk


class MediaCheckService:
    def __init__(
        self,
        settings: Settings,
        fact_checker: FactCheckService,
        inspector: MediaInspector | None = None,
    ) -> None:
        self.settings = settings
        self.fact_checker = fact_checker
        self.inspector = inspector or MediaInspector(settings)

    async def check(
        self,
        llm: BaseLLMProvider | None,
        *,
        upload: UploadFile | None = None,
        url: str | None = None,
        claim: str | None = None,
        country: CountryContext | None = None,
        notes: list[str] | None = None,
    ) -> MediaFactCheckReport:
        if upload is None and not url:
            raise MediaError("Envie um arquivo ou cole o link do vídeo, áudio ou imagem.")
        notes = list(notes or [])
        caps = await asyncio.to_thread(detect_capabilities)

        async with self.inspector.workspace() as workdir:
            if upload is not None:
                media = await self.inspector.ingest_stream(
                    _upload_chunks(upload),
                    workdir,
                    filename=upload.filename,
                    declared_mime=upload.content_type,
                )
            else:
                media = await self.inspector.ingest_url(str(url), workdir)
            forensics = await self.inspector.analyse(
                media,
                workdir,
                provenance=C2paValidator() if caps.c2pa.available else None,
                transcriber=build_transcriber(llm, self.settings, caps),
            )

        checks: list[TimedCheck] = []
        context = (claim or "").strip()
        if context:
            report = await self.fact_checker.check_text(
                context, llm, country_override=country, notes=list(notes)
            )
            checks.append(TimedCheck(label="Texto informado", quote=context, report=report))

        transcript = forensics.transcript
        if transcript and transcript.note:
            notes.append(transcript.note)
        if transcript and transcript.segments:
            timed = await extract_timed_claims(transcript, llm, MAX_CLAIMS)
            if not timed:
                notes.append("Nenhuma afirmação verificável foi encontrada na fala.")
            # Sequential on purpose: free tiers (Groq/Gemini) limit requests per minute.
            for item in timed:
                report = await self.fact_checker.check_text(
                    item.claim, llm, country_override=country, notes=list(notes)
                )
                checks.append(
                    TimedCheck(
                        start_time=item.start_time,
                        label=item.label,
                        quote=item.quote or item.claim,
                        report=report,
                    )
                )

        ai_used = any(c.report.ai_used for c in checks) or (
            llm is not None and bool(transcript and transcript.engine not in ("none",))
        )
        return MediaFactCheckReport(
            forensics=forensics,
            checks=checks,
            ai_used=ai_used,
            provider=llm.name.value if llm else "nenhum",
            model=llm.model if llm else "nenhum",
            notes=list(dict.fromkeys(notes)),
        )
