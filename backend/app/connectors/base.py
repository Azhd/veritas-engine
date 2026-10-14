"""Base HTTP connector for public government APIs.

Features:
    * strict per-request timeout (default 8s);
    * automatic retries with exponential backoff for transient failures
      (timeouts, connection errors, HTTP 429 and 5xx), honoring ``Retry-After``;
    * in-memory TTL + LRU cache so repeated checks do not hammer public servers.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar

import httpx

from app.core.errors import ConnectorHTTPError, ConnectorUnavailableError
from app.schemas.evidence import Country, Evidence, EvidenceQuery

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
USER_AGENT = "VeritasEngine/0.1 (+https://github.com/veritas-engine; open-source fact-checking)"


def build_http_client(**kwargs: Any) -> httpx.AsyncClient:
    """HTTP client for public APIs, verifying TLS against the OS trust store when possible.

    Some government servers (e.g. IBGE) do not send their full certificate chain; the OS store
    (via ``truststore``) resolves the missing intermediates where the bundled ``certifi`` cannot.
    """
    try:
        import truststore

        kwargs.setdefault("verify", truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    except ImportError:  # pragma: no cover - optional dependency
        logger.debug("truststore not installed; using certifi CA bundle")
    kwargs.setdefault("headers", {"User-Agent": USER_AGENT})
    return httpx.AsyncClient(**kwargs)


class TTLCache:
    """Small LRU cache with per-entry expiry. Safe for single event-loop use."""

    def __init__(
        self,
        ttl_seconds: float = 900.0,
        max_entries: int = 1024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if self.ttl_seconds <= 0:
            return
        self._data[key] = (self._clock() + self.ttl_seconds, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class BaseGovConnector(ABC):
    """Common resilient HTTP layer for government data connectors."""

    #: Stable identifier, e.g. ``"br.camara"``.
    source_id: ClassVar[str]
    country: ClassVar[Country]
    publisher: ClassVar[str]
    base_url: ClassVar[str]

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        timeout_seconds: float = 8.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        backoff_max_seconds: float = 8.0,
        cache: TTLCache | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._owns_client = client is None
        self._client = client or build_http_client()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self.cache = cache if cache is not None else TTLCache()
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @abstractmethod
    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        """Return normalized evidence relevant to ``query`` (may be empty)."""

    # ------------------------------------------------------------------ HTTP core
    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _cache_key(url: str, params: Mapping[str, Any] | None) -> str:
        if not params:
            return url
        items = sorted((str(k), str(v)) for k, v in params.items() if v is not None)
        return url + "?" + "&".join(f"{k}={v}" for k, v in items)

    def _backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.strip().isdigit():
                return min(float(retry_after), self.backoff_max_seconds)
        return min(self.backoff_base_seconds * (2**attempt), self.backoff_max_seconds)

    async def _get_json(
        self, path: str, params: Mapping[str, Any] | None = None, *, use_cache: bool = True
    ) -> Any:
        url = self._url(path)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        key = self._cache_key(url, clean_params)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        last_problem = "unknown error"
        for attempt in range(self.max_retries + 1):
            response: httpx.Response | None = None
            try:
                response = await self._client.get(
                    url,
                    params=clean_params,
                    timeout=self.timeout_seconds,
                    headers={"Accept": "application/json"},
                )
            except httpx.TimeoutException:
                last_problem = "timeout"
            except httpx.TransportError as exc:
                last_problem = f"transport error ({type(exc).__name__})"
            else:
                if response.status_code < 400:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise ConnectorHTTPError(
                            f"{self.source_id}: invalid JSON response", response.status_code
                        ) from exc
                    if use_cache:
                        self.cache.set(key, payload)
                    return payload
                if response.status_code not in RETRYABLE_STATUS:
                    raise ConnectorHTTPError(
                        f"{self.source_id}: HTTP {response.status_code} for {url}",
                        response.status_code,
                    )
                last_problem = f"HTTP {response.status_code}"

            if attempt < self.max_retries:
                delay = self._backoff(attempt, response)
                logger.warning(
                    "%s: %s on %s (attempt %d/%d), retrying in %.2fs",
                    self.source_id,
                    last_problem,
                    url,
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                )
                await self._sleep(delay)

        raise ConnectorUnavailableError(
            f"{self.source_id}: unavailable after {self.max_retries + 1} attempts ({last_problem})"
        )


def truncate(text: str | None, limit: int = 600) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
