"""Translate SDK exceptions (anthropic / openai / groq share the same hierarchy) into domain errors.

Messages are intentionally generic: SDK error bodies may echo request data, so they are never
forwarded verbatim to API clients.
"""

from __future__ import annotations

from types import ModuleType

from app.core.errors import (
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    VeritasError,
)


def map_openai_style_error(exc: Exception, sdk: ModuleType, provider: str) -> VeritasError:
    if isinstance(exc, sdk.AuthenticationError | sdk.PermissionDeniedError):
        return ProviderAuthenticationError(f"{provider}: API key rejected or lacks permission.")
    if isinstance(exc, sdk.RateLimitError):
        return ProviderRateLimitError(f"{provider}: rate limit or quota exceeded.")
    if isinstance(exc, sdk.NotFoundError):
        return ProviderConfigurationError(f"{provider}: model or endpoint not found.")
    if isinstance(exc, sdk.BadRequestError):
        return ProviderConfigurationError(f"{provider}: request rejected (bad request).")
    if isinstance(exc, sdk.APITimeoutError):
        return ProviderUnavailableError(f"{provider}: request timed out.")
    if isinstance(exc, sdk.APIConnectionError):
        return ProviderUnavailableError(f"{provider}: could not connect to the provider.")
    if isinstance(exc, sdk.APIStatusError):
        return ProviderUnavailableError(f"{provider}: upstream error (HTTP {exc.status_code}).")
    return ProviderUnavailableError(f"{provider}: unexpected error ({type(exc).__name__}).")


def map_status_code(status: int | None, provider: str) -> VeritasError:
    if status in (401, 403):
        return ProviderAuthenticationError(f"{provider}: API key rejected or lacks permission.")
    if status == 429:
        return ProviderRateLimitError(f"{provider}: rate limit or quota exceeded.")
    if status in (400, 404, 422):
        return ProviderConfigurationError(f"{provider}: request rejected (HTTP {status}).")
    return ProviderUnavailableError(f"{provider}: upstream error (HTTP {status}).")
