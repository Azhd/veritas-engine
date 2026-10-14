"""Anthropic Claude adapter."""

from __future__ import annotations

from typing import Any

import anthropic

from app.core.config import ProviderName
from app.engines.base import BaseLLMProvider, ProviderCredentials
from app.engines.providers._errors import map_openai_style_error


class ClaudeProvider(BaseLLMProvider):
    name = ProviderName.ANTHROPIC

    def __init__(self, credentials: ProviderCredentials, client: Any | None = None) -> None:
        super().__init__(credentials)
        self._client = client or anthropic.AsyncAnthropic(
            api_key=credentials.secret(),
            timeout=credentials.timeout_seconds,
            max_retries=2,
        )

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        # ``temperature`` is accepted for interface parity but not forwarded: current Claude
        # models manage sampling themselves and the SDK no longer exposes the parameter.
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.credentials.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            kwargs["system"] = system_instruction
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise map_openai_style_error(exc, anthropic, self.name.value) from None
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )

    async def aclose(self) -> None:
        await self._client.close()
