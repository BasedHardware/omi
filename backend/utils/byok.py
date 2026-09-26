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
import hmac
import logging
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from cachetools import TTLCache
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket
from utils.executors import critical_executor, run_blocking

logger = logging.getLogger('byok')

_BYOK_PEPPER = os.getenv('BYOK_FINGERPRINT_PEPPER', '')
_warned_no_pepper = False


def peppered_fingerprint(client_fingerprint: str) -> str:
    """Wrap a client-computed SHA-256 key fingerprint with a server-side HMAC
    pepper before it's persisted or compared.

    The client only ever sends/knows plain SHA-256(raw_key) — that's a
    deliberate privacy property (the server never sees raw BYOK keys at
    enrollment). But a plain, unsalted SHA-256 of a well-known-prefix API key
    (sk-, sk-ant-, AIza, ...) is rainbow-table attackable if the stored
    fingerprint ever leaks (e.g. a Firestore export). Mixing in a
    server-only secret closes that without changing the client protocol at
    all — clients still send the same plain fingerprint/raw key they always
    did; only what Omi's server persists changes.

    Falls back to the identity function (legacy behavior, no pepper) when
    BYOK_FINGERPRINT_PEPPER isn't configured, so this stays a strict
    improvement rather than a required migration.
    """
    if not _BYOK_PEPPER:
        global _warned_no_pepper
        if not _warned_no_pepper:
            logger.warning('BYOK_FINGERPRINT_PEPPER not set — BYOK fingerprints are stored unsalted')
            _warned_no_pepper = True
        return client_fingerprint
    return hmac.new(_BYOK_PEPPER.encode(), client_fingerprint.encode(), hashlib.sha256).hexdigest()


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
    'openrouter': 'x-byok-openrouter',
    'deepgram': 'x-byok-deepgram',
}

# Keys for the current request, if the client supplied them.
# Default is None (not {}) to avoid sharing a mutable object across contexts.
_byok_ctx: ContextVar[Optional[Dict[str, str]]] = ContextVar('byok_keys', default=None)
_byok_uid_ctx: ContextVar[Optional[str]] = ContextVar('byok_uid', default=None)
_byok_validated_ctx: ContextVar[bool] = ContextVar('byok_validated', default=False)
_BYOK_RECOVERY_PATHS = frozenset(
    {
        '/v1/payments/available-plans',
        '/v1/payments/overage-info',
        '/v1/users/me/byok-active',
        '/v1/users/me/subscription',
    }
)


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
    return bool(keys)


def has_validated_byok_keys() -> bool:
    """True when the current request's BYOK headers passed enrollment validation."""
    return _byok_validated_ctx.get() and bool(_byok_ctx.get())


def set_byok_keys(keys: Dict[str, str]):
    """Used by the middleware; also useful from WS handlers that read headers manually."""
    _byok_ctx.set({k: v for k, v in keys.items() if v})
    _byok_validated_ctx.set(False)


def set_validated_byok_keys(keys: Dict[str, str], uid: str) -> None:
    """Install already-validated BYOK keys in the current request context."""
    _byok_ctx.set({k: v for k, v in keys.items() if v})
    _byok_validated_ctx.set(True)
    set_byok_uid(uid)


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

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        keys: Dict[str, str] = {}
        for provider, header in BYOK_HEADERS.items():
            value = request.headers.get(header)
            if value:
                keys[provider] = value
        token = _byok_ctx.set(keys)
        uid_token = _byok_uid_ctx.set(None)
        validated_token = _byok_validated_ctx.set(False)
        try:
            if keys:
                authorization = request.headers.get('authorization', '')
                parts = authorization.split(' ', 1)
                if len(parts) == 2 and parts[0].lower() == 'bearer' and parts[1]:
                    try:
                        from utils.other.endpoints import verify_token

                        uid = await run_blocking(critical_executor, verify_token, parts[1])
                        validated_keys, error = await run_blocking(critical_executor, _validated_byok_keys, uid, keys)
                        if error:
                            if request.url.path not in _BYOK_RECOVERY_PATHS:
                                return JSONResponse(status_code=403, content={'detail': error})
                            set_validated_byok_keys({}, uid)
                        else:
                            set_validated_byok_keys(validated_keys, uid)
                    except Exception:
                        # Transient verify/Firestore failures must not leave raw
                        # headers in context; ContextVar mutations in worker
                        # threads are discarded, so later route auth cannot
                        # sanitize this request.
                        set_byok_keys({})
                        set_byok_uid(None)
                        logger.warning('BYOK middleware validation failed; clearing unvalidated keys')
            return await call_next(request)
        finally:
            _byok_ctx.reset(token)
            _byok_uid_ctx.reset(uid_token)
            _byok_validated_ctx.reset(validated_token)


# ---------------------------------------------------------------------------
# Per-request fingerprint validation against Firestore enrollment
# ---------------------------------------------------------------------------


def _validated_byok_keys(uid: str, request_keys: Dict[str, str]) -> tuple[Dict[str, str], Optional[str]]:
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
    if not request_keys:
        return {}, None

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
        return {}, None

    # BYOK-active user with headers present — validate every enrolled
    # provider fingerprint.
    stored_fingerprints = state.get('fingerprints', {})

    validated: Dict[str, str] = {}
    for provider, stored_fp in stored_fingerprints.items():
        raw_key = request_keys.get(provider)
        if not raw_key:
            return {}, f"BYOK key header missing for enrolled provider: {provider}"
        request_fp = hashlib.sha256(raw_key.encode()).hexdigest()
        # Accept either the current peppered form or the legacy plain form,
        # so users enrolled before BYOK_FINGERPRINT_PEPPER was set aren't
        # locked out until they next rotate/re-enroll their keys.
        if not (
            hmac.compare_digest(peppered_fingerprint(request_fp), stored_fp)
            or hmac.compare_digest(request_fp, stored_fp)
        ):
            return {}, f"BYOK key fingerprint mismatch for provider: {provider}"
        validated[provider] = raw_key

    return validated, None


def _check_byok_validity(uid: str) -> Optional[str]:
    """Validate current context keys and retain only the enrolled capabilities."""
    validated_keys, error = _validated_byok_keys(uid, _byok_ctx.get() or {})
    if error:
        return error
    _byok_ctx.set(validated_keys)
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
    _byok_validated_ctx.set(True)
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
        _byok_validated_ctx.set(True)
        set_byok_uid(uid)
    return error


def validate_byok_websocket_keys(uid: str, request_keys: Dict[str, str]) -> tuple[Dict[str, str], Optional[str]]:
    """Validate WebSocket BYOK keys without mutating worker-local ContextVars."""
    validated_keys, error = _validated_byok_keys(uid, request_keys)
    if error:
        logger.warning('BYOK WS validation failed uid=%s: %s', uid, error)
    return validated_keys, error
