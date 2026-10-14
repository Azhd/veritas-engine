"""Shared test fixtures. No test performs real network calls."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.core.config import ProviderName, Settings
from app.engines.base import BaseLLMProvider, ProviderCredentials


def make_settings(**overrides: Any) -> Settings:
    """Settings isolated from the developer's real environment / .env file."""
    base: dict[str, Any] = {
        "default_provider": None,
        "gemini_api_key": None,
        "anthropic_api_key": None,
        "openai_api_key": None,
        "groq_api_key": None,
        "connector_backoff_base_seconds": 0.0,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


class FakeLLMProvider(BaseLLMProvider):
    """Scripted provider: returns queued raw outputs and records every call."""

    name = ProviderName.OPENAI

    def __init__(self, credentials: ProviderCredentials, outputs: list[str] | None = None) -> None:
        super().__init__(credentials)
        self.outputs = list(outputs or [])
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def generate_text(
        self, prompt: str, system_instruction: str | None = None, temperature: float = 0.2
    ) -> str:
        self.calls.append({"prompt": prompt, "system": system_instruction})
        if not self.outputs:
            raise AssertionError("FakeLLMProvider ran out of scripted outputs")
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    async def aclose(self) -> None:
        self.closed = True


def fake_credentials(**overrides: Any) -> ProviderCredentials:
    data: dict[str, Any] = {"provider": ProviderName.OPENAI, "model": "fake-model"}
    data.update(overrides)
    return ProviderCredentials(**data)


def json_response(payload: Any, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
