"""Google Gemini adapter (``google-genai`` SDK)."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import ProviderName
from app.core.errors import ProviderUnavailableError
from app.engines.base import BaseLLMProvider, ProviderCredentials
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

    def __init__(self, credentials: ProviderCredentials, client: Any | None = None) -> None:
        super().__init__(credentials)
        self._client = client or genai.Client(
            api_key=credentials.secret(),
            http_options=types.HttpOptions(timeout=int(credentials.timeout_seconds * 1000)),
        )

    async def _generate(self, prompt: str, config: types.GenerateContentConfig) -> str:
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
