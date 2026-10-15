"""OpenAI adapter (also used for any OpenAI-compatible server via ``X-Endpoint-URL``, e.g. vLLM)."""

from __future__ import annotations

from types import ModuleType
from typing import Any, ClassVar

import openai

from app.core.config import ProviderName
from app.engines.base import (
    BaseLLMProvider,
    ProviderCredentials,
    TranscriptionResult,
    json_system_instruction,
)
from app.engines.providers._errors import map_openai_style_error


class OpenAICompatibleProvider(BaseLLMProvider):
    """Shared Chat Completions logic for OpenAI and Groq (same request/response shape)."""

    sdk: ClassVar[ModuleType]
    #: Whisper models for ``/audio/transcriptions`` (first available wins).
    audio_models: ClassVar[tuple[str, ...]] = ()

    @property
    def supports_audio(self) -> bool:  # type: ignore[override]
        # Custom OpenAI-compatible servers (vLLM...) rarely expose Whisper.
        return bool(self.audio_models) and not self.credentials.endpoint_url

    def __init__(self, credentials: ProviderCredentials, client: Any | None = None) -> None:
        super().__init__(credentials)
        self._client = client or self._build_client()

    def _build_client(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    async def _chat(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        response_format: dict | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.credentials.max_output_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except self.sdk.NotFoundError as exc:
            # The model is unknown to this key (retired / not enabled): pick an available one.
            if await self.switch_to_available_model():
                return await self._chat(prompt, system_instruction, temperature, response_format)
            raise map_openai_style_error(exc, self.sdk, self.name.value) from None
        except self.sdk.APIError as exc:
            raise map_openai_style_error(exc, self.sdk, self.name.value) from None
        return response.choices[0].message.content or ""

    async def transcribe_audio(
        self, audio: bytes, filename: str, mime_type: str, language: str | None = None
    ) -> TranscriptionResult:
        last_error: Exception | None = None
        for model in self.audio_models:
            kwargs: dict[str, Any] = {
                "file": (filename, audio, mime_type),
                "model": model,
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment"],
                "temperature": 0.0,
            }
            if language:
                kwargs["language"] = language
            try:
                response = await self._client.audio.transcriptions.create(**kwargs)
            except self.sdk.NotFoundError as exc:  # model not enabled for this key: try the next
                last_error = exc
                continue
            except self.sdk.APIError as exc:
                raise map_openai_style_error(exc, self.sdk, self.name.value) from None
            segments = []
            for seg in getattr(response, "segments", None) or []:
                get = seg.get if isinstance(seg, dict) else lambda k, s=seg: getattr(s, k, None)
                text = str(get("text") or "").strip()
                if text:
                    segments.append((float(get("start") or 0), float(get("end") or 0), text))
            if not segments and getattr(response, "text", ""):
                segments = [(0.0, 0.0, str(response.text).strip())]
            return TranscriptionResult(
                segments=segments, language=getattr(response, "language", None), model=model
            )
        raise map_openai_style_error(last_error, self.sdk, self.name.value) from None

    async def list_models(self) -> list[str]:
        result = self._client.models.list()
        if hasattr(result, "__await__"):
            result = await result
        items = getattr(result, "data", None)
        if items is None:  # AsyncPaginator (openai SDK)
            items = [item async for item in result]
        return [str(getattr(item, "id", item)) for item in items]

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        return await self._chat(prompt, system_instruction, temperature)

    async def _generate_json(
        self,
        prompt: str,
        json_schema: dict,
        system_instruction: str | None,
        temperature: float,
    ) -> str:
        # ``json_object`` mode is the most widely supported (OpenAI, Groq, vLLM); schema
        # conformance is enforced afterwards by Pydantic validation in the base class.
        return await self._chat(
            prompt,
            json_system_instruction(system_instruction, json_schema),
            temperature,
            response_format={"type": "json_object"},
        )

    async def aclose(self) -> None:
        await self._client.close()


class OpenAIProvider(OpenAICompatibleProvider):
    name = ProviderName.OPENAI
    sdk = openai
    supports_custom_endpoint = True
    preferred_models = ("gpt-4o", "gpt-4.1", "gpt-4o-mini", "gpt-4.1-mini")
    audio_models = ("whisper-1",)

    def _build_client(self) -> Any:
        return openai.AsyncOpenAI(
            api_key=self.credentials.secret() or "not-needed",
            base_url=self.credentials.endpoint_url or None,
            timeout=self.credentials.timeout_seconds,
            max_retries=2,
        )
