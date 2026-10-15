"""Google Gemini adapter (``google-genai`` SDK)."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import ProviderName
from app.core.errors import ProviderOutputError, ProviderUnavailableError
from app.engines.base import BaseLLMProvider, ProviderCredentials, TranscriptionResult
from app.engines.json_utils import extract_json
from app.engines.providers._errors import map_status_code


class GeminiProvider(BaseLLMProvider):
    name = ProviderName.GEMINI
    preferred_models = (
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash-lite",
    )
    non_chat_markers = (*BaseLLMProvider.non_chat_markers, "pro", "exp", "preview", "gemma")
    supports_audio = True

    def __init__(self, credentials: ProviderCredentials, client: Any | None = None) -> None:
        super().__init__(credentials)
        self._client = client or genai.Client(
            api_key=credentials.secret(),
            http_options=types.HttpOptions(timeout=int(credentials.timeout_seconds * 1000)),
        )

    async def _generate(self, prompt: Any, config: types.GenerateContentConfig) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
        except genai_errors.APIError as exc:
            if getattr(exc, "code", None) == 404 and await self.switch_to_available_model():
                return await self._generate(prompt, config)
            body = getattr(exc, "details", None)
            if not isinstance(body, dict):
                body = {"error": {"message": getattr(exc, "message", None), "code": exc.status}}
            raise map_status_code(getattr(exc, "code", None), self.name.value, body) from None
        except Exception as exc:  # network errors surface as httpx exceptions
            raise ProviderUnavailableError(
                f"{self.name.value}: unexpected provider error ({type(exc).__name__})."
            ) from None
        return response.text or ""

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=self.credentials.max_output_tokens,
        )
        return await self._generate(prompt, config)

    async def _generate_json(
        self,
        prompt: str,
        json_schema: dict,
        system_instruction: str | None,
        temperature: float,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
            max_output_tokens=self.credentials.max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=json_schema,
        )
        return await self._generate(prompt, config)

    async def transcribe_audio(
        self, audio: bytes, filename: str, mime_type: str, language: str | None = None
    ) -> TranscriptionResult:
        """Gemini listens to the audio directly and returns timestamped segments as JSON."""
        schema = {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "start": {"type": "number"},
                            "end": {"type": "number"},
                            "text": {"type": "string"},
                        },
                        "required": ["start", "end", "text"],
                    },
                },
            },
            "required": ["segments"],
        }
        config = types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=self.credentials.max_output_tokens * 2,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        prompt = (
            "Transcreva fielmente este áudio, no idioma original, em trechos de 5 a 20 segundos. "
            "Para cada trecho informe start e end em segundos desde o início. Não resuma e não "
            "invente falas; trechos inaudíveis viram [inaudível]."
        )
        contents = [types.Part.from_bytes(data=audio, mime_type=mime_type), prompt]
        raw = await self._generate(contents, config)
        try:
            payload = extract_json(raw)
            segments = [
                (float(s["start"]), float(s["end"]), str(s["text"]).strip())
                for s in payload.get("segments", [])
                if str(s.get("text", "")).strip()
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderOutputError("gemini: transcrição em formato inválido") from exc
        return TranscriptionResult(
            segments=segments, language=payload.get("language"), model=self.model
        )

    async def list_models(self) -> list[str]:
        names: list[str] = []
        async for model in await self._client.aio.models.list():
            actions = getattr(model, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            names.append(str(model.name).removeprefix("models/"))
        return names

    async def aclose(self) -> None:
        await self._client.aio.aclose()
