"""Ollama adapter for local models, via its REST API (``POST /api/chat``)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import ProviderName
from app.core.errors import ProviderUnavailableError
from app.engines.base import BaseLLMProvider, ProviderCredentials
from app.engines.providers._errors import map_status_code


class OllamaProvider(BaseLLMProvider):
    name = ProviderName.OLLAMA
    requires_api_key = False
    supports_custom_endpoint = True

    def __init__(
        self, credentials: ProviderCredentials, client: httpx.AsyncClient | None = None
    ) -> None:
        super().__init__(credentials)
        if not credentials.endpoint_url:
            raise ValueError("Ollama provider requires an endpoint URL")
        headers = {}
        # Hosted / reverse-proxied Ollama instances may require a bearer token.
        if credentials.secret():
            headers["Authorization"] = f"Bearer {credentials.secret()}"
        self._client = client or httpx.AsyncClient(
            base_url=credentials.endpoint_url.rstrip("/"),
            timeout=credentials.timeout_seconds,
            headers=headers,
        )

    async def _chat(
        self,
        prompt: str,
        system_instruction: str | None,
        temperature: float,
        response_format: dict | str | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if response_format is not None:
            payload["format"] = response_format
        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.TimeoutException:
            raise ProviderUnavailableError("ollama: request timed out.") from None
        except httpx.HTTPError:
            raise ProviderUnavailableError("ollama: could not connect to the endpoint.") from None
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = None
            raise map_status_code(response.status_code, self.name.value, body)
        try:
            return response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise ProviderUnavailableError("ollama: unexpected response format.") from None

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
        # Ollama >= 0.5 accepts a full JSON schema in ``format`` (structured outputs).
        return await self._chat(prompt, system_instruction, temperature, json_schema)

    async def aclose(self) -> None:
        await self._client.aclose()
