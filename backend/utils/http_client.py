"""Shared httpx.AsyncClient instances for outbound HTTP.

Implements Lane 1 of the 3-lane async architecture (issue #6369):
- Connection pooling per service (4 clients)
- Bounded concurrency via asyncio.Semaphore
- Per-target circuit breakers for webhooks
- Latest-wins dropping for audio-byte-level calls

Lifecycle: clients are lazily created on first use and should be closed
at application shutdown via ``close_all_clients()``.
"""

import asyncio
import logging
import time
from collections import defaultdict

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Circuit breaker for webhook targets
# ---------------------------------------------------------------------------

_CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
_CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30  # seconds
_CIRCUIT_BREAKER_HALF_OPEN_MAX = 1  # probes allowed in half-open


class WebhookCircuitBreaker:
    """Per-target circuit breaker for outbound webhook HTTP calls.

    States:
      CLOSED  — normal operation, failures counted
      OPEN    — target is down, calls short-circuited
      HALF_OPEN — recovery probe allowed (single request)

    Thread-safe: uses only time.monotonic() and simple int/bool fields with
    no asyncio primitives.  Safe to call from multiple threads / event loops
    (e.g. asyncio.run() in sync FastAPI endpoints, executor threads).
    httpx.AsyncClient instances are likewise thread-safe (httpcore is
    thread-safe).  Per-loop semaphores are keyed by loop ID so they work
    correctly across different event loops.
    """

    __slots__ = ('_failures', '_last_failure_time', '_state', '_half_open_in_flight', '_url')

    def __init__(self, url: str):
        self._url = url
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = 'closed'
        self._half_open_in_flight = 0

    @property
    def state(self) -> str:
        if self._state == 'open':
            if time.monotonic() - self._last_failure_time >= _CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                self._state = 'half_open'
                self._half_open_in_flight = 0
        return self._state

    def allow_request(self) -> bool:
        s = self.state
        if s == 'closed':
            return True
        if s == 'half_open':
            if self._half_open_in_flight < _CIRCUIT_BREAKER_HALF_OPEN_MAX:
                self._half_open_in_flight += 1
                return True
            return False
        return False  # open

    def record_success(self):
        self._failures = 0
        self._state = 'closed'
        self._half_open_in_flight = 0

    def record_failure(self):
        self._failures += 1
        self._last_failure_time = time.monotonic()
        if self._failures >= _CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            self._state = 'open'
            logger.warning(f'Circuit breaker OPEN for webhook: {self._url[:80]}')


# Global registry of per-target circuit breakers
_webhook_circuit_breakers: dict[str, WebhookCircuitBreaker] = {}


def get_webhook_circuit_breaker(url: str) -> WebhookCircuitBreaker:
    """Get or create a circuit breaker for a webhook target URL.

    Keyed by the URL path (scheme + host + path, without query params) so that
    different webhook endpoints on the same host are isolated from each other.
    """
    try:
        # Strip query params but keep scheme + host + path
        key = url.split('?')[0].split('#')[0]
    except (IndexError, AttributeError):
        key = url
    if key not in _webhook_circuit_breakers:
        _webhook_circuit_breakers[key] = WebhookCircuitBreaker(key)
    return _webhook_circuit_breakers[key]


# ---------------------------------------------------------------------------
# Latest-wins tracking for audio byte webhook calls
# ---------------------------------------------------------------------------

_latest_wins_versions: dict[str, int] = defaultdict(int)


def latest_wins_start(uid: str) -> int:
    """Increment and return the current version for a uid's audio byte call."""
    _latest_wins_versions[uid] += 1
    return _latest_wins_versions[uid]


def latest_wins_check(uid: str, version: int) -> bool:
    """Return True if this version is still the latest for the uid."""
    return _latest_wins_versions.get(uid, 0) == version


# ---------------------------------------------------------------------------
# Semaphores for bounded concurrency per client type
# ---------------------------------------------------------------------------
# Semaphores are event-loop-bound in Python's asyncio. Since sync FastAPI
# endpoints use asyncio.run() which creates a new event loop each call,
# we key semaphores by event loop ID so each loop gets its own instance.
# The main FastAPI event loop (used by async endpoints) shares one set.

_semaphores: dict[tuple[int, str], asyncio.Semaphore] = {}
_SEMAPHORE_CACHE_MAX = 100  # Prune when cache exceeds this size


def _get_semaphore(name: str, limit: int) -> asyncio.Semaphore:
    """Get or create a semaphore for the current event loop.

    Keyed by (loop_id, name) so each event loop gets its own set. This is
    necessary because asyncio.run() in sync FastAPI endpoints creates a
    fresh event loop per call, and semaphores are loop-bound.

    The main FastAPI event loop (used by async endpoints) reuses the same
    loop_id for the lifetime of the process, so its semaphores are stable.
    Entries from short-lived asyncio.run() loops are pruned when the cache
    grows beyond _SEMAPHORE_CACHE_MAX to prevent unbounded growth.
    """
    try:
        loop = asyncio.get_running_loop()
        key = (id(loop), name)
    except RuntimeError:
        # No running loop — create unbound semaphore (will bind on first acquire)
        return asyncio.Semaphore(limit)
    if key not in _semaphores:
        # Prune stale entries from destroyed loops when cache grows large
        if len(_semaphores) > _SEMAPHORE_CACHE_MAX:
            _semaphores.clear()
        _semaphores[key] = asyncio.Semaphore(limit)
    return _semaphores[key]


def get_webhook_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('webhook', 64)


def get_maps_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('maps', 8)


def get_auth_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('auth', 20)


def get_stt_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('stt', 8)


# ---------------------------------------------------------------------------
# Shared httpx.AsyncClient instances
# ---------------------------------------------------------------------------

_webhook_client: httpx.AsyncClient | None = None
_maps_client: httpx.AsyncClient | None = None
_auth_client: httpx.AsyncClient | None = None
_stt_client: httpx.AsyncClient | None = None


def get_webhook_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for webhook delivery.

    Uses aggressive connect timeout (2s) and modest read timeout (15s)
    to match existing semantics while avoiding thread pool exhaustion.
    """
    global _webhook_client
    if _webhook_client is None:
        _webhook_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=2.0),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
        )
    return _webhook_client


def get_maps_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for Google Maps geocoding."""
    global _maps_client
    if _maps_client is None:
        _maps_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
    return _maps_client


def get_auth_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for OAuth/auth token exchanges."""
    global _auth_client
    if _auth_client is None:
        _auth_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=8),
        )
    return _auth_client


def get_stt_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for STT/ML services (long timeout)."""
    global _stt_client
    if _stt_client is None:
        _stt_client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=5.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
    return _stt_client


async def close_all_clients():
    """Close all shared HTTP clients. Call at app shutdown."""
    global _webhook_client, _maps_client, _auth_client, _stt_client
    for client in (_webhook_client, _maps_client, _auth_client, _stt_client):
        if client is not None:
            try:
                await client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")
    _webhook_client = None
    _maps_client = None
    _auth_client = None
    _stt_client = None
    # Reset semaphores (keyed by event loop)
    _semaphores.clear()
