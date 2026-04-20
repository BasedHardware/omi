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
import logging
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

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
_byok_state_cache: TTLCache = TTLCache(maxsize=_BYOK_STATE_CACHE_MAX, ttl=_BYOK_STATE_CACHE_TTL)
_byok_state_cache_lock = threading.Lock()


def get_cached_byok_state(uid: str) -> dict:
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
}

# Keys for the current request, if the client supplied them.
# Default is None (not {}) to avoid sharing a mutable object across contexts.
_byok_ctx: ContextVar[Optional[Dict[str, str]]] = ContextVar('byok_keys', default=None)


def get_byok_keys() -> Dict[str, str]:
    """The keys attached to the current request (may be empty)."""
    return _byok_ctx.get() or {}


def get_byok_key(provider: str) -> Optional[str]:
    keys = _byok_ctx.get()
    if keys is None:
        return None
    return keys.get(provider)


def has_byok_keys() -> bool:
    """True if the current request carries at least one BYOK header."""
    keys = _byok_ctx.get()
    return bool(keys)


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
    return keys


class BYOKMiddleware(BaseHTTPMiddleware):
    """Extract BYOK headers from each HTTP request into the contextvar.

    NOTE: BaseHTTPMiddleware does NOT fire for WebSocket connections
    (scope["type"] == "websocket"). WebSocket handlers must call
    ``extract_byok_from_websocket`` + ``set_byok_keys`` manually.
    """

    async def dispatch(self, request: Request, call_next):
        keys: Dict[str, str] = {}
        for provider, header in BYOK_HEADERS.items():
            value = request.headers.get(header)
            if value:
                keys[provider] = value
        token = _byok_ctx.set(keys)
        try:
            return await call_next(request)
        finally:
            _byok_ctx.reset(token)


# ---------------------------------------------------------------------------
# Per-request fingerprint validation against Firestore enrollment
# ---------------------------------------------------------------------------


def _check_byok_validity(uid: str) -> Optional[str]:
    """Core validation: Firestore BYOK state is source of truth.

    Returns an error message string on failure, or ``None`` on success.

    Behaviour:
    - If user is NOT BYOK-active → clears any BYOK headers from the context
      (so they are never used) and returns None.
    - If user IS BYOK-active → every enrolled provider fingerprint must be
      matched by a header whose SHA-256 equals the stored fingerprint.
      Missing or mismatched headers → returns an error string.
    """
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

    # BYOK-active: validate every enrolled provider.
    stored_fingerprints = state.get('fingerprints', {})
    request_keys = _byok_ctx.get() or {}

    for provider, stored_fp in stored_fingerprints.items():
        raw_key = request_keys.get(provider)
        if not raw_key:
            return f"BYOK active but missing key header for provider: {provider}"
        request_fp = hashlib.sha256(raw_key.encode()).hexdigest()
        if request_fp != stored_fp:
            return f"BYOK key fingerprint mismatch for provider: {provider}"

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


def validate_byok_websocket(uid: str) -> Optional[str]:
    """Validate BYOK keys for WebSocket endpoints (listen, etc.).

    Returns an error message string on failure, or ``None`` on success.
    The caller is responsible for closing the WebSocket with an appropriate
    error when a non-None value is returned.
    """
    error = _check_byok_validity(uid)
    if error:
        logger.warning('BYOK WS validation failed uid=%s: %s', uid, error)
    return error
