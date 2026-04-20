import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException, WebSocketException
from fastapi import Request
from firebase_admin import auth
from firebase_admin.auth import InvalidIdTokenError
import logging
import redis as redis_pkg

from database.redis_db import check_rate_limit, try_acquire_listen_lock
from database.users import record_user_platform
from utils.rate_limit_config import RATE_POLICIES, RATE_LIMIT_SHADOW, get_effective_limit

logger = logging.getLogger(__name__)


def get_user(uid: str):
    user = auth.get_user(uid)
    return user


def _is_dev_environment() -> bool:
    """Dev bypasses only fire when LOCAL_DEVELOPMENT=true AND env is not prod.

    Two gates so a single misconfigured env var can't nuke auth in production.
    """
    if os.getenv('LOCAL_DEVELOPMENT') != 'true':
        return False
    env = (os.getenv('ENV') or os.getenv('ENVIRONMENT') or '').lower()
    if env in ('prod', 'production', 'live'):
        return False
    return True


def verify_token(token: str) -> str:
    """
    Verify a Firebase token and return the uid.

    ADMIN_KEY impersonation is ONLY honored in dev environments (see
    _is_dev_environment). In production, ADMIN_KEY is strictly a shared
    secret for server-to-server admin endpoints (routers/apps.py,
    fair_use_admin.py, etc.) — it MUST NOT grant the ability to act as
    arbitrary users. If it ever leaks from CI/Helm/etc., the blast radius
    is limited to those endpoints.

    Raises:
        InvalidIdTokenError: If the token is invalid.
    """
    # Dev-only: ADMIN_KEY can mint an arbitrary uid for integration tests.
    # Production path skips this entirely.
    if _is_dev_environment():
        admin_key = os.getenv('ADMIN_KEY')
        if admin_key and token.startswith(admin_key):
            impersonated = token[len(admin_key):]
            logger.warning(f"[dev] ADMIN_KEY impersonation uid={impersonated}")
            return impersonated

    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except InvalidIdTokenError:
        if _is_dev_environment():
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


# Process-local fallback used only when Redis is unreachable. Replicated
# across pods so the effective limit is N * declared when the fallback
# kicks in — accept as graceful degradation rather than failing requests.
_local_rl_cached: dict = {}


def _rate_limit_local_fallback(key: str, requests_per_window: int, window_seconds: int) -> None:
    current = _local_rl_cached.get(key)
    if current:
        current = json.loads(current)
        remaining = current["remaining"]
        timestamp = current["timestamp"]
        current_time = int(time.time())
        if current_time - timestamp >= window_seconds:
            remaining = requests_per_window - 1
            timestamp = current_time
        elif remaining == 0:
            raise HTTPException(status_code=429, detail="Too Many Requests")
        else:
            remaining -= 1
    else:
        remaining = requests_per_window - 1
        timestamp = int(time.time())
    _local_rl_cached[key] = json.dumps({"timestamp": timestamp, "remaining": remaining})


def rate_limit_custom(endpoint: str, request: Request, requests_per_window: int, window_seconds: int):
    """Per-IP rate limit for pre-auth / non-UID endpoints.

    Primary path uses Redis so all replicas share a counter. Falls back
    to process-local state only on Redis error (fail-open rather than
    block legitimate traffic during a Redis outage).
    """
    ip = request.client.host if request.client else 'unknown'
    key = f"{endpoint}:ip:{ip}"

    try:
        allowed, _remaining, retry_after = check_rate_limit(
            key, f'custom:{endpoint}', requests_per_window, window_seconds
        )
    except redis_pkg.exceptions.RedisError as e:
        logger.warning(f"Rate limit Redis error, falling back to local: {e}")
        _rate_limit_local_fallback(f"rate_limit:{endpoint}:{ip}", requests_per_window, window_seconds)
        return True

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too Many Requests",
            headers={"Retry-After": str(retry_after)},
        )
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


def require_admin_key(secret_key: str = Header(...)):
    """FastAPI dependency: constant-time check that the request carries
    the admin shared secret.

    Replaces the widespread pattern `if secret_key != os.getenv('ADMIN_KEY')`
    which is vulnerable to timing side-channels (char-by-char `!=` short-
    circuits). `hmac.compare_digest` runs in time proportional to the
    LONGER of the two inputs regardless of where they differ.

    Use as: `def handler(_: None = Depends(require_admin_key), ...)` or
    via router-level `dependencies=[Depends(require_admin_key)]`.
    """
    expected = os.getenv('ADMIN_KEY') or ''
    # Reject if server isn't configured — do not allow an empty ADMIN_KEY
    # to match any request.
    if not expected:
        raise HTTPException(status_code=503, detail='ADMIN_KEY is not configured')
    if not secret_key or not hmac.compare_digest(str(secret_key), expected):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
