"""Groq adapter (fast Llama inference). Groq exposes an OpenAI-compatible Chat Completions API."""

from __future__ import annotations

from typing import Any

import groq

from app.core.config import ProviderName
from app.engines.providers.openai_provider import OpenAICompatibleProvider


class GroqProvider(OpenAICompatibleProvider):
    name = ProviderName.GROQ
    sdk = groq
    #: Groq's free catalog changes often; best general-purpose chat models first.
    preferred_models = (
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "qwen/qwen3-32b",
        "openai/gpt-oss-20b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.1-8b-instant",
    )
    #: Groq's free tier includes Whisper: same key, no cost, 25 MB per file.
    audio_models = ("whisper-large-v3-turbo", "whisper-large-v3")

    def _build_client(self) -> Any:
        return groq.AsyncGroq(
            api_key=self.credentials.secret(),
            timeout=self.credentials.timeout_seconds,
            max_retries=2,
        )
