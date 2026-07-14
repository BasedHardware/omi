import json
import os
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from fastapi import Depends, Header, HTTPException, WebSocketException
from fastapi import Request
from starlette.websockets import WebSocket
from firebase_admin import auth
from firebase_admin.auth import CertificateFetchError, ExpiredIdTokenError, InvalidIdTokenError, RevokedIdTokenError
import logging
import redis as redis_pkg

from database.redis_db import check_rate_limit, try_acquire_listen_lock
from database.users import record_client_device, record_user_platform
from utils.api_key_families import FIREBASE_FAMILY, wrong_key_family_detail
from utils.client_device import resolve_client_device
from utils.byok import extract_byok_from_websocket, set_byok_keys, validate_byok_request, validate_byok_websocket
from utils.executors import critical_executor, run_blocking
from utils.rate_limit_config import RATE_POLICIES, RATE_LIMIT_SHADOW, get_effective_limit

logger = logging.getLogger(__name__)

WS_AUTH_CODE_TOKEN_REFRESH = 4001
WS_AUTH_CODE_RELOGIN_REQUIRED = 4004


def get_user(uid: str) -> Any:
    return auth.get_user(uid)  # type: ignore[reportUnknownVariableType,reportUnknownMemberType]  # firebase_admin auth untyped


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
        decoded_token = cast(Any, auth.verify_id_token(token))  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped
        return decoded_token['uid']
    except InvalidIdTokenError:
        if os.getenv('LOCAL_DEVELOPMENT') == 'true':
            return '123'
        raise


def get_current_user_uid(
    authorization: str = Header(None),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
    x_device_id_hash: str = Header(None, alias='X-Device-Id-Hash'),
    x_app_version: str = Header(None, alias='X-App-Version'),
) -> str:
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

    token = authorization.split(' ')[1]
    key_family_mismatch = wrong_key_family_detail(token, FIREBASE_FAMILY)
    if key_family_mismatch:
        raise HTTPException(status_code=401, detail=key_family_mismatch)

    try:
        uid = verify_token(token)
    except InvalidIdTokenError as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    try:
        record_user_platform(uid, x_app_platform)
    except Exception as e:  # noqa: BLE001 — telemetry must never fail the request
        logger.debug("record_user_platform swallowed error for uid=%s: %s", uid, e)

    try:
        device_ctx = resolve_client_device(
            x_app_platform=x_app_platform,
            x_device_id_hash=x_device_id_hash,
            x_app_version=x_app_version,
        )
        record_client_device(
            uid,
            client_device_id=device_ctx.client_device_id,
            platform=device_ctx.platform,
            app_version=device_ctx.app_version,
        )
    except Exception as e:  # noqa: BLE001 — telemetry must never fail the request
        logger.debug("record_client_device swallowed error for uid=%s: %s", uid, e)

    # Validate BYOK keys against Firestore enrollment for ALL authenticated
    # HTTP endpoints.  Runs after auth so we have the uid.  Lightweight: uses
    # a 30-second TTL cache for Firestore state, and is a no-op when no BYOK
    # headers are present.
    validate_byok_request(uid)

    return uid


def get_current_user_uid_no_byok_validation(
    authorization: str = Header(None),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
    x_device_id_hash: str = Header(None, alias='X-Device-Id-Hash'),
    x_app_version: str = Header(None, alias='X-App-Version'),
) -> str:
    """Auth dependency that skips BYOK fingerprint validation.

    Used ONLY by the BYOK activation/deactivation endpoints — those need to
    update Firestore fingerprints, so validating the old fingerprints first
    would deadlock key rotation.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header not found")
    elif len(str(authorization).split(' ')) != 2:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    token = authorization.split(' ')[1]
    key_family_mismatch = wrong_key_family_detail(token, FIREBASE_FAMILY)
    if key_family_mismatch:
        raise HTTPException(status_code=401, detail=key_family_mismatch)

    try:
        uid = verify_token(token)
    except InvalidIdTokenError as e:
        logger.error(e)
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    try:
        record_user_platform(uid, x_app_platform)
    except Exception as e:  # noqa: BLE001 — telemetry must never fail the request
        logger.debug("record_user_platform swallowed error for uid=%s: %s", uid, e)

    try:
        device_ctx = resolve_client_device(
            x_app_platform=x_app_platform,
            x_device_id_hash=x_device_id_hash,
            x_app_version=x_app_version,
        )
        record_client_device(
            uid,
            client_device_id=device_ctx.client_device_id,
            platform=device_ctx.platform,
            app_version=device_ctx.app_version,
        )
    except Exception as e:  # noqa: BLE001 — telemetry must never fail the request
        logger.debug("record_client_device swallowed error for uid=%s: %s", uid, e)

    return uid


def _verify_ws_auth(authorization: str) -> str:
    """Common WebSocket auth — verifies token, returns uid.

    Raises WebSocketException instead of HTTPException(401) so the ASGI server
    sends a proper WebSocket close frame (not a handshake crash). Auth failures
    use 1008 by default, 4001 when the client should refresh its token, and
    4004 when it should force re-login.
    """
    if not authorization:
        raise WebSocketException(code=1008, reason="Authorization header not found")
    elif len(str(authorization).split(' ')) != 2:
        raise WebSocketException(code=1008, reason="Invalid authorization token")

    try:
        token = authorization.split(' ')[1]
        return verify_token(token)
    except (InvalidIdTokenError, CertificateFetchError) as e:
        close_code, reason = _get_ws_auth_close(e)
        logger.error("WebSocket auth failed: code=%s error=%s", close_code, e)
        raise WebSocketException(code=close_code, reason=reason)
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        raise WebSocketException(code=1008, reason="Auth error")


def _get_ws_auth_close(error: Exception) -> 'tuple[int, str]':
    if isinstance(error, RevokedIdTokenError):
        return WS_AUTH_CODE_RELOGIN_REQUIRED, "Token revoked; re-login required"
    if isinstance(error, CertificateFetchError):
        return WS_AUTH_CODE_TOKEN_REFRESH, "Token refresh required"
    if isinstance(error, ExpiredIdTokenError):
        return WS_AUTH_CODE_TOKEN_REFRESH, "Token refresh required"

    message = str(error).lower()
    if 'revoked' in message:
        return WS_AUTH_CODE_RELOGIN_REQUIRED, "Token revoked; re-login required"
    if 'expired' in message or 'certificate' in message:
        return WS_AUTH_CODE_TOKEN_REFRESH, "Token refresh required"
    return 1008, "Invalid authorization token"


async def get_current_user_uid_ws_listen(
    websocket: WebSocket = None,  # pyright: ignore[reportArgumentType]  # FastAPI needs bare WebSocket type for WS injection
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
    Firestore calls are offloaded via ``run_blocking``.
    """
    uid = await run_blocking(critical_executor, _verify_ws_auth, authorization)

    # Extract BYOK headers from the WS upgrade request and validate.
    if websocket is not None:  # pyright: ignore[reportUnnecessaryComparison]  # websocket is None outside WS context
        byok_keys = extract_byok_from_websocket(websocket)
        if byok_keys:
            set_byok_keys(byok_keys)
        error = await run_blocking(critical_executor, validate_byok_websocket, uid)
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


def get_current_user_uid_from_ws_message(message: Dict[str, Any]) -> str:
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
        loaded = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON")

    auth_data: Dict[str, Any] = cast(Dict[str, Any], loaded) if isinstance(loaded, dict) else {}

    if auth_data.get("type") != "auth":
        raise ValueError("First message must be auth")

    token = auth_data.get("token")
    if not token:
        raise ValueError("Missing token")

    return verify_token(token)


cached: Dict[str, Any] = {}


def rate_limit_custom(endpoint: str, request: Request, requests_per_window: int, window_seconds: int) -> bool:
    ip = request.client.host if request.client else None
    key = f"rate_limit:{endpoint}:{ip}"

    # Check if the IP is already rate-limited
    current_raw = cached.get(key)
    current: Optional[Dict[str, Any]] = None
    if current_raw:
        try:
            current = cast(Dict[str, Any], json.loads(current_raw))
        except (json.JSONDecodeError, TypeError, KeyError):
            # Corrupt cache entry: fail open by starting a fresh window rather than 500ing the request.
            current = None

    timestamp = 0
    remaining = 0
    if current:
        current_time = int(time.time())
        remaining = current.get("remaining", 0)
        timestamp = current.get("timestamp", 0)

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
    cached[key] = json.dumps({"timestamp": timestamp, "remaining": remaining})

    return True


# Dependency to enforce custom rate limiting for specific endpoints
def rate_limit_dependency(
    endpoint: str = "", requests_per_window: int = 60, window_seconds: int = 60
) -> Callable[[Request], bool]:
    def rate_limit(request: Request) -> bool:
        return rate_limit_custom(endpoint, request, requests_per_window, window_seconds)

    return rate_limit


def _enforce_rate_limit(key: str, policy_name: str, *, fail_closed: bool = False) -> None:
    """Shared rate limit enforcement. Raises HTTPException(429) or logs in shadow mode.

    One Redis round-trip per call (Lua script). Fail-open on Redis errors.
    """
    max_requests, window = get_effective_limit(policy_name)
    try:
        allowed, _remaining, retry_after = check_rate_limit(key, policy_name, max_requests, window)
    except redis_pkg.exceptions.RedisError as e:  # type: ignore[reportAttributeAccessIssue]  # redis pkg exposes exceptions at runtime
        logger.error(f"Rate limit Redis error policy={policy_name} key={key}: {e}")
        if fail_closed:
            raise HTTPException(status_code=503, detail="Rate limiter unavailable")
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


def rate_limit_key_for_context(auth_context: Any) -> str:
    """Return the narrowest stable rate-limit subject for an auth context."""
    app_id = getattr(auth_context, 'app_id', None)
    key_id = getattr(auth_context, 'key_id', None)
    uid = getattr(auth_context, 'uid', None)
    if app_id and key_id:
        return f"app:{app_id}:key:{key_id}"
    if app_id or key_id:
        raise HTTPException(status_code=403, detail="Missing API key identity")
    if uid:
        return str(uid)
    raise HTTPException(status_code=401, detail="Authenticated subject missing")


def check_api_key_rate_limit(
    *,
    prefix: str,
    uid: str,
    app_id: Optional[str],
    key_id: Optional[str],
    policy_name: str,
) -> None:
    if not key_id:
        raise HTTPException(status_code=403, detail="Missing API key identity")
    key = f"{prefix}:{uid}:{app_id or 'unknown_app'}:{key_id}"
    _enforce_rate_limit(key, policy_name, fail_closed=True)


def with_rate_limit(auth_dependency: Callable[..., Any], policy_name: str) -> Callable[..., Any]:
    """Wrap an auth dependency with per-UID rate limiting.

    After auth succeeds, checks the rate limit for that UID.
    One Redis call per request. Fail-open on Redis errors for first-party user paths.

    Args:
        auth_dependency: FastAPI dependency that returns a UID string.
        policy_name: Key in RATE_POLICIES (utils/rate_limit_config.py).
    """
    if policy_name not in RATE_POLICIES:
        raise ValueError(f"Unknown rate limit policy: {policy_name}")

    async def dependency(uid: str = Depends(auth_dependency)) -> str:
        await run_blocking(critical_executor, _enforce_rate_limit, uid, policy_name)
        return uid

    return dependency


def with_rate_limit_context(auth_context_dependency: Callable[..., Any], policy_name: str) -> Callable[..., Any]:
    """Wrap a context-returning auth dependency with per-subject rate limiting.

    After auth succeeds, checks the rate limit for app/key identity when present,
    falling back to UID for first-party or legacy auth contexts.
    One Redis call per request. Fail-closed on Redis errors for API-key paths.

    Args:
        auth_context_dependency: FastAPI dependency that returns an auth context
            object with a ``uid`` attribute (e.g. ProductAuthorizationContext).
        policy_name: Key in RATE_POLICIES (utils/rate_limit_config.py).
    """
    if policy_name not in RATE_POLICIES:
        raise ValueError(f"Unknown rate limit policy: {policy_name}")

    async def dependency(auth_context: Any = Depends(auth_context_dependency)) -> Any:
        key = rate_limit_key_for_context(auth_context)
        await run_blocking(critical_executor, _enforce_rate_limit, key, policy_name, fail_closed=True)
        return auth_context

    return dependency


def check_rate_limit_context(auth_context: Any, policy_name: str) -> None:
    """Check rate limit inline for an already-authenticated context."""
    _enforce_rate_limit(rate_limit_key_for_context(auth_context), policy_name, fail_closed=True)


def check_rate_limit_inline(key: str, policy_name: str) -> None:
    """Check rate limit inline (for endpoints with custom auth).

    Use when auth is not a standard Depends() pattern (e.g., MCP, integration).
    """
    _enforce_rate_limit(key, policy_name)


F = TypeVar("F", bound=Callable[..., Any])


def timeit(func: F) -> F:
    """
    Decorator for measuring function's running time.
    """

    def measure_time(*args: Any, **kw: Any) -> Any:
        start_time = time.time()
        result = func(*args, **kw)
        logger.info("Processing time of %s(): %.2f seconds." % (func.__qualname__, time.time() - start_time))
        return result

    return cast(F, measure_time)


def delete_account(uid: str) -> Dict[str, str]:
    auth.delete_user(uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped
    return {"message": "User deleted"}
