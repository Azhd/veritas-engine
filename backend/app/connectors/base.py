"""Base HTTP connector for public primary-source APIs.

Features:
    * strict per-request timeout (default 8s; bulk dataset downloads may opt into a longer one);
    * automatic retries with exponential backoff for transient failures
      (timeouts, connection errors, HTTP 429 and 5xx), honoring ``Retry-After``;
    * in-memory TTL + LRU cache so repeated checks do not hammer public servers;
    * optional configuration gate (``disabled_reason``) for sources needing credentials.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import httpx

from app.core.errors import ConnectorHTTPError, ConnectorUnavailableError
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
USER_AGENT = (
    "VeritasEngine/0.1 (+https://github.com/Azhd/veritas-engine; open-source fact-checking)"
)

ResponseKind = Literal["json", "text"]


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
    kwargs.setdefault("follow_redirects", True)
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

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            return
        self._data[key] = (self._clock() + ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class BaseGovConnector(ABC):
    """Common resilient HTTP layer shared by every primary-source connector."""

    #: Stable identifier, e.g. ``"br.camara"``.
    source_id: ClassVar[str]
    country: ClassVar[Country]
    publisher: ClassVar[str]
    base_url: ClassVar[str]
    #: Knowledge areas this source can substantiate (used by the orchestrator to select sources).
    domains: ClassVar[frozenset[Domain]] = frozenset()

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

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> BaseGovConnector:
        """Build the connector from app settings; override to inject credentials.

        ``extras`` carries shared resources built once by the registry (e.g. the PISTE OAuth
        client used by both Légifrance and Judilibre).
        """
        return cls(client, **common)

    async def warm_up(self) -> None:  # noqa: B027 - optional hook
        """Preload slow resources (bulk datasets) in the background at startup."""

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @property
    def disabled_reason(self) -> str | None:
        """Why the connector cannot run (e.g. missing credential); ``None`` when usable."""
        return None

    @property
    def enabled(self) -> bool:
        return self.disabled_reason is None

    @abstractmethod
    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        """Return normalized evidence relevant to ``query`` (may be empty)."""

    def _evidence(self, **fields: Any) -> Evidence:
        fields.setdefault("connector", self.source_id)
        fields.setdefault("country", self.country)
        fields.setdefault("publisher", self.publisher)
        return Evidence(**fields)

    # ------------------------------------------------------------------ HTTP core
    async def _auth_headers(self) -> dict[str, str]:
        """Hook for connectors that need per-request authentication headers."""
        return {}

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _cache_key(
        method: str, url: str, params: Mapping[str, Any] | None, body: Any = None
    ) -> str:
        key = url if method == "GET" else f"{method} {url}"
        if params:
            items = sorted((str(k), str(v)) for k, v in params.items() if v is not None)
            key += "?" + "&".join(f"{k}={v}" for k, v in items)
        if body is not None:
            key += f" body={body!r}"
        return key

    def _backoff(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.strip().isdigit():
                return min(float(retry_after), self.backoff_max_seconds)
        return min(self.backoff_base_seconds * (2**attempt), self.backoff_max_seconds)

    async def _request(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        method: str = "GET",
        json_body: Any = None,
        form: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        kind: ResponseKind = "json",
        request_timeout: float | None = None,
        use_cache: bool = True,
        cache_ttl: float | None = None,
    ) -> Any:
        url = self._url(path)
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        key = self._cache_key(method, url, clean_params, json_body if json_body else form)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        request_headers = {"Accept": "application/json" if kind == "json" else "*/*"}
        request_headers.update(headers or {})
        last_problem = "unknown error"
        for attempt in range(self.max_retries + 1):
            response: httpx.Response | None = None
            try:
                request_headers.update(await self._auth_headers())
                response = await self._client.request(
                    method,
                    url,
                    params=clean_params,
                    json=json_body,
                    data=form,
                    timeout=request_timeout or self.timeout_seconds,
                    headers=request_headers,
                )
            except httpx.TimeoutException:
                last_problem = "timeout"
            except httpx.TransportError as exc:
                last_problem = f"transport error ({type(exc).__name__})"
            else:
                if response.status_code < 400:
                    payload = self._decode(response, kind)
                    if use_cache:
                        self.cache.set(key, payload, cache_ttl)
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

    def _decode(self, response: httpx.Response, kind: ResponseKind) -> Any:
        if kind == "text":
            return response.text
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorHTTPError(
                f"{self.source_id}: invalid JSON response", response.status_code
            ) from exc

    async def _get_json(
        self, path: str, params: Mapping[str, Any] | None = None, *, use_cache: bool = True
    ) -> Any:
        return await self._request(path, params, use_cache=use_cache)


def truncate(text: str | None, limit: int = 600) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
