"""PISTE (French government API gateway) OAuth2 client-credentials helper.

Shared by Légifrance (DILA) and Judilibre (Cour de cassation). Tokens are cached in memory
until shortly before expiry and refreshed under a lock so concurrent checks reuse one token.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import httpx
from pydantic import SecretStr

from app.core.errors import ConnectorHTTPError, ConnectorUnavailableError

PISTE_OAUTH_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
PISTE_SANDBOX_OAUTH_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
PISTE_API_URL = "https://api.piste.gouv.fr"
PISTE_SANDBOX_API_URL = "https://sandbox-api.piste.gouv.fr"
_EXPIRY_MARGIN_SECONDS = 60


class PisteAuth:
    def __init__(
        self,
        client: httpx.AsyncClient,
        client_id: SecretStr | None,
        client_secret: SecretStr | None,
        *,
        sandbox: bool = False,
        timeout_seconds: float = 8.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._client_id = client_id
        self._client_secret = client_secret
        self.sandbox = sandbox
        self._timeout = timeout_seconds
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(
            self._client_id
            and self._client_secret
            and self._client_id.get_secret_value()
            and self._client_secret.get_secret_value()
        )

    @property
    def api_url(self) -> str:
        return PISTE_SANDBOX_API_URL if self.sandbox else PISTE_API_URL

    async def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self.token()}"}

    async def token(self) -> str:
        if self._token and self._clock() < self._expires_at:
            return self._token
        async with self._lock:
            if self._token and self._clock() < self._expires_at:
                return self._token
            await self._refresh()
            assert self._token is not None
            return self._token

    async def _refresh(self) -> None:
        if not self.configured:
            raise ConnectorHTTPError("piste: credentials not configured", 401)
        assert self._client_id and self._client_secret
        try:
            response = await self._client.post(
                PISTE_SANDBOX_OAUTH_URL if self.sandbox else PISTE_OAUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id.get_secret_value(),
                    "client_secret": self._client_secret.get_secret_value(),
                    "scope": "openid",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise ConnectorUnavailableError(
                f"piste: token endpoint unreachable ({type(exc).__name__})"
            ) from None
        if response.status_code >= 400:
            # Never echo the response body: it may contain the submitted credentials.
            raise ConnectorHTTPError(
                f"piste: token request rejected (HTTP {response.status_code})",
                response.status_code,
            )
        payload = response.json()
        self._token = payload["access_token"]
        expires_in = float(payload.get("expires_in", 3600))
        self._expires_at = self._clock() + max(expires_in - _EXPIRY_MARGIN_SECONDS, 0)
