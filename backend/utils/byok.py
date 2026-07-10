"""Per-request BYOK (Bring Your Own Keys) key plumbing.

The desktop client sends user-provided API keys as headers on every request
(`X-BYOK-OpenAI`, `X-BYOK-Anthropic`, `X-BYOK-Gemini`, `X-BYOK-Deepgram`).
A FastAPI middleware stashes them in a per-request contextvar; the LLM/STT
clients can then read them without re-reading the request object.

Keys are NEVER persisted — only fingerprints (see `database.users.set_byok_active`).

Firestore BYOK state is the **source of truth**.  Per-request headers are
validated against enrolled fingerprints so that:
  - BYOK-active users MUST send keys that match their enrolled fingerprints.
  - Non-BYOK users' headers are silently ignored (Omi keys are used).
"""

import hashlib
import ipaddress
import logging
import socket
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from cachetools import TTLCache
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.websockets import WebSocket

logger = logging.getLogger('byok')

# ---------------------------------------------------------------------------
# In-memory TTL cache for Firestore BYOK state lookups.
#
# Without this, get_byok_state(uid) triggers a Firestore read 2-3 times per
# request (once in validate_byok_request, again in is_byok_active inside
# subscription code).  A short TTL (30 s) keeps reads fresh enough for key
# rotation detection while cutting redundant Firestore traffic.
# ---------------------------------------------------------------------------
_BYOK_STATE_CACHE_MAX = 1024
_BYOK_STATE_CACHE_TTL = 30  # seconds
_byok_state_cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=_BYOK_STATE_CACHE_MAX, ttl=_BYOK_STATE_CACHE_TTL)
_byok_state_cache_lock = threading.Lock()


def get_cached_byok_state(uid: str) -> Dict[str, Any]:
    """Return BYOK state for *uid*, hitting Firestore at most once per TTL window."""
    with _byok_state_cache_lock:
        cached = _byok_state_cache.get(uid)
    if cached is not None:
        return cached

    import database.users as users_db

    state = users_db.get_byok_state(uid)
    with _byok_state_cache_lock:
        _byok_state_cache[uid] = state
    return state


def invalidate_byok_state_cache(uid: str) -> None:
    """Call after activation/deactivation to bust the cache immediately."""
    with _byok_state_cache_lock:
        _byok_state_cache.pop(uid, None)


BYOK_HEADERS = {
    'openai': 'x-byok-openai',
    'anthropic': 'x-byok-anthropic',
    'gemini': 'x-byok-gemini',
    'deepgram': 'x-byok-deepgram',
    # User-hosted OpenAI-compatible provider (OpenRouter, Together, Groq, a local
    # server, ...). The value is the API key; the base URL and model name travel
    # alongside it in the companion config headers below (#6878).
    'custom': 'x-byok-custom',
}

# Non-secret config for the custom provider. Carried per-request (like the keys)
# and stashed in the same contextvar under reserved names so it never collides
# with a provider key and is never fingerprint-validated.
_CUSTOM_BASE_URL_FIELD = '__custom_base_url'
_CUSTOM_MODEL_FIELD = '__custom_model'
BYOK_CUSTOM_CONFIG_HEADERS = {
    _CUSTOM_BASE_URL_FIELD: 'x-byok-custom-base-url',
    _CUSTOM_MODEL_FIELD: 'x-byok-custom-model',
}

# Keys for the current request, if the client supplied them.
# Default is None (not {}) to avoid sharing a mutable object across contexts.
_byok_ctx: ContextVar[Optional[Dict[str, str]]] = ContextVar('byok_keys', default=None)
_byok_uid_ctx: ContextVar[Optional[str]] = ContextVar('byok_uid', default=None)


def get_byok_keys() -> Dict[str, str]:
    """The keys attached to the current request (may be empty)."""
    return _byok_ctx.get() or {}


def get_byok_key(provider: str) -> Optional[str]:
    keys = _byok_ctx.get()
    if keys is None:
        return None
    return keys.get(provider)


def get_byok_uid() -> Optional[str]:
    """Return the authenticated uid for the current request, when known."""
    return _byok_uid_ctx.get()


def set_byok_uid(uid: Optional[str]) -> None:
    """Attach the authenticated uid to the current request context."""
    _byok_uid_ctx.set(uid)


def has_byok_keys() -> bool:
    """True if the current request carries at least one BYOK header."""
    keys = _byok_ctx.get()
    if not keys:
        return False
    # Custom-provider config alone (base URL / model with no key) is not a usable
    # BYOK request, so don't let it flip quota bypass on its own.
    return any(not k.startswith('__') for k in keys)


def _is_blocked_ip(ip: "ipaddress._BaseAddress") -> bool:
    """True for any address the backend must never make an outbound call to."""
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified


# Cache of per-host SSRF *rejections* only. A custom base URL is validated on every
# get_llm call (get_byok_custom_provider), so caching avoids re-resolving an abusive
# or already-blocked host repeatedly. Successful validations are deliberately never
# cached: a cached success would let an attacker who controls the host's DNS resolve
# to a public IP, get it cached, then rebind the name to an internal address and have
# the next TTL window of requests skip re-resolution (DNS rebinding). Only rejection
# messages are stored; the short TTL bounds how long a rejection sticks after a DNS
# change. get_llm runs in a worker thread, so the per-call resolution is off the loop.
_DNS_VALIDATION_CACHE: TTLCache = TTLCache(maxsize=512, ttl=300)
_dns_validation_lock = threading.Lock()


def validate_custom_base_url(base_url: str) -> str:
    """Validate a user-supplied custom provider base URL and return it normalized.

    The backend makes outbound LLM calls to this URL with the user's key, so this
    is an SSRF guard: require HTTPS, reject literal internal/loopback/link-local/
    private addresses, and resolve a hostname so a public-looking name that points
    at a private/metadata IP is blocked too. Raises ValueError on anything that
    does not pass.

    Note: this validates at call time and does not pin the resolved IP through to
    the LLM client's connection, so a host that re-resolves to an internal address
    between this check and the actual request (active DNS rebinding) is not fully
    covered. Connect-time pinning would route the custom client through a dedicated
    transport and is a follow-up.
    """
    if not base_url or not isinstance(base_url, str):
        raise ValueError('custom base URL is required')
    url = base_url.strip()
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise ValueError('custom base URL must use https')
    host = parsed.hostname
    if not host:
        raise ValueError('custom base URL must include a host')
    lowered = host.lower()
    if lowered == 'localhost' or lowered.endswith('.localhost') or lowered.endswith('.local'):
        raise ValueError('custom base URL host is not allowed')

    try:
        literal_ip = ipaddress.ip_address(lowered)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        if _is_blocked_ip(literal_ip):
            raise ValueError('custom base URL host is not allowed')
        return url  # literal public IP, nothing to resolve

    # Hostname: resolve and reject if any resolved address is internal, so a
    # public-looking name pointing at a private/metadata IP cannot slip through.
    # Re-resolve on every successful call (successes are never cached) so a host
    # that has been rebound to an internal address since a prior check is still
    # caught; only rejections are cached.
    with _dns_validation_lock:
        cached = _DNS_VALIDATION_CACHE.get(lowered)
    if isinstance(cached, str):
        raise ValueError(cached)
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as e:
        # Any resolver failure degrades to a rejected URL rather than a 500: OSError covers
        # socket.gaierror and other DNS/socket errors, UnicodeError covers IDNA failures such
        # as an overlong hostname label. Transient failures are not cached.
        raise ValueError(f'custom base URL host did not resolve: {e}')
    for info in infos:
        addr = info[4][0]
        try:
            resolved = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_blocked_ip(resolved):
            msg = 'custom base URL resolves to a non-public address'
            with _dns_validation_lock:
                _DNS_VALIDATION_CACHE[lowered] = msg
            raise ValueError(msg)
    return url


def get_byok_custom_provider() -> Optional[Dict[str, str]]:
    """The fully configured custom OpenAI-compatible provider for this request, or
    None. Requires the key, base URL, and model to all be present, and the base
    URL to pass validation (an invalid URL yields None rather than raising, so a
    bad header degrades to the default provider instead of failing the request)."""
    keys = _byok_ctx.get()
    if not keys:
        return None
    api_key = keys.get('custom')
    base_url = keys.get(_CUSTOM_BASE_URL_FIELD)
    model = keys.get(_CUSTOM_MODEL_FIELD)
    if not (api_key and base_url and model):
        return None
    try:
        base_url = validate_custom_base_url(base_url)
    except ValueError as e:
        logger.warning('BYOK custom provider: rejecting base URL: %s', e)
        return None
    return {'api_key': api_key, 'base_url': base_url, 'model': model}


def set_byok_keys(keys: Dict[str, str]):
    """Used by the middleware; also useful from WS handlers that read headers manually."""
    _byok_ctx.set({k: v for k, v in keys.items() if v})


def extract_byok_from_websocket(websocket: WebSocket) -> Dict[str, str]:
    """Read BYOK headers from a WebSocket's initial upgrade request.

    BaseHTTPMiddleware only fires for HTTP scope, so WebSocket handlers must
    call this manually and then pass the result to ``set_byok_keys``.
    """
    keys: Dict[str, str] = {}
    for provider, header in BYOK_HEADERS.items():
        value = websocket.headers.get(header)
        if value:
            keys[provider] = value
    for field, header in BYOK_CUSTOM_CONFIG_HEADERS.items():
        value = websocket.headers.get(header)
        if value:
            keys[field] = value
    return keys


class BYOKMiddleware(BaseHTTPMiddleware):
    """Extract BYOK headers from each HTTP request into the contextvar.

    NOTE: BaseHTTPMiddleware does NOT fire for WebSocket connections
    (scope["type"] == "websocket"). WebSocket handlers must call
    ``extract_byok_from_websocket`` + ``set_byok_keys`` manually.
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        keys: Dict[str, str] = {}
        for provider, header in BYOK_HEADERS.items():
            value = request.headers.get(header)
            if value:
                keys[provider] = value
        for field, header in BYOK_CUSTOM_CONFIG_HEADERS.items():
            value = request.headers.get(header)
            if value:
                keys[field] = value
        token = _byok_ctx.set(keys)
        uid_token = _byok_uid_ctx.set(None)
        try:
            return await call_next(request)
        finally:
            _byok_ctx.reset(token)
            _byok_uid_ctx.reset(uid_token)


# ---------------------------------------------------------------------------
# Per-request fingerprint validation against Firestore enrollment
# ---------------------------------------------------------------------------


def _check_byok_validity(uid: str) -> Optional[str]:
    """Core validation: Firestore BYOK state is source of truth.

    Returns an error message string on failure, or ``None`` on success.

    Behaviour:
    - If NO BYOK headers on this request → returns None immediately without
      touching Firestore.  This is the fast path for mobile and non-BYOK users.
    - If user is NOT BYOK-active but sends headers → clears headers from the
      context (so they are never used) and returns None.
    - If user IS BYOK-active **and sends BYOK headers** → every header key's
      SHA-256 must match the enrolled fingerprint.  Mismatch → error string.
    """
    # Fast path: no BYOK headers on this request → nothing to validate.
    # Avoids hitting Firestore/cache for the vast majority of requests
    # (mobile, non-BYOK desktop).
    request_keys = _byok_ctx.get() or {}
    if not request_keys:
        return None

    import database.users as users_db

    state = get_cached_byok_state(uid)

    # Replicate is_byok_active logic on the already-fetched state to avoid a
    # second Firestore read.
    is_active = False
    if state.get('active'):
        last_seen = state.get('last_seen_at')
        if isinstance(last_seen, datetime):
            age = (datetime.now(timezone.utc) - last_seen).total_seconds()
            is_active = age <= users_db.BYOK_HEARTBEAT_TTL_SECONDS

    if not is_active:
        # Non-enrolled user — silently discard any BYOK headers so downstream
        # code always uses Omi's own keys.
        if _byok_ctx.get():
            _byok_ctx.set(None)
        return None

    # BYOK-active user with headers present — validate every enrolled
    # provider fingerprint.
    stored_fingerprints = state.get('fingerprints', {})

    for provider, stored_fp in stored_fingerprints.items():
        raw_key = request_keys.get(provider)
        if not raw_key:
            return f"BYOK key header missing for enrolled provider: {provider}"
        request_fp = hashlib.sha256(raw_key.encode()).hexdigest()
        if request_fp != stored_fp:
            return f"BYOK key fingerprint mismatch for provider: {provider}"

    # Honor the custom provider only when it is actually enrolled. Otherwise drop
    # its key + config so an un-enrolled `x-byok-custom` header can never route a
    # user's traffic to an unvalidated endpoint.
    if 'custom' not in stored_fingerprints:
        _custom_fields = ('custom', _CUSTOM_BASE_URL_FIELD, _CUSTOM_MODEL_FIELD)
        if any(f in request_keys for f in _custom_fields):
            _byok_ctx.set({k: v for k, v in request_keys.items() if k not in _custom_fields})

    return None


def validate_byok_request(uid: str) -> None:
    """Validate BYOK keys for HTTP endpoints (chat, etc.).

    Raises ``HTTPException(403)`` when the user is BYOK-active but the
    request headers are missing or don't match enrolled fingerprints.
    """
    error = _check_byok_validity(uid)
    if error:
        logger.warning('BYOK validation failed uid=%s: %s', uid, error)
        raise HTTPException(status_code=403, detail=error)
    set_byok_uid(uid)


def validate_byok_websocket(uid: str) -> Optional[str]:
    """Validate BYOK keys for WebSocket endpoints (listen, etc.).

    Returns an error message string on failure, or ``None`` on success.
    The caller is responsible for closing the WebSocket with an appropriate
    error when a non-None value is returned.
    """
    error = _check_byok_validity(uid)
    if error:
        logger.warning('BYOK WS validation failed uid=%s: %s', uid, error)
    else:
        set_byok_uid(uid)
    return error
