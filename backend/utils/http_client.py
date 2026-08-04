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
import ipaddress
import logging
import socket
import time
from collections import defaultdict
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class UnsafeWebhookURLError(Exception):
    """Raised when a developer-configured webhook/callback URL resolves to a
    non-public address (private LAN, loopback, or the 169.254.169.254-style
    cloud metadata range) — blocks SSRF via app webhook_url / setup_completed_url."""


# RFC 6598 carrier-grade NAT shared address space (100.64.0.0/10). Python's
# ipaddress flags neither is_private nor is_reserved for this range, so without
# an explicit check a developer-configured webhook that resolves here would be
# wrongly accepted as "public" — it is not globally reachable and must be
# rejected for SSRF protection.
_CGNAT_NETWORK = ipaddress.ip_network('100.64.0.0/10')


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # covers the 169.254.169.254 cloud metadata address
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_public_http_url(url: str) -> str:
    """Reject webhook/callback URLs that don't point at a public host.

    Returns the first resolved IP address (as a string). Callers that go on
    to make the actual request MUST connect to that exact address (see
    `pin_to_resolved_ip` / `safe_request_target`) rather than letting the
    HTTP client re-resolve the hostname — otherwise a DNS record can be
    swapped between this check and the real connect (DNS rebinding), and
    this validation is worthless.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise UnsafeWebhookURLError(f'Unsupported URL scheme: {parsed.scheme!r}')

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeWebhookURLError('URL has no hostname')

    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise UnsafeWebhookURLError(f'Could not resolve host {hostname!r}: {e}')

    first_safe_ip: str | None = None
    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if _is_unsafe_ip(ip):
            raise UnsafeWebhookURLError(f'{hostname!r} resolves to non-public address {ip}')
        if first_safe_ip is None:
            first_safe_ip = str(ip)

    if first_safe_ip is None:
        # getaddrinfo() succeeded but returned zero records — treat like a resolution failure.
        raise UnsafeWebhookURLError(f'Could not resolve host {hostname!r}: no addresses returned')

    return first_safe_ip


def pin_to_resolved_ip(url: str, resolved_ip: str) -> tuple[str, dict]:
    """Rewrite `url` to connect directly to `resolved_ip` instead of trusting
    a second DNS lookup at connect time. Returns (pinned_url, extra) where
    `extra` carries the `Host` header and TLS `sni_hostname` extension the
    caller must merge into its request so the original hostname is still
    used for virtual-host routing and certificate verification — the
    connection targets the pinned IP, but looks and authenticates exactly
    like a normal request to the original hostname.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    netloc = f'[{resolved_ip}]' if ':' in resolved_ip else resolved_ip
    if parsed.port:
        netloc += f':{parsed.port}'
    pinned_url = parsed._replace(netloc=netloc).geturl()
    extra = {'headers': {'Host': hostname}, 'extensions': {'sni_hostname': hostname}}
    return pinned_url, extra


def safe_request_target(url: str) -> tuple[str, dict]:
    """Validate `url` (see `assert_public_http_url`) and return the
    (pinned_url, extra_kwargs) pair callers should actually request —
    closing the DNS-rebinding gap in one step. Raises UnsafeWebhookURLError
    for anything private/loopback/link-local/reserved/unresolvable."""
    resolved_ip = assert_public_http_url(url)
    return pin_to_resolved_ip(url, resolved_ip)


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


def get_desktop_gemini_semaphore() -> asyncio.Semaphore:
    """Bound concurrent desktop Gemini calls per event loop.

    The proxy accepts large multimodal bodies, so an upstream stall must not be
    allowed to turn every request into a new socket and an unbounded in-memory
    body. The client pool uses the same limit below.
    """
    return _get_semaphore('desktop_gemini', 32)


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


def get_desktop_gemini_client() -> httpx.AsyncClient:
    """Return the pooled client for non-streaming desktop Gemini requests.

    ``read`` is the upstream idle/first-byte bound. The proxy owns a separate
    absolute logical deadline so these per-phase limits cannot accumulate into
    another multi-minute request.
    """
    return _get_client(
        'desktop_gemini',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=70.0, write=15.0, pool=5.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
        ),
    )


def get_desktop_gemini_stream_client() -> httpx.AsyncClient:
    """Return the pooled client for streaming desktop Gemini requests.

    A 30-second read timeout is an idle-gap bound, not a total stream duration.
    Long healthy SSE responses remain valid while silent upstream sockets are
    released promptly.
    """
    return _get_client(
        'desktop_gemini_stream',
        lambda: httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=15.0, pool=5.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
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
