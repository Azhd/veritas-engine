"""Domain exceptions and their HTTP mapping.

Error messages must never contain secrets (API keys). Provider adapters are responsible for
translating SDK exceptions into these types with sanitized messages.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class VeritasError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ---------------- BYOK / LLM providers ----------------
class ProviderConfigurationError(VeritasError):
    """The request did not carry a usable provider configuration (bad header, missing key...)."""

    status_code = 400
    code = "provider_configuration_error"


class ProviderAuthenticationError(VeritasError):
    status_code = 401
    code = "provider_authentication_error"


class ProviderRateLimitError(VeritasError):
    status_code = 429
    code = "provider_rate_limited"


class ProviderUnavailableError(VeritasError):
    status_code = 502
    code = "provider_unavailable"


class ProviderOutputError(VeritasError):
    """The LLM answered, but the output could not be parsed/validated."""

    status_code = 502
    code = "provider_invalid_output"


# ---------------- Government connectors ----------------
class ConnectorError(VeritasError):
    status_code = 502
    code = "connector_error"


class ConnectorHTTPError(ConnectorError):
    """Non-retryable HTTP error returned by an upstream public API (e.g. 400/404)."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class ConnectorUnavailableError(ConnectorError):
    """Upstream kept failing after all retries (timeouts, 5xx, 429)."""

    status_code = 503
    code = "connector_unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(VeritasError)
    async def _veritas_error_handler(_: Request, exc: VeritasError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
