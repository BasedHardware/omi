"""Auth dependencies and rate limiting for FastAPI endpoints.

HTTP auth is handled by per-router dependencies in ``utils/auth_middleware.py``
(``require_firebase``, ``require_firebase_no_byok``) which set
``request.state.uid`` and ``request.state.byok_keys``.

This module retains:
- ``verify_token`` — shared by auth deps and WS auth
- ``with_rate_limit`` — per-endpoint rate limiting (reads request.state.uid)
- WebSocket auth helpers — router-level deps don't fire for WS
- ``get_current_user_uid`` — DEPRECATED, kept only for backward compat
- Rate limiting utilities
"""

import json
import os
import time
from typing import Dict

from fastapi import Depends, Header, HTTPException, WebSocketException
from fastapi import Request
from starlette.websockets import WebSocket
from firebase_admin import auth
from firebase_admin.auth import InvalidIdTokenError
import logging
import redis as redis_pkg

from database.redis_db import check_rate_limit, try_acquire_listen_lock
from database.users import record_user_platform
from utils.byok import (
    _extract_byok_from_request,
    extract_byok_from_websocket,
    validate_and_return_byok_keys,
    validate_and_return_byok_keys_ws,
)
from utils.rate_limit_config import RATE_POLICIES, RATE_LIMIT_SHADOW, get_effective_limit

logger = logging.getLogger(__name__)


def get_user(uid: str):
    user = auth.get_user(uid)
    return user


def verify_token(token: str) -> str:
    """
    Verify a Firebase token or ADMIN_KEY and return the uid.

    Args:
        token: The token to verify (Firebase ID token or ADMIN_KEY format)

    Returns:
        The user's uid

    Raises:
        InvalidIdTokenError: If the token is invalid
    """
    # Check for ADMIN_KEY format
    admin_key = os.getenv('ADMIN_KEY')
    if admin_key and token.startswith(admin_key):
        return token[len(admin_key) :]

    # Verify Firebase token
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except InvalidIdTokenError:
        if os.getenv('LOCAL_DEVELOPMENT') == 'true':
            return '123'
        raise


def get_current_user_uid(
    authorization: str = Header(None),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
):
    """DEPRECATED: Auth is now handled by per-router dependencies (require_firebase).

    Kept for backward compatibility with any code that still references it.
    Prefer reading ``request.state.uid`` set by the auth dependency.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header not found")
    elif len(str(authorization).split(' ')) != 2:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    try:
        token = authorization.split(' ')[1]
        uid = verify_token(token)
    except InvalidIdTokenError as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    try:
        record_user_platform(uid, x_app_platform)
    except Exception as e:  # noqa: BLE001 — telemetry must never fail the request
        logger.debug("record_user_platform swallowed error for uid=%s: %s", uid, e)

    return uid


def get_current_user_uid_no_byok_validation(
    authorization: str = Header(None),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
):
    """DEPRECATED: BYOK-skip auth is now handled by require_firebase_no_byok dependency.

    Kept for backward compatibility.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header not found")
    elif len(str(authorization).split(' ')) != 2:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    try:
        token = authorization.split(' ')[1]
        uid = verify_token(token)
    except InvalidIdTokenError as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    try:
        record_user_platform(uid, x_app_platform)
    except Exception as e:  # noqa: BLE001 — telemetry must never fail the request
        logger.debug("record_user_platform swallowed error for uid=%s: %s", uid, e)

    return uid


# ---------------------------------------------------------------------------
# WebSocket auth — BaseHTTPMiddleware does NOT fire for WS scope
# ---------------------------------------------------------------------------


def _verify_ws_auth(authorization: str) -> str:
    """Common WebSocket auth — verifies token, returns uid.

    Raises WebSocketException(code=1008) instead of HTTPException(401) so the
    ASGI server sends a proper WebSocket close frame (not a handshake crash).
    """
    if not authorization:
        raise WebSocketException(code=1008, reason="Authorization header not found")
    elif len(str(authorization).split(' ')) != 2:
        raise WebSocketException(code=1008, reason="Invalid authorization token")

    try:
        token = authorization.split(' ')[1]
        return verify_token(token)
    except InvalidIdTokenError as e:
        logger.error(f"WebSocket auth failed: {e}")
        raise WebSocketException(code=1008, reason="Invalid or expired token")
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        raise WebSocketException(code=1008, reason="Auth error")


def get_current_user_uid_ws_listen(authorization: str = Header(None)):
    """WebSocket auth for /v4/listen — NO rate limiting.

    Mobile apps reconnect legitimately on network switch / backgrounding,
    so the per-UID rate limiter must not block them.
    """
    return _verify_ws_auth(authorization)


def get_current_user_uid_ws(authorization: str = Header(None)):
    """WebSocket auth WITH per-UID rate limiting (7s window).

    Use for WebSocket endpoints that need retry-storm protection.
    """
    uid = _verify_ws_auth(authorization)

    # Fail-open on Redis errors to avoid reintroducing handshake crashes
    try:
        if not try_acquire_listen_lock(uid):
            logger.warning(f"WebSocket rate limited uid={uid}")
            raise WebSocketException(code=1008, reason="Rate limited, retry later")
    except WebSocketException:
        raise
    except Exception as e:
        logger.error(f"Rate limit check failed (allowing connection): {e}")

    return uid


def get_current_user_uid_from_ws_message(message: dict) -> str:
    """
    Get user uid from WebSocket first-message auth.

    Expected message format: {"type": "auth", "token": "<token>"}

    Returns:
        The user's uid

    Raises:
        ValueError: If message format is invalid
        InvalidIdTokenError: If token is invalid
    """
    if message.get("type") == "websocket.disconnect":
        raise ValueError("Client disconnected")

    text = message.get("text")
    if text is None:
        raise ValueError("Expected JSON auth message")

    try:
        auth_data = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON")

    if auth_data.get("type") != "auth":
        raise ValueError("First message must be auth")

    token = auth_data.get("token")
    if not token:
        raise ValueError("Missing token")

    return verify_token(token)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

cached = {}


def rate_limit_custom(endpoint: str, request: Request, requests_per_window: int, window_seconds: int):
    ip = request.client.host
    key = f"rate_limit:{endpoint}:{ip}"

    # Check if the IP is already rate-limited
    current = cached.get(key)
    if current:
        current = json.loads(current)
        remaining = current["remaining"]
        timestamp = current["timestamp"]
        current_time = int(time.time())

        # Check if the time window has expired
        if current_time - timestamp >= window_seconds:
            remaining = requests_per_window - 1  # Reset the counter for the new window
            timestamp = current_time
        elif remaining == 0:
            raise HTTPException(status_code=429, detail="Too Many Requests")

        remaining -= 1

    else:
        # If no previous data found, start a new time window
        remaining = requests_per_window - 1
        timestamp = int(time.time())

    # Update the rate limit info in Redis
    current = {"timestamp": timestamp, "remaining": remaining}
    cached[key] = json.dumps(current)

    return True


# Dependency to enforce custom rate limiting for specific endpoints
def rate_limit_dependency(endpoint: str = "", requests_per_window: int = 60, window_seconds: int = 60):
    def rate_limit(request: Request):
        return rate_limit_custom(endpoint, request, requests_per_window, window_seconds)

    return rate_limit


def _enforce_rate_limit(key: str, policy_name: str):
    """Shared rate limit enforcement. Raises HTTPException(429) or logs in shadow mode.

    One Redis round-trip per call (Lua script). Fail-open on Redis errors.
    """
    max_requests, window = get_effective_limit(policy_name)
    try:
        allowed, remaining, retry_after = check_rate_limit(key, policy_name, max_requests, window)
    except redis_pkg.exceptions.RedisError as e:
        logger.error(f"Rate limit Redis error (allowing request): {e}")
        return

    if not allowed:
        if RATE_LIMIT_SHADOW:
            logger.warning(f"[shadow] rate_limit_exceeded policy={policy_name} key={key} retry_after={retry_after}")
            return
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )


def with_rate_limit(policy_or_auth_dep, policy_name: str = None):
    """Per-endpoint rate limiting.

    Two calling conventions:
    - ``with_rate_limit("policy")`` — reads uid from request.state (set by auth dependency)
    - ``with_rate_limit(auth_dep, "policy")`` — legacy, wraps a custom auth dep (e.g. developer API key)
    """
    if policy_name is None:
        # New convention: with_rate_limit("policy")
        actual_policy = policy_or_auth_dep
        if actual_policy not in RATE_POLICIES:
            raise ValueError(f"Unknown rate limit policy: {actual_policy}")

        async def dependency(request: Request):
            uid = getattr(request.state, 'uid', None)
            if not uid:
                raise HTTPException(status_code=401, detail="Authentication required")
            _enforce_rate_limit(uid, actual_policy)

        return dependency
    else:
        # Legacy convention: with_rate_limit(auth_dep, "policy")
        auth_dependency = policy_or_auth_dep
        if policy_name not in RATE_POLICIES:
            raise ValueError(f"Unknown rate limit policy: {policy_name}")

        async def dependency(uid: str = Depends(auth_dependency)):
            _enforce_rate_limit(uid, policy_name)
            return uid

        return dependency


def check_rate_limit_inline(key: str, policy_name: str):
    """Check rate limit inline (for endpoints with custom auth).

    Use when auth is not a standard Depends() pattern (e.g., MCP, integration).
    """
    _enforce_rate_limit(key, policy_name)


# ---------------------------------------------------------------------------
# BYOK WebSocket dependencies — middleware doesn't fire for WS
# ---------------------------------------------------------------------------


def get_validated_byok_keys_ws(
    websocket: WebSocket,
    uid: str = Depends(get_current_user_uid_ws_listen),
) -> Dict[str, str]:
    """Extract and validate BYOK keys from a WebSocket upgrade request.

    Returns validated keys dict (empty if user is not BYOK-active or no
    headers).  Raises WebSocketException(4003) on fingerprint mismatch.
    """
    keys = extract_byok_from_websocket(websocket)
    return validate_and_return_byok_keys_ws(uid, keys)


def timeit(func):
    """
    Decorator for measuring function's running time.
    """

    def measure_time(*args, **kw):
        start_time = time.time()
        result = func(*args, **kw)
        logger.info("Processing time of %s(): %.2f seconds." % (func.__qualname__, time.time() - start_time))
        return result

    return measure_time


def delete_account(uid: str):
    auth.delete_user(uid)
    return {"message": "User deleted"}
