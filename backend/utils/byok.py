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
    'regolo': 'x-byok-regolo',
}

# ---------------------------------------------------------------------------
# EU Privacy Mode — per-request flag that asks the backend to route every
# routable LLM workload through regolo.ai (Italy-hosted, zero retention)
# instead of the active MODEL_QOS profile. Set via the X-Privacy-Mode HTTP
# header with a truthy value; absence or a falsy value keeps the existing
# routing. Orthogonal to BYOK — a user can have Privacy Mode on with or
# without regolo key enrolment (though without the key the request will
# fail loudly at the LLM call site by design).
# ---------------------------------------------------------------------------
PRIVACY_MODE_HEADER = 'x-privacy-mode'
_PRIVACY_MODE_TRUTHY = frozenset({'1', 'on', 'true', 'yes', 'enabled'})

_privacy_mode_ctx: ContextVar[bool] = ContextVar('privacy_mode', default=False)


def _parse_privacy_mode(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _PRIVACY_MODE_TRUTHY


def is_privacy_mode_active() -> bool:
    """True when the current request sent an X-Privacy-Mode truthy header."""
    return _privacy_mode_ctx.get()


def set_privacy_mode(enabled: bool) -> None:
    """Used by the middleware; also by WS handlers that read headers manually."""
    _privacy_mode_ctx.set(bool(enabled))

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


def extract_privacy_mode_from_websocket(websocket: WebSocket) -> bool:
    """Read the X-Privacy-Mode header from a WebSocket's initial upgrade request.

    Like ``extract_byok_from_websocket``, WebSocket handlers must call this
    manually and then pass the result to ``set_privacy_mode``.
    """
    return _parse_privacy_mode(websocket.headers.get(PRIVACY_MODE_HEADER))


# ---------------------------------------------------------------------------
# Privacy Mode fallback signalling — response-side contract
#
# When Privacy Mode is on but a specific request could not actually be served
# by regolo (vision unsupported, regolo outage, persistent 429), the response
# must tell the client *which* fallback fired so the UI can surface a visible
# red banner rather than silently leaking traffic to Claude/Gemini.
#
# Contract: set the X-Privacy-Mode-Fallback response header to a short reason
# token.  Clients that sent X-Privacy-Mode but receive this header back should
# show a per-request "⚠️ This request left the EU" banner with the reason.
# ---------------------------------------------------------------------------
PRIVACY_MODE_FALLBACK_HEADER = 'x-privacy-mode-fallback'

PRIVACY_FALLBACK_VISION_UNSUPPORTED = 'vision_unsupported'
PRIVACY_FALLBACK_REGOLO_OUTAGE = 'regolo_outage'
PRIVACY_FALLBACK_REGOLO_RATE_LIMITED = 'regolo_rate_limited'
PRIVACY_FALLBACK_NO_KEY = 'no_regolo_key'

_PRIVACY_FALLBACK_REASONS = frozenset({
    PRIVACY_FALLBACK_VISION_UNSUPPORTED,
    PRIVACY_FALLBACK_REGOLO_OUTAGE,
    PRIVACY_FALLBACK_REGOLO_RATE_LIMITED,
    PRIVACY_FALLBACK_NO_KEY,
})

# The reason for the current request's fallback, if any.  Set by call sites
# that actually route non-regolo traffic while privacy mode was requested.
# Consumed by a response middleware that stamps the header before returning.
_privacy_fallback_ctx: ContextVar[Optional[str]] = ContextVar(
    'privacy_fallback_reason', default=None
)


def mark_privacy_fallback(reason: str) -> None:
    """Record that the current request fell back out of Privacy Mode.

    Call this from any code path that routes a privacy-mode request to
    Claude/Gemini/OpenAI instead of regolo — e.g. the vision router when a
    screenshot analysis can't run on regolo, or the retry loop when regolo
    5xx's three times.  The response middleware adds the X-Privacy-Mode-Fallback
    header based on this value so the client can show a banner.

    Only accepts reasons from the PRIVACY_FALLBACK_* constant set — unknown
    reasons would turn the client-side banner into noise.
    """
    if reason not in _PRIVACY_FALLBACK_REASONS:
        logger.warning('mark_privacy_fallback called with unknown reason=%s', reason)
        return
    _privacy_fallback_ctx.set(reason)


def get_privacy_fallback_reason() -> Optional[str]:
    """Return the fallback reason recorded for the current request, or None."""
    return _privacy_fallback_ctx.get()


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
        privacy_mode = _parse_privacy_mode(request.headers.get(PRIVACY_MODE_HEADER))
        token = _byok_ctx.set(keys)
        privacy_token = _privacy_mode_ctx.set(privacy_mode)
        fallback_token = _privacy_fallback_ctx.set(None)
        try:
            response = await call_next(request)
            # If a downstream code path called mark_privacy_fallback(), stamp
            # the response header so the client can surface a visible banner.
            fallback_reason = _privacy_fallback_ctx.get()
            if fallback_reason is not None and privacy_mode:
                response.headers[PRIVACY_MODE_FALLBACK_HEADER] = fallback_reason
            return response
        finally:
            _privacy_fallback_ctx.reset(fallback_token)
            _privacy_mode_ctx.reset(privacy_token)
            _byok_ctx.reset(token)


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
