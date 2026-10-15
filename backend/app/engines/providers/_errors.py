"""Translate SDK exceptions (anthropic / openai / groq share the same hierarchy) into domain errors.

The provider's own short reason (e.g. Groq's ``invalid_api_key``) is appended because it tells the
user what to fix, but it is sanitized first: error bodies may echo part of the key (OpenAI does),
so anything that looks like a credential is redacted and the text is truncated.
"""

from __future__ import annotations

import re
from types import ModuleType
from typing import Any

from app.core.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    VeritasError,
)

#: Credential-looking tokens: provider prefixes (sk-, gsk_, AIza...) or long opaque strings.
_SECRET_RE = re.compile(
    r"(?:sk-|gsk_|sk-ant-|AIza|xai-|pplx-)[\w\-*.]*|\b[\w\-]{24,}\b", re.IGNORECASE
)
_MAX_REASON = 120


def provider_reason(body: Any) -> str | None:
    """Short, redacted reason taken from an OpenAI-style error body."""
    error = body.get("error", body) if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None
    parts = [str(error.get(k)) for k in ("message", "code") if error.get(k)]
    if not parts:
        return None
    reason = " / ".join(dict.fromkeys(parts))
    reason = _SECRET_RE.sub("[oculto]", reason)
    return reason[:_MAX_REASON]


def _with_reason(message: str, exc: Exception) -> str:
    reason = provider_reason(getattr(exc, "body", None))
    status = getattr(exc, "status_code", None)
    details = ", ".join(p for p in (f"HTTP {status}" if status else "", reason or "") if p)
    return f"{message} ({details})." if details else f"{message}."


def map_openai_style_error(exc: Exception, sdk: ModuleType, provider: str) -> VeritasError:
    if isinstance(exc, sdk.AuthenticationError | sdk.PermissionDeniedError):
        return ProviderAuthenticationError(
            _with_reason(f"{provider}: API key rejected or lacks permission", exc)
        )
    if isinstance(exc, sdk.RateLimitError):
        return ProviderRateLimitError(
            _with_reason(f"{provider}: rate limit or quota exceeded", exc)
        )
    if isinstance(exc, sdk.NotFoundError):
        return ProviderConfigurationError(
            _with_reason(f"{provider}: model or endpoint not found", exc)
        )
    if isinstance(exc, sdk.BadRequestError):
        return ProviderConfigurationError(_with_reason(f"{provider}: request rejected", exc))
    if isinstance(exc, sdk.APITimeoutError):
        return ProviderUnavailableError(f"{provider}: request timed out.")
    if isinstance(exc, sdk.APIConnectionError):
        return ProviderUnavailableError(f"{provider}: could not connect to the provider.")
    if isinstance(exc, sdk.APIStatusError):
        return ProviderUnavailableError(_with_reason(f"{provider}: upstream error", exc))
    return ProviderUnavailableError(f"{provider}: unexpected error ({type(exc).__name__}).")


def map_status_code(status: int | None, provider: str, body: Any = None) -> VeritasError:
    reason = provider_reason(body)
    suffix = f" (HTTP {status}{', ' + reason if reason else ''})."
    # Google answers an invalid key with HTTP 400 "API key not valid" (API_KEY_INVALID).
    key_problem = bool(reason and re.search(r"api[ _]?key", reason, re.IGNORECASE))
    if status in (401, 403) or (status == 400 and key_problem):
        return ProviderAuthenticationError(
            f"{provider}: API key rejected or lacks permission{suffix}"
        )
    if status == 429:
        return ProviderRateLimitError(f"{provider}: rate limit or quota exceeded{suffix}")
    if status in (400, 404, 422):
        return ProviderConfigurationError(f"{provider}: request rejected{suffix}")
    return ProviderUnavailableError(f"{provider}: upstream error{suffix}")
