"""BYOK engine: factory resolution, key isolation and provider adapters (all mocked)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import anthropic
import groq
import httpx
import openai
import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel

from app.core.config import ProviderName
from app.core.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderOutputError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from app.engines.base import ProviderCredentials
from app.engines.factory import ProviderFactory
from app.engines.json_utils import extract_json
from app.engines.providers.claude_provider import ClaudeProvider
from app.engines.providers.gemini_provider import GeminiProvider
from app.engines.providers.groq_provider import GroqProvider
from app.engines.providers.ollama_provider import OllamaProvider
from app.engines.providers.openai_provider import OpenAIProvider
from tests.conftest import FakeLLMProvider, fake_credentials, make_settings


class Answer(BaseModel):
    answer: str
    score: float


# =============================================================== ProviderFactory
class TestProviderFactory:
    @pytest.mark.parametrize(
        ("header", "expected_cls"),
        [
            ("gemini", GeminiProvider),
            ("anthropic", ClaudeProvider),
            ("claude", ClaudeProvider),
            ("OpenAI", OpenAIProvider),
            ("groq", GroqProvider),
        ],
    )
    def test_creates_provider_from_header(self, settings, header, expected_cls):
        provider = ProviderFactory(settings).create(provider=header, api_key="sk-user-123")
        assert isinstance(provider, expected_cls)
        assert provider.credentials.secret() == "sk-user-123"
        assert provider.model == settings.default_model(provider.name)

    def test_ollama_needs_no_key_and_uses_default_endpoint(self, settings):
        provider = ProviderFactory(settings).create(provider="ollama")
        assert isinstance(provider, OllamaProvider)
        assert provider.credentials.api_key is None
        assert provider.credentials.endpoint_url == "http://localhost:11434"

    def test_from_headers_is_case_insensitive_and_reads_all_fields(self, settings):
        provider = ProviderFactory(settings).from_headers(
            {
                "X-PROVIDER": "openai",
                "x-api-key": "sk-abc",
                "X-Endpoint-URL": "http://vllm.local:8000/v1/",
                "X-Model": "my-model",
            }
        )
        assert provider.credentials.endpoint_url == "http://vllm.local:8000/v1"
        assert provider.model == "my-model"
        assert provider.credentials.secret() == "sk-abc"

    def test_missing_provider_without_default_is_rejected(self, settings):
        with pytest.raises(ProviderConfigurationError, match="X-Provider"):
            ProviderFactory(settings).create()

    def test_default_provider_from_env(self):
        settings = make_settings(default_provider="groq", groq_api_key="gsk-env")
        provider = ProviderFactory(settings).create()
        assert isinstance(provider, GroqProvider)
        assert provider.credentials.secret() == "gsk-env"

    def test_unknown_provider_is_rejected(self, settings):
        with pytest.raises(ProviderConfigurationError, match="Unsupported provider"):
            ProviderFactory(settings).create(provider="skynet", api_key="x")

    def test_missing_key_is_rejected_when_no_fallback(self, settings):
        with pytest.raises(ProviderConfigurationError, match="requires an API key"):
            ProviderFactory(settings).create(provider="anthropic")

    def test_env_fallback_used_only_when_header_absent(self):
        settings = make_settings(openai_api_key="sk-server")
        factory = ProviderFactory(settings)
        assert factory.create(provider="openai").credentials.secret() == "sk-server"
        assert factory.create(provider="openai", api_key="sk-user").credentials.secret() == (
            "sk-user"
        )

    def test_env_fallback_can_be_disabled(self):
        settings = make_settings(openai_api_key="sk-server", allow_env_fallback=False)
        with pytest.raises(ProviderConfigurationError):
            ProviderFactory(settings).create(provider="openai")

    @pytest.mark.parametrize(
        "endpoint",
        ["ftp://host", "not-a-url", "http://user:pass@host:11434", "/relative/path"],
    )
    def test_invalid_endpoints_are_rejected(self, settings, endpoint):
        with pytest.raises(ProviderConfigurationError):
            ProviderFactory(settings).create(provider="ollama", endpoint_url=endpoint)

    def test_endpoint_rejected_for_providers_without_support(self, settings):
        with pytest.raises(ProviderConfigurationError, match="does not accept"):
            ProviderFactory(settings).create(
                provider="anthropic", api_key="k", endpoint_url="http://evil.example"
            )

    def test_custom_endpoints_can_be_disabled(self):
        settings = make_settings(allow_custom_endpoints=False)
        with pytest.raises(ProviderConfigurationError, match="disabled"):
            ProviderFactory(settings).create(provider="ollama", endpoint_url="http://h:1")

    def test_malformed_key_is_rejected(self, settings):
        with pytest.raises(ProviderConfigurationError, match="Malformed"):
            ProviderFactory(settings).create(provider="openai", api_key="sk bad key")

    def test_each_request_gets_isolated_instance_and_credentials(self, settings):
        factory = ProviderFactory(settings)
        first = factory.create(provider="openai", api_key="sk-user-A")
        second = factory.create(provider="openai", api_key="sk-user-B")
        third = factory.create(provider="openai", api_key="sk-user-C")
        assert first is not second
        assert first._client is not second._client
        assert [p.credentials.secret() for p in (first, second, third)] == [
            "sk-user-A",
            "sk-user-B",
            "sk-user-C",
        ]
        assert first._client.api_key == "sk-user-A"
        assert second._client.api_key == "sk-user-B"

    def test_key_never_appears_in_repr(self, settings):
        provider = ProviderFactory(settings).create(provider="openai", api_key="sk-super-secret")
        assert "sk-super-secret" not in repr(provider)
        assert "sk-super-secret" not in repr(provider.credentials)
        assert "sk-super-secret" not in str(provider.credentials)

    def test_errors_never_echo_the_key(self, settings):
        with pytest.raises(ProviderConfigurationError) as exc_info:
            ProviderFactory(settings).create(provider="nope", api_key="sk-leak-me")
        assert "sk-leak-me" not in str(exc_info.value)


# =============================================================== structured output (base class)
class TestStructuredGeneration:
    async def test_parses_fenced_json(self):
        llm = FakeLLMProvider(
            fake_credentials(), ['Sure!\n```json\n{"answer": "ok", "score": 0.9}\n```']
        )
        result = await llm.generate_structured("q", Answer)
        assert result == Answer(answer="ok", score=0.9)
        assert "JSON Schema" in llm.calls[0]["system"]

    async def test_retries_once_on_invalid_output(self):
        llm = FakeLLMProvider(fake_credentials(), ["not json", '{"answer": "ok", "score": 1}'])
        result = await llm.generate_structured("q", Answer)
        assert result.answer == "ok"
        assert len(llm.calls) == 2
        assert "previous answer was invalid" in llm.calls[1]["prompt"]

    async def test_raises_after_exhausting_retries(self):
        llm = FakeLLMProvider(fake_credentials(), ['{"answer": 1}', "garbage"])
        with pytest.raises(ProviderOutputError):
            await llm.generate_structured("q", Answer)

    def test_extract_json_variants(self):
        assert extract_json('{"a": 1}') == {"a": 1}
        assert extract_json('Answer: {"a": {"b": [1, 2]}} trailing') == {"a": {"b": [1, 2]}}
        with pytest.raises(ValueError):
            extract_json("")
        with pytest.raises(ValueError):
            extract_json("no json here")


# =============================================================== OpenAI / Groq adapters
def _chat_completion(content: str) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _openai_client(content: str = "hello") -> MagicMock:
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_chat_completion(content))
    client.close = AsyncMock()
    return client


def _status_error(sdk, cls_name: str, status: int) -> Exception:
    request = httpx.Request("POST", "https://api.example/v1")
    response = httpx.Response(status, request=request)
    return getattr(sdk, cls_name)("boom sk-secret-in-body", response=response, body=None)


class TestOpenAICompatibleAdapters:
    @pytest.mark.parametrize("provider_cls", [OpenAIProvider, GroqProvider])
    async def test_generate_text_builds_messages(self, provider_cls):
        client = _openai_client("resposta")
        provider = provider_cls(fake_credentials(provider=provider_cls.name), client=client)
        text = await provider.generate_text("pergunta", system_instruction="sys", temperature=0.3)
        assert text == "resposta"
        kwargs = client.chat.completions.create.await_args.kwargs
        assert kwargs["messages"] == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "pergunta"},
        ]
        assert kwargs["temperature"] == 0.3
        assert kwargs["model"] == "fake-model"

    async def test_structured_uses_json_mode(self):
        client = _openai_client('{"answer": "x", "score": 0.5}')
        provider = OpenAIProvider(fake_credentials(), client=client)
        result = await provider.generate_structured("q", Answer)
        assert result.score == 0.5
        kwargs = client.chat.completions.create.await_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.parametrize(
        ("cls_name", "status", "expected"),
        [
            ("AuthenticationError", 401, ProviderAuthenticationError),
            ("RateLimitError", 429, ProviderRateLimitError),
            ("BadRequestError", 400, ProviderConfigurationError),
            ("InternalServerError", 500, ProviderUnavailableError),
        ],
    )
    async def test_sdk_errors_are_mapped_and_sanitized(self, cls_name, status, expected):
        client = _openai_client()
        client.chat.completions.create.side_effect = _status_error(openai, cls_name, status)
        provider = OpenAIProvider(fake_credentials(), client=client)
        with pytest.raises(expected) as exc_info:
            await provider.generate_text("q")
        assert "sk-secret" not in str(exc_info.value)

    async def test_openai_custom_base_url_is_applied(self):
        provider = OpenAIProvider(
            fake_credentials(endpoint_url="http://localhost:8000/v1", api_key=None)
        )
        assert str(provider._client.base_url).startswith("http://localhost:8000/v1")
        await provider.aclose()


# =============================================================== Claude adapter
class TestClaudeAdapter:
    async def test_generate_text_joins_text_blocks(self):
        client = MagicMock()
        client.messages.create = AsyncMock(
            return_value=SimpleNamespace(
                content=[
                    SimpleNamespace(type="thinking", thinking="..."),
                    SimpleNamespace(type="text", text="Olá "),
                    SimpleNamespace(type="text", text="mundo"),
                ]
            )
        )
        provider = ClaudeProvider(fake_credentials(provider=ProviderName.ANTHROPIC), client=client)
        assert await provider.generate_text("oi", system_instruction="sys") == "Olá mundo"
        kwargs = client.messages.create.await_args.kwargs
        assert kwargs["system"] == "sys"
        assert kwargs["messages"] == [{"role": "user", "content": "oi"}]
        assert "max_tokens" in kwargs

    async def test_auth_error_mapped(self):
        client = MagicMock()
        client.messages.create = AsyncMock(
            side_effect=_status_error(anthropic, "AuthenticationError", 401)
        )
        provider = ClaudeProvider(fake_credentials(provider=ProviderName.ANTHROPIC), client=client)
        with pytest.raises(ProviderAuthenticationError):
            await provider.generate_text("oi")


# =============================================================== Gemini adapter
class TestGeminiAdapter:
    def _client(self, text: str = '{"answer": "g", "score": 0.1}') -> MagicMock:
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(return_value=SimpleNamespace(text=text))
        client.aio.aclose = AsyncMock()
        return client

    async def test_structured_uses_native_json_schema(self):
        client = self._client()
        provider = GeminiProvider(fake_credentials(provider=ProviderName.GEMINI), client=client)
        result = await provider.generate_structured("q", Answer, system_instruction="sys")
        assert result.answer == "g"
        config = client.aio.models.generate_content.await_args.kwargs["config"]
        assert config.response_mime_type == "application/json"
        assert config.response_json_schema["title"] == "Answer"
        assert config.system_instruction == "sys"

    async def test_api_error_mapped_by_status(self):
        client = self._client()
        client.aio.models.generate_content.side_effect = genai_errors.ClientError(
            429, {"error": {"message": "quota"}}
        )
        provider = GeminiProvider(fake_credentials(provider=ProviderName.GEMINI), client=client)
        with pytest.raises(ProviderRateLimitError):
            await provider.generate_text("q")


# =============================================================== Ollama adapter
class TestOllamaAdapter:
    def _provider(self, handler, api_key=None) -> OllamaProvider:
        creds = ProviderCredentials(
            provider=ProviderName.OLLAMA,
            model="llama3.1",
            endpoint_url="http://ollama.local:11434",
            api_key=api_key,
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        client = httpx.AsyncClient(
            base_url="http://ollama.local:11434",
            transport=httpx.MockTransport(handler),
            headers=headers,
        )
        return OllamaProvider(creds, client=client)

    async def test_chat_payload_and_structured_format(self):
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            assert request.url.path == "/api/chat"
            return httpx.Response(
                200, json={"message": {"content": '{"answer": "local", "score": 0.7}'}}
            )

        provider = self._provider(handler)
        result = await provider.generate_structured("q", Answer, system_instruction="sys")
        assert result.answer == "local"
        assert seen[0]["stream"] is False
        assert seen[0]["format"]["title"] == "Answer"
        assert seen[0]["messages"][0] == {"role": "system", "content": "sys"}
        await provider.aclose()

    async def test_http_errors_mapped(self):
        provider = self._provider(lambda r: httpx.Response(404, json={"error": "model"}))
        with pytest.raises(ProviderConfigurationError):
            await provider.generate_text("q")

    async def test_connection_error_mapped(self):
        def handler(request):
            raise httpx.ConnectError("refused")

        provider = self._provider(handler)
        with pytest.raises(ProviderUnavailableError):
            await provider.generate_text("q")

    def test_builds_bearer_header_from_key(self):
        from pydantic import SecretStr

        provider = OllamaProvider(
            ProviderCredentials(
                provider=ProviderName.OLLAMA,
                model="m",
                endpoint_url="http://h:1",
                api_key=SecretStr("tok"),
            )
        )
        assert provider._client.headers["Authorization"] == "Bearer tok"


# =============================================================== model fallback (catalog changes)
class TestModelFallback:
    def test_pick_model_prefers_known_good_and_skips_non_chat(self):
        from app.engines.base import pick_model
        from app.engines.providers.groq_provider import GroqProvider

        available = [
            "whisper-large-v3",
            "meta-llama/llama-guard-4-12b",
            "llama-3.1-8b-instant",
            "openai/gpt-oss-120b",
            "playai-tts",
        ]
        chosen = pick_model(
            available,
            GroqProvider.preferred_models,
            GroqProvider.non_chat_markers,
            "llama-3.3-70b-versatile",
        )
        assert chosen == "openai/gpt-oss-120b"

    def test_pick_model_falls_back_to_largest_unknown_model(self):
        from app.engines.base import pick_model

        chosen = pick_model(["acme/tiny-8b", "acme/big-70b", "acme-guard-12b"], (), ("guard",), "x")
        assert chosen == "acme/big-70b"
        assert pick_model(["whisper"], (), ("whisper",), "x") is None

    async def test_groq_switches_model_after_404_and_reports_it(self):
        not_found = _status_error(groq, "NotFoundError", 404)
        client = _openai_client("resposta")
        client.chat.completions.create.side_effect = [not_found, _chat_completion("resposta")]
        client.models.list = AsyncMock(
            return_value=SimpleNamespace(
                data=[
                    SimpleNamespace(id="whisper-large-v3"),
                    SimpleNamespace(id="openai/gpt-oss-120b"),
                ]
            )
        )
        provider = GroqProvider(
            fake_credentials(provider=ProviderName.GROQ, model="llama-3.3-70b-versatile"),
            client=client,
        )
        assert await provider.generate_text("oi") == "resposta"
        calls = client.chat.completions.create.await_args_list
        assert [c.kwargs["model"] for c in calls] == [
            "llama-3.3-70b-versatile",
            "openai/gpt-oss-120b",
        ]
        assert provider.model == "openai/gpt-oss-120b"

    async def test_fallback_is_tried_only_once(self):
        not_found = _status_error(groq, "NotFoundError", 404)
        client = _openai_client()
        client.chat.completions.create.side_effect = not_found
        client.models.list = AsyncMock(
            return_value=SimpleNamespace(data=[SimpleNamespace(id="openai/gpt-oss-20b")])
        )
        provider = GroqProvider(fake_credentials(provider=ProviderName.GROQ), client=client)
        with pytest.raises(ProviderConfigurationError, match="not found"):
            await provider.generate_text("oi")
        assert client.chat.completions.create.await_count == 2
        assert client.models.list.await_count == 1

    async def test_gemini_switches_model_after_404(self):
        client = MagicMock()
        client.aio.models.generate_content = AsyncMock(
            side_effect=[
                genai_errors.ClientError(404, {"error": {"message": "model not found"}}),
                SimpleNamespace(text="ok"),
            ]
        )

        async def _pager():
            for name, actions in (
                ("models/text-embedding-004", ["embedContent"]),
                ("models/gemini-2.5-flash", ["generateContent"]),
            ):
                yield SimpleNamespace(name=name, supported_actions=actions)

        client.aio.models.list = AsyncMock(return_value=_pager())
        provider = GeminiProvider(
            fake_credentials(provider=ProviderName.GEMINI, model="gemini-flash-latest"),
            client=client,
        )
        assert await provider.generate_text("oi") == "ok"
        assert provider.model == "gemini-2.5-flash"
