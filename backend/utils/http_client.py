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
from collections.abc import Callable

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
    thread-safe), but their pooled connections are not portable across event
    loops, so both they and the semaphores are keyed by loop ID.
    """

    __slots__ = ('_failures', '_last_failure_time', '_last_access_time', '_state', '_half_open_in_flight', '_url')

    def __init__(self, url: str):
        self._url = url
        self._failures = 0
        self._last_failure_time = 0.0
        self._last_access_time = time.monotonic()
        self._state = 'closed'
        self._half_open_in_flight = 0

    @property
    def state(self) -> str:
        if self._state == 'open':
            if time.monotonic() - self._last_failure_time >= _CIRCUIT_BREAKER_RECOVERY_TIMEOUT:
                self._state = 'half_open'
                self._half_open_in_flight = 0
        return self._state

    @property
    def last_access_time(self) -> float:
        return self._last_access_time

    def allow_request(self) -> bool:
        self._last_access_time = time.monotonic()
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
_CIRCUIT_BREAKER_MAX_ENTRIES = 500
_CIRCUIT_BREAKER_IDLE_TTL = 3600  # seconds — evict entries idle for 1 hour


def get_webhook_circuit_breaker(url: str) -> WebhookCircuitBreaker:
    """Get or create a circuit breaker for a webhook target URL.

    Keyed by the URL path (scheme + host + path, without query params) so that
    different webhook endpoints on the same host are isolated from each other.
    Evicts stale entries when the registry grows beyond _CIRCUIT_BREAKER_MAX_ENTRIES.
    """
    try:
        # Strip query params but keep scheme + host + path
        key = url.split('?')[0].split('#')[0]
    except (IndexError, AttributeError):
        key = url
    if key not in _webhook_circuit_breakers:
        if len(_webhook_circuit_breakers) > _CIRCUIT_BREAKER_MAX_ENTRIES:
            _evict_stale_circuit_breakers()
        _webhook_circuit_breakers[key] = WebhookCircuitBreaker(key)
    return _webhook_circuit_breakers[key]


def _evict_stale_circuit_breakers():
    """Remove circuit breaker entries not accessed for longer than _CIRCUIT_BREAKER_IDLE_TTL.

    Uses _last_access_time (updated on every allow_request call) so actively
    used breakers are never evicted, regardless of failure state.
    """
    now = time.monotonic()
    stale_keys = [
        k for k, cb in _webhook_circuit_breakers.items() if now - cb.last_access_time > _CIRCUIT_BREAKER_IDLE_TTL
    ]
    for k in stale_keys:
        del _webhook_circuit_breakers[k]
    if stale_keys:
        logger.info(f'Evicted {len(stale_keys)} stale circuit breakers, {len(_webhook_circuit_breakers)} remaining')


# ---------------------------------------------------------------------------
# Latest-wins tracking for audio byte webhook calls
# ---------------------------------------------------------------------------

_latest_wins_versions: dict[str, int] = defaultdict(int)
_latest_wins_last_seen: dict[str, float] = {}
_LATEST_WINS_MAX_ENTRIES = 10000
_LATEST_WINS_IDLE_TTL = 600  # seconds — evict UIDs idle for 10 minutes


def latest_wins_start(uid: str) -> int:
    """Increment and return the current version for a uid's audio byte call."""
    _latest_wins_versions[uid] += 1
    _latest_wins_last_seen[uid] = time.monotonic()
    if len(_latest_wins_versions) > _LATEST_WINS_MAX_ENTRIES:
        _evict_stale_latest_wins()
    return _latest_wins_versions[uid]


def latest_wins_check(uid: str, version: int) -> bool:
    """Return True if this version is still the latest for the uid."""
    return _latest_wins_versions.get(uid, 0) == version


def _evict_stale_latest_wins():
    """Remove latest-wins entries for UIDs not seen recently."""
    now = time.monotonic()
    stale_uids = [uid for uid, last_seen in _latest_wins_last_seen.items() if now - last_seen > _LATEST_WINS_IDLE_TTL]
    for uid in stale_uids:
        _latest_wins_versions.pop(uid, None)
        _latest_wins_last_seen.pop(uid, None)
    if stale_uids:
        logger.info(f'Evicted {len(stale_uids)} stale latest-wins entries, {len(_latest_wins_versions)} remaining')


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
            _evict_foreign_loop_semaphores(id(loop))
        _semaphores[key] = asyncio.Semaphore(limit)
    return _semaphores[key]


def _evict_foreign_loop_semaphores(live_loop_id: int) -> None:
    """Drop semaphores belonging to loops other than the one running now.

    Mirrors _evict_stale_circuit_breakers / _evict_stale_latest_wins: remove only what is
    stale. A blanket clear() also dropped the running loop's own entry, so the next caller
    got a fresh Semaphore while in-flight tasks still held permits on the old one — briefly
    allowing twice the concurrency the limit exists to cap.
    """
    for key in [k for k in _semaphores if k[0] != live_loop_id]:
        del _semaphores[key]


def get_webhook_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('webhook', 64)


def get_maps_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('maps', 8)


def get_auth_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('auth', 20)


def get_stt_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('stt', 8)


def get_tts_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('tts', 32)


def get_llm_gateway_semaphore() -> asyncio.Semaphore:
    return _get_semaphore('llm_gateway', 24)


# ---------------------------------------------------------------------------
# Shared httpx.AsyncClient instances
# ---------------------------------------------------------------------------

_clients: dict[int, tuple[asyncio.AbstractEventLoop, dict[str, httpx.AsyncClient]]] = {}
_loopless_clients: dict[str, httpx.AsyncClient] = {}


def _get_client(name: str, factory: Callable[[], httpx.AsyncClient]) -> httpx.AsyncClient:
    """Get or create a shared client owned by the current event loop.

    Clients are per-loop for the same reason as `_get_semaphore`: a pooled
    keep-alive connection belongs to the event loop that opened it. Sync
    FastAPI endpoints run `asyncio.run()`, which closes its loop on return, so
    a process-wide client ends up holding connections whose loop is gone. The
    next request on a live loop makes the pool discard one, and closing it
    calls `write_eof()` on a freed uvloop handle — `RuntimeError: unable to
    perform operation on <TCPTransport closed=True ...>; the handler is
    closed`, which httpcore re-raises at the caller. In prod that surfaced as
    intermittent HTTP 500s on `/v1/apps/enable` and dropped app-integration
    webhook deliveries (~270/day).

    A finished loop's entry is dropped when the next loop appears — its
    clients cannot be closed (that is the same dead-handle error) and its
    sockets went down with the loop. Each entry keeps the loop itself, both to
    recognise that moment and so no two live entries can share an id.

    The main FastAPI event loop keeps one stable entry, so async callers — the
    hot paths — reuse their pool exactly as before.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop: configuration inspection, not requests.
        by_name = _loopless_clients
    else:
        entry = _clients.get(id(loop))
        if entry is None or entry[0] is not loop:
            for cached_id, (cached_loop, _) in list(_clients.items()):
                if cached_loop.is_closed():
                    del _clients[cached_id]
            entry = (loop, {})
            _clients[id(loop)] = entry
        by_name = entry[1]
    client = by_name.get(name)
    if client is None:
        client = factory()
        by_name[name] = client
    return client


def get_webhook_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for webhook delivery.

    Uses aggressive connect timeout (2s) and 30s read timeout to match
    the previous per-call timeout=30 that partner webhooks relied on.
    """
    return _get_client(
        'webhook',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=2.0),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=16),
        ),
    )


def get_maps_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for Google Maps geocoding."""
    return _get_client(
        'maps',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        ),
    )


def get_auth_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for OAuth/auth token exchanges.

    Keep-alive is disabled (`max_keepalive_connections=0`) for the same reason
    as `get_tts_client()`: in Cloud Run we observed stale keep-alive sockets
    being reused after the remote (Google/Apple/Firebase token endpoints) or an
    intermediate NAT silently dropped them, raising asyncio's "handler is
    closed" RuntimeError mid-request. That surfaced as intermittent HTTP 500s
    on `/v1/auth/callback/{google,apple}` and `/v1/auth/token`, breaking both
    Sign in with Google and Sign in with Apple (both providers share this
    client). Auth token-exchange volume is low, so paying a TLS handshake per
    request is a fine trade for eliminating the stale-socket failures.
    """
    return _get_client(
        'auth',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=2.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=0),
        ),
    )


def get_stt_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for STT/ML services (long timeout)."""
    return _get_client(
        'stt',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=5.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        ),
    )


def get_tts_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for TTS streaming (ElevenLabs).

    Keep-alive is disabled (`max_keepalive_connections=0`) because in Cloud
    Run we observed stale keep-alive sockets being reused after the remote
    or an intermediate NAT silently dropped them, raising asyncio's
    "handler is closed" error and returning 502 to the client. TTS
    volume is low enough that paying a TLS handshake per request is fine,
    and the correctness win is worth it.
    """
    return _get_client(
        'tts',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=0),
        ),
    )


def get_web_fetch_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client for user-initiated URL fetches.

    Isolated from the webhook pool so slow/stalled external pages don't
    compete with partner webhook delivery slots.
    """
    return _get_client(
        'web_fetch',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=5.0),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=4),
        ),
    )


def get_llm_gateway_client() -> httpx.AsyncClient:
    """Return the shared async client for the internal LLM gateway."""
    return _get_client(
        'llm_gateway',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=3.0),
            limits=httpx.Limits(max_connections=24, max_keepalive_connections=12),
        ),
    )


async def close_all_clients():
    """Close all shared HTTP clients. Call at app shutdown.

    Only this loop's clients can be closed: another loop's connections are
    already gone with it, and awaiting aclose() on them raises the dead-handle
    RuntimeError described in `_get_client`.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    _, own_clients = _clients.pop(id(loop), (None, {})) if loop is not None else (None, {})
    for client in own_clients.values():
        try:
            await client.aclose()
        except Exception as e:
            logger.warning(f"Error closing HTTP client: {e}")
    _clients.clear()
    _loopless_clients.clear()
    # Reset stateful registries
    _semaphores.clear()
    _webhook_circuit_breakers.clear()
    _latest_wins_versions.clear()
    _latest_wins_last_seen.clear()
