"""Groq adapter (fast Llama inference). Groq exposes an OpenAI-compatible Chat Completions API."""

from __future__ import annotations

from typing import Any

import groq

from app.core.config import ProviderName
from app.engines.providers.openai_provider import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = ProviderName.GROQ
    sdk = groq

    def _build_client(self) -> Any:
        return groq.AsyncGroq(
            api_key=self.credentials.secret(),
            timeout=self.credentials.timeout_seconds,
            max_retries=2,
        )
