"""Abstract BYOK provider contract.

Every adapter receives a :class:`ProviderCredentials` instance created *per request* by the
:class:`~app.engines.factory.ProviderFactory`. Providers hold no global state, so a key sent by
one user can never leak into another user's request.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar

from pydantic import BaseModel, SecretStr, ValidationError

from app.core.config import ProviderName
from app.core.errors import ProviderOutputError
from app.engines.json_utils import extract_json

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ProviderCredentials:
    """Transient, per-request credentials. ``repr`` never exposes the key."""

    provider: ProviderName
    model: str
    api_key: SecretStr | None = field(default=None, repr=False)
    endpoint_url: str | None = None
    timeout_seconds: float = 60.0
    max_output_tokens: int = 4096

    def secret(self) -> str | None:
        return self.api_key.get_secret_value() if self.api_key else None


class BaseLLMProvider(ABC):
    """Uniform interface over Gemini, Claude, OpenAI, Groq and Ollama."""

    name: ClassVar[ProviderName]
    requires_api_key: ClassVar[bool] = True
    supports_custom_endpoint: ClassVar[bool] = False

    #: How many times ``generate_structured`` re-asks the model after an invalid JSON answer.
    structured_retries: ClassVar[int] = 1

    def __init__(self, credentials: ProviderCredentials) -> None:
        self.credentials = credentials

    @property
    def model(self) -> str:
        return self.credentials.model

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        """Plain text completion."""

    async def generate_structured(
        self,
        prompt: str,
        schema: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.0,
    ) -> T:
        """Completion validated against a Pydantic ``schema``.

        Adapters provide the raw JSON via :meth:`_generate_json` (using native JSON modes where the
        provider supports them). Invalid answers are retried with the validation error as feedback.
        """
        json_schema = schema.model_json_schema()
        current_prompt = prompt
        last_error: Exception | None = None
        for _ in range(self.structured_retries + 1):
            raw = await self._generate_json(
                current_prompt, json_schema, system_instruction, temperature
            )
            try:
                return schema.model_validate(extract_json(raw))
            except (ValueError, ValidationError) as exc:
                last_error = exc
                current_prompt = (
                    f"{prompt}\n\nYour previous answer was invalid ({_short(exc)}). "
                    "Answer again with ONLY a JSON object that matches the schema."
                )
        raise ProviderOutputError(
            f"{self.name} returned output that does not match {schema.__name__}: "
            f"{_short(last_error)}"
        )

    async def _generate_json(
        self,
        prompt: str,
        json_schema: dict,
        system_instruction: str | None,
        temperature: float,
    ) -> str:
        """Default: instruct the model through the system prompt. Override for native JSON modes."""
        return await self.generate_text(
            prompt,
            system_instruction=json_system_instruction(system_instruction, json_schema),
            temperature=temperature,
        )

    async def aclose(self) -> None:  # noqa: B027 - optional hook
        """Release network resources held by the adapter."""


def json_system_instruction(system_instruction: str | None, json_schema: dict) -> str:
    base = (system_instruction or "").strip()
    return (
        f"{base}\n\n"
        "Respond ONLY with a single valid JSON object (no markdown, no commentary) that conforms "
        f"to this JSON Schema:\n{json.dumps(json_schema, ensure_ascii=False)}"
    ).strip()


def _short(exc: Exception | None, limit: int = 300) -> str:
    text = str(exc) if exc else "unknown error"
    return text if len(text) <= limit else text[:limit] + "..."
