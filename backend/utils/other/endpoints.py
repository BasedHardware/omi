import asyncio
import json
import os
import time

from fastapi import Depends, Header, HTTPException, WebSocketException
from fastapi import Request
from starlette.websockets import WebSocket
from firebase_admin import auth
from firebase_admin.auth import InvalidIdTokenError
import logging
import redis as redis_pkg

from database.redis_db import check_rate_limit, try_acquire_listen_lock
from database.users import record_user_platform
from utils.byok import extract_byok_from_websocket, set_byok_keys, validate_byok_request, validate_byok_websocket
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
    """FastAPI dependency for HTTP endpoints with Authorization header.

    Side-effect: records the signup/last-active platform for the user via
    `record_user_platform`, which is throttled via Redis to one Firestore
    write per (uid, platform) every 10 minutes. Failures here never fail the
    request — it's telemetry, not auth.

    Also validates BYOK headers against Firestore enrollment (if applicable).
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

    # Validate BYOK keys against Firestore enrollment for ALL authenticated
    # HTTP endpoints.  Runs after auth so we have the uid.  Lightweight: uses
    # a 30-second TTL cache for Firestore state, and is a no-op when no BYOK
    # headers are present.
    validate_byok_request(uid)

    return uid


def get_current_user_uid_no_byok_validation(
    authorization: str = Header(None),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
):
    """Auth dependency that skips BYOK fingerprint validation.

    Used ONLY by the BYOK activation/deactivation endpoints — those need to
    update Firestore fingerprints, so validating the old fingerprints first
    would deadlock key rotation.
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


async def get_current_user_uid_ws_listen(
    websocket: WebSocket = None,
    authorization: str = Header(None),
):
    """WebSocket auth for /v4/listen — NO rate limiting.

    Mobile apps reconnect legitimately on network switch / backgrounding,
    so the per-UID rate limiter must not block them.

    Also extracts BYOK headers from the WS upgrade request and validates
    them against Firestore enrollment (BaseHTTPMiddleware doesn't fire for
    WebSocket scope, so this is the shared entry point for WS BYOK).

    **Why async:** Starlette runs sync WS deps in a worker thread via
    ``anyio.to_thread.run_sync``, which copies the context. ContextVar
    mutations inside the sync dep (``set_byok_keys``) are discarded when
    control returns to the async handler, so ``get_byok_key('deepgram')``
    would return None downstream. Running the dep on the event loop keeps
    the mutation in the handler's context; the blocking Firebase and
    Firestore calls are offloaded via ``asyncio.to_thread``.
    """
    uid = await asyncio.to_thread(_verify_ws_auth, authorization)

    # Extract BYOK headers from the WS upgrade request and validate.
    if websocket is not None:
        byok_keys = extract_byok_from_websocket(websocket)
        if byok_keys:
            set_byok_keys(byok_keys)
        error = await asyncio.to_thread(validate_byok_websocket, uid)
        if error:
            raise WebSocketException(code=4003, reason=error)

    return uid


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


def with_rate_limit(auth_dependency, policy_name: str):
    """Wrap an auth dependency with per-UID rate limiting.

    After auth succeeds, checks the rate limit for that UID.
    One Redis call per request. Fail-open on Redis errors.

    Args:
        auth_dependency: FastAPI dependency that returns a UID string.
        policy_name: Key in RATE_POLICIES (utils/rate_limit_config.py).
    """
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
