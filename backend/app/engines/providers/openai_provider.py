"""OpenAI adapter (also used for any OpenAI-compatible server via ``X-Endpoint-URL``, e.g. vLLM)."""

from __future__ import annotations

from types import ModuleType
from typing import Any, ClassVar

import openai

from app.core.config import ProviderName
from app.engines.base import BaseLLMProvider, ProviderCredentials, json_system_instruction
from app.engines.providers._errors import map_openai_style_error


class OpenAICompatibleProvider(BaseLLMProvider):
    """Shared Chat Completions logic for OpenAI and Groq (same request/response shape)."""

    sdk: ClassVar[ModuleType]

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

    def _build_client(self) -> Any:
        return openai.AsyncOpenAI(
            api_key=self.credentials.secret() or "not-needed",
            base_url=self.credentials.endpoint_url or None,
            timeout=self.credentials.timeout_seconds,
            max_retries=2,
        )
