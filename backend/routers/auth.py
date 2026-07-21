import base64
import hmac
import os
import uuid
import json
import hashlib
import time
import jwt
from typing import Any, Dict, Optional, cast
from urllib.parse import quote, urlparse
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm
from fastapi import APIRouter, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import pathlib
import firebase_admin.auth
from database.redis_db import set_auth_session, get_auth_session, set_auth_code, get_auth_code, delete_auth_code
from utils.executors import critical_executor, run_blocking
from utils.http_client import get_auth_client
from utils.log_sanitizer import sanitize
from utils.metrics import AUTH_FLOW_DURATION_SECONDS, AUTH_FLOW_EVENTS
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/auth",
    tags=["authentication"],
)

# Set up Jinja2 templates
templates_path = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))


# Loopback hosts permitted for CLI/native-app OAuth flows per RFC 8252 §7.3.
_LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
_DEFAULT_MOBILE_REDIRECT = "omi://auth/callback"

# Schemes that must NOT receive an OAuth code:
#   - ``https``: would leak the code to an arbitrary remote host. (Loopback OAuth
#     is HTTP, not HTTPS, per RFC 8252.)
#   - ``javascript``, ``data``, ``vbscript``: browser-executable URLs. A code
#     leaked into one of these would be exfiltrated by the rendered page.
#   - ``file``: local file URL — could end up read by another process.
#   - ``blob``, ``filesystem``, ``about``: browser-internal pseudo-schemes.
_FORBIDDEN_REDIRECT_SCHEMES = {
    "https",
    "javascript",
    "data",
    "vbscript",
    "file",
    "blob",
    "filesystem",
    "about",
}


def _validate_redirect_uri(redirect_uri: str) -> None:
    """Reject redirect URIs that could deliver the OAuth code to an attacker.

    Allow:

    * **Custom app schemes** (``omi://``, ``omi-computer://``,
      ``omi-computer-dev://``, ``omi-fix-rewind://``, ``com.omi.app://``,
      etc.). The Omi mobile app, the macOS desktop app, and per-bundle
      developer test builds register their own URL schemes with the OS
      via ``CFBundleURLSchemes`` / Android intent filters; this is the
      standard native-app OAuth callback mechanism per RFC 8252.

    * **HTTP loopback** (``http://localhost[:PORT]/...``,
      ``http://127.0.0.1[:PORT]/...``, ``http://[::1][:PORT]/...``) for the
      CLI's loopback callback server.

    Reject:

    * **https://** and any other web-fetchable scheme — they could exfiltrate
      the auth code off-device.
    * **http://** to anything other than loopback.
    * Browser-executable schemes (``javascript:``, ``data:``, etc.).
    * Empty / unparseable input.

    Security note: the auth ``code`` is a one-time secret. If we accepted
    arbitrary URLs, an attacker who induced a user to start a flow could
    harvest the code at their own host. Restricting to native-app custom
    schemes + loopback is the RFC 8252 §7 mitigation.
    """
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri is required")

    parsed = urlparse(redirect_uri)
    scheme = (parsed.scheme or "").strip().lower()

    if not scheme:
        raise HTTPException(status_code=400, detail="redirect_uri must include a scheme")

    if scheme == "http":
        hostname = (parsed.hostname or "").strip().lower()
        if hostname not in _LOOPBACK_HOSTNAMES:
            raise HTTPException(
                status_code=400,
                detail="HTTP redirect_uri must point at loopback (localhost, 127.0.0.1, or ::1)",
            )
        return

    if scheme in _FORBIDDEN_REDIRECT_SCHEMES:
        raise HTTPException(
            status_code=400,
            detail=f"redirect_uri scheme '{scheme}' is not permitted",
        )

    # Custom app scheme. Per RFC 3986, a scheme is
    # ``ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )``. Be a little stricter
    # than urllib here — require the scheme to start with a letter and contain
    # only the RFC-allowed characters, so we don't accept garbage like ``://x``.
    if not _is_valid_scheme(scheme):
        raise HTTPException(
            status_code=400,
            detail=f"redirect_uri scheme '{scheme}' is malformed",
        )

    return


_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyz")
_ASCII_ALNUM = _ASCII_LETTERS | frozenset("0123456789")
_PKCE_ALLOWED_CHARS = _ASCII_ALNUM | frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ-._~")
_PKCE_MIN_LENGTH = 43
_PKCE_MAX_LENGTH = 128


def _is_valid_scheme(scheme: str) -> bool:
    """RFC 3986 scheme validity check: ASCII ALPHA, then ASCII ALPHA/DIGIT/+/-/.

    We deliberately use explicit ASCII sets instead of ``str.isalpha`` /
    ``str.isalnum`` — those are Unicode-aware and would happily accept
    non-ASCII letters (``ñ``, ``й``, etc.) that RFC 3986 forbids in scheme names.
    """
    if not scheme:
        return False
    lowered = scheme.lower()
    if lowered[0] not in _ASCII_LETTERS:
        return False
    return all(c in _ASCII_ALNUM or c in "+-." for c in lowered)


def _is_valid_pkce_value(value: str) -> bool:
    return _PKCE_MIN_LENGTH <= len(value) <= _PKCE_MAX_LENGTH and all(c in _PKCE_ALLOWED_CHARS for c in value)


def _validate_pkce_challenge(code_challenge: Optional[str], code_challenge_method: Optional[str]) -> str:
    if not code_challenge:
        raise HTTPException(status_code=400, detail="code_challenge is required")

    if not _is_valid_pkce_value(code_challenge):
        raise HTTPException(status_code=400, detail="code_challenge is malformed")

    method = (code_challenge_method or "").strip().upper()
    if method != "S256":
        raise HTTPException(status_code=400, detail="code_challenge_method must be S256")

    return method


def _code_challenge_for_verifier(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _verify_pkce_code_verifier(
    code_verifier: Optional[str],
    expected_code_challenge: Optional[str],
    code_challenge_method: Optional[str],
) -> None:
    method = _validate_pkce_challenge(expected_code_challenge, code_challenge_method)

    if not code_verifier:
        raise HTTPException(status_code=400, detail="code_verifier is required")

    if not _is_valid_pkce_value(code_verifier):
        raise HTTPException(status_code=400, detail="code_verifier is malformed")

    if method != "S256":
        raise HTTPException(status_code=400, detail="code_challenge_method must be S256")

    actual_code_challenge = _code_challenge_for_verifier(code_verifier)
    if not hmac.compare_digest(actual_code_challenge, cast(str, expected_code_challenge)):
        raise HTTPException(status_code=400, detail="invalid code_verifier")


def _auth_code_data_from_session(oauth_credentials: str, redirect_uri: str, session_data: Dict[str, Any]) -> str:
    code_challenge = session_data.get('code_challenge')
    code_challenge_method = session_data.get('code_challenge_method')
    _validate_pkce_challenge(code_challenge, code_challenge_method)

    return json.dumps(
        {
            'credentials': oauth_credentials,
            'redirect_uri': redirect_uri,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'provider': session_data.get('provider'),
            'auth_flow_id': session_data.get('auth_flow_id'),
            'created_at': session_data.get('created_at'),
        }
    )


def _auth_flow_id_from_state(state: Optional[str]) -> str:
    if not state:
        return "missing"
    return state.split("|", 1)[0][:64] or "missing"


def _redirect_scheme(redirect_uri: Optional[str]) -> str:
    if not redirect_uri:
        return "missing"
    return (urlparse(redirect_uri).scheme or "missing").lower()[:64]


def _failure_class(error: Optional[object]) -> str:
    if error is None:
        return "none"
    if isinstance(error, HTTPException):
        return f"http_{error.status_code}"
    value = str(error).strip().lower().replace(" ", "_")
    return value[:80] or error.__class__.__name__.lower()


def _log_auth_event(
    *,
    provider: Optional[str],
    stage: str,
    outcome: str,
    auth_flow_id: Optional[str] = None,
    failure_class: str = "none",
    status_code: Optional[int] = None,
    redirect_scheme: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    safe_provider = provider if provider in {"apple", "google"} else "unknown"
    safe_failure_class = _failure_class(failure_class)
    AUTH_FLOW_EVENTS.labels(
        provider=safe_provider,
        stage=stage,
        outcome=outcome,
        failure_class=safe_failure_class,
    ).inc()
    if duration_seconds is not None:
        AUTH_FLOW_DURATION_SECONDS.labels(provider=safe_provider, terminal_state=outcome).observe(duration_seconds)

    logger.info(
        "auth_flow_event provider=%s stage=%s outcome=%s failure_class=%s status_code=%s redirect_scheme=%s auth_flow_id=%s duration_ms=%s",
        safe_provider,
        stage,
        outcome,
        safe_failure_class,
        status_code if status_code is not None else "",
        sanitize(redirect_scheme or ""),
        sanitize(auth_flow_id or ""),
        int(duration_seconds * 1000) if duration_seconds is not None else "",
    )


@router.get("/authorize")
async def auth_authorize(
    request: Request,
    provider: str,  # 'google', 'apple'
    redirect_uri: str,
    state: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
):
    """
    User authentication authorization endpoint for the main Omi app
    Supports both initial sign-in and account linking flows
    """
    auth_flow_id = _auth_flow_id_from_state(state)
    redirect_scheme = _redirect_scheme(redirect_uri)
    _log_auth_event(
        provider=provider,
        stage="authorize_received",
        outcome="started",
        auth_flow_id=auth_flow_id,
        redirect_scheme=redirect_scheme,
    )
    if provider not in ['google', 'apple']:
        _log_auth_event(
            provider=provider,
            stage="authorize_validated",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="unsupported_provider",
            redirect_scheme=redirect_scheme,
        )
        raise HTTPException(status_code=400, detail="Unsupported provider")

    # Strict allowlist on where we'll deliver the auth code post-callback.
    try:
        _validate_redirect_uri(redirect_uri)
        normalized_code_challenge_method = _validate_pkce_challenge(code_challenge, code_challenge_method)
    except HTTPException as exc:
        _log_auth_event(
            provider=provider,
            stage="authorize_validated",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class=_failure_class(exc),
            status_code=exc.status_code,
            redirect_scheme=redirect_scheme,
        )
        raise

    # Store session for auth flow
    session_id = str(uuid.uuid4())
    session_data = {
        'provider': provider,
        'redirect_uri': redirect_uri,
        'state': state,
        'flow_type': 'user_auth',  # Distinguish from app oauth
        'code_challenge': code_challenge,
        'code_challenge_method': normalized_code_challenge_method,
        'auth_flow_id': auth_flow_id,
        'created_at': time.time(),
    }

    # Store in Redis with 5-minute expiration
    await run_blocking(critical_executor, set_auth_session, session_id, session_data, 300)
    _log_auth_event(
        provider=provider,
        stage="authorize_session_created",
        outcome="succeeded",
        auth_flow_id=auth_flow_id,
        redirect_scheme=redirect_scheme,
    )

    # Redirect to provider OAuth
    if provider == 'google':
        response = await _google_auth_redirect(session_id)
    else:
        # provider == 'apple' — only 'google'/'apple' reach here (validated above).
        response = await _apple_auth_redirect(session_id)
    _log_auth_event(
        provider=provider,
        stage="authorize_redirect_created",
        outcome="succeeded",
        auth_flow_id=auth_flow_id,
        redirect_scheme=redirect_scheme,
    )
    return response


@router.get("/callback/google")
async def auth_callback_google(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """
    Google authentication callback handler (GET method)
    """
    auth_flow_id = _auth_flow_id_from_state(state)
    _log_auth_event(provider="google", stage="provider_callback_received", outcome="started", auth_flow_id=auth_flow_id)
    if error:
        _log_auth_event(
            provider="google",
            stage="provider_callback_received",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class=error,
            status_code=400,
        )
        raise HTTPException(status_code=400, detail=f"Auth error: {error}")

    # Retrieve session
    session_data = await run_blocking(critical_executor, get_auth_session, state)
    if not session_data:
        _log_auth_event(
            provider="google",
            stage="provider_callback_session_lookup",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="auth_session_not_found",
            status_code=400,
        )
        raise HTTPException(status_code=400, detail="Invalid auth session")
    auth_flow_id = session_data.get('auth_flow_id') or auth_flow_id
    _log_auth_event(
        provider="google", stage="provider_callback_session_lookup", outcome="succeeded", auth_flow_id=auth_flow_id
    )

    # Exchange code for OAuth credentials
    oauth_credentials = await _exchange_provider_code_for_oauth_credentials('google', cast(str, code), session_data)

    # Create temporary auth code bound to the original redirect_uri
    auth_code = str(uuid.uuid4())
    app_redirect_uri = session_data.get('redirect_uri', _DEFAULT_MOBILE_REDIRECT)
    code_data = _auth_code_data_from_session(oauth_credentials, app_redirect_uri, session_data)
    await run_blocking(critical_executor, set_auth_code, auth_code, code_data, 300)
    _log_auth_event(
        provider="google",
        stage="auth_code_created",
        outcome="succeeded",
        auth_flow_id=auth_flow_id,
        redirect_scheme=_redirect_scheme(app_redirect_uri),
    )

    # Redirect to HTML page that will handle the eventual scheme/loopback redirect.
    # The original ``redirect_uri`` was validated by ``_validate_redirect_uri`` at
    # ``/authorize`` time and cannot be overridden by the caller here.
    return templates.TemplateResponse(
        "auth_callback.html",
        {
            "request": request,
            "code": auth_code,
            "state": session_data['state'] or '',
            "redirect_uri": app_redirect_uri,
        },
    )


def _parse_apple_user_name(user_json: Optional[str]) -> Optional[str]:
    """Apple includes the user's name in the ``user`` form field ONLY on the very
    first authorization (JSON: ``{"name": {"firstName", "lastName"}, ...}``).
    Parse it into a display name; return None when absent or unparseable."""
    if not user_json:
        return None
    try:
        name = (json.loads(user_json) or {}).get('name') or {}
        parts = [str(name.get('firstName', '')).strip(), str(name.get('lastName', '')).strip()]
        full = ' '.join(p for p in parts if p)
        return full or None
    except (json.JSONDecodeError, TypeError, AttributeError):
        return None


@router.post("/callback/apple")
async def auth_callback_apple_post(
    request: Request,
    code: str = Form(...),
    state: str = Form(...),
    error: Optional[str] = Form(None),
    user: Optional[str] = Form(None),
):
    """
    Apple authentication callback handler (POST method)
    Apple uses form_post response_mode, so we need a separate POST endpoint.
    Apple's id_token carries no name, so the ``user`` form field (sent only on the
    first authorization) is the sole source of the user's name — capture it here.
    """
    auth_flow_id = _auth_flow_id_from_state(state)
    _log_auth_event(provider="apple", stage="provider_callback_received", outcome="started", auth_flow_id=auth_flow_id)
    if error:
        _log_auth_event(
            provider="apple",
            stage="provider_callback_received",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class=error,
            status_code=400,
        )
        raise HTTPException(status_code=400, detail=f"Auth error: {error}")

    # Retrieve session
    session_data = await run_blocking(critical_executor, get_auth_session, state)
    if not session_data:
        _log_auth_event(
            provider="apple",
            stage="provider_callback_session_lookup",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="auth_session_not_found",
            status_code=400,
        )
        raise HTTPException(status_code=400, detail="Invalid auth session")
    auth_flow_id = session_data.get('auth_flow_id') or auth_flow_id
    _log_auth_event(
        provider="apple", stage="provider_callback_session_lookup", outcome="succeeded", auth_flow_id=auth_flow_id
    )

    # Exchange code for OAuth credentials
    oauth_credentials = await _exchange_provider_code_for_oauth_credentials('apple', code, session_data)

    # Apple sends the name in the `user` form field only on first auth; carry it
    # through the auth-code blob so `/token` can persist it (it never rides the
    # id_token). Absent on every later sign-in — expected, not an error.
    full_name = _parse_apple_user_name(user)
    if full_name:
        try:
            creds = json.loads(oauth_credentials)
            creds['full_name'] = full_name
            oauth_credentials = json.dumps(creds)
        except (json.JSONDecodeError, TypeError):
            pass

    # Create temporary auth code bound to the original redirect_uri
    auth_code = str(uuid.uuid4())
    app_redirect_uri = session_data.get('redirect_uri', _DEFAULT_MOBILE_REDIRECT)
    code_data = _auth_code_data_from_session(oauth_credentials, app_redirect_uri, session_data)
    await run_blocking(critical_executor, set_auth_code, auth_code, code_data, 300)
    _log_auth_event(
        provider="apple",
        stage="auth_code_created",
        outcome="succeeded",
        auth_flow_id=auth_flow_id,
        redirect_scheme=_redirect_scheme(app_redirect_uri),
    )

    # Redirect to HTML page that will handle the eventual scheme/loopback redirect.
    # The original ``redirect_uri`` was validated by ``_validate_redirect_uri`` at
    # ``/authorize`` time and cannot be overridden by the caller here.
    return templates.TemplateResponse(
        "auth_callback.html",
        {
            "request": request,
            "code": auth_code,
            "state": session_data['state'] or '',
            "redirect_uri": app_redirect_uri,
        },
    )


@router.post("/token")
async def auth_token(
    request: Request,
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    use_custom_token: bool = Form(False),
    code_verifier: Optional[str] = Form(None),
):
    """
    Exchange auth code for OAuth credentials
    Used for both initial sign-in and account linking flows

    Args:
        use_custom_token: If True, also generate Firebase custom token (default: True)
    """
    started_at = time.monotonic()
    provider = "unknown"
    auth_flow_id = "missing"
    redirect_scheme = _redirect_scheme(redirect_uri)
    _log_auth_event(
        provider=provider,
        stage="token_exchange_received",
        outcome="started",
        auth_flow_id=auth_flow_id,
        redirect_scheme=redirect_scheme,
    )
    if grant_type != 'authorization_code':
        _log_auth_event(
            provider=provider,
            stage="token_exchange_validated",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="unsupported_grant_type",
            status_code=400,
            redirect_scheme=redirect_scheme,
        )
        raise HTTPException(status_code=400, detail="Unsupported grant type")

    # Get auth code data from Redis
    raw_code_data = await run_blocking(critical_executor, get_auth_code, code)
    if not raw_code_data:
        _log_auth_event(
            provider=provider,
            stage="auth_code_lookup",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="auth_code_expired_or_not_found",
            status_code=400,
            redirect_scheme=redirect_scheme,
        )
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Clean up used code
    await run_blocking(critical_executor, delete_auth_code, code)

    try:
        code_data = json.loads(raw_code_data)

        # Support both new format (with redirect_uri binding) and legacy format
        if 'credentials' in code_data:
            # New format: auth code bound to redirect_uri — fail closed if redirect_uri missing
            stored_redirect_uri = code_data.get('redirect_uri')
            provider = code_data.get('provider') or provider
            auth_flow_id = code_data.get('auth_flow_id') or auth_flow_id
            created_at = code_data.get('created_at')
            if not stored_redirect_uri:
                logger.error("auth code in new format but missing redirect_uri — rejecting (fail closed)")
                _log_auth_event(
                    provider=provider,
                    stage="auth_code_validated",
                    outcome="failed",
                    auth_flow_id=auth_flow_id,
                    failure_class="auth_code_missing_redirect_uri",
                    status_code=400,
                    redirect_scheme=redirect_scheme,
                )
                raise HTTPException(status_code=400, detail="malformed auth code")
            if redirect_uri != stored_redirect_uri:
                logger.warning(
                    f"redirect_uri mismatch: expected={sanitize(stored_redirect_uri)}, got={sanitize(redirect_uri)}"
                )
                _log_auth_event(
                    provider=provider,
                    stage="auth_code_validated",
                    outcome="failed",
                    auth_flow_id=auth_flow_id,
                    failure_class="redirect_uri_mismatch",
                    status_code=400,
                    redirect_scheme=redirect_scheme,
                )
                raise HTTPException(status_code=400, detail="redirect_uri mismatch")

            try:
                _verify_pkce_code_verifier(
                    code_verifier,
                    code_data.get('code_challenge'),
                    code_data.get('code_challenge_method'),
                )
            except HTTPException as exc:
                _log_auth_event(
                    provider=provider,
                    stage="pkce_verified",
                    outcome="failed",
                    auth_flow_id=auth_flow_id,
                    failure_class=_failure_class(exc),
                    status_code=exc.status_code,
                    redirect_scheme=redirect_scheme,
                )
                raise
            _log_auth_event(
                provider=provider,
                stage="auth_code_validated",
                outcome="succeeded",
                auth_flow_id=auth_flow_id,
                redirect_scheme=redirect_scheme,
                duration_seconds=(time.time() - created_at) if isinstance(created_at, (int, float)) else None,
            )
            oauth_credentials_json = code_data['credentials']
            oauth_credentials = (
                json.loads(oauth_credentials_json)
                if isinstance(oauth_credentials_json, str)
                else oauth_credentials_json
            )
        else:
            # Legacy format: raw OAuth credentials (backwards compatible)
            oauth_credentials = code_data

        provider = oauth_credentials.get('provider')
        id_token = oauth_credentials.get('id_token')
        access_token = oauth_credentials.get('access_token')
        full_name = oauth_credentials.get('full_name')

        response = {
            "provider": provider,
            "id_token": id_token,
            "access_token": access_token,
            "provider_id": oauth_credentials.get('provider_id'),
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        # Generate custom token if requested
        if use_custom_token:
            try:
                _log_auth_event(
                    provider=provider,
                    stage="firebase_custom_token_generation",
                    outcome="started",
                    auth_flow_id=auth_flow_id,
                    redirect_scheme=redirect_scheme,
                )
                custom_token = await _generate_custom_token(provider, id_token, access_token, display_name=full_name)
                response["custom_token"] = custom_token
                _log_auth_event(
                    provider=provider,
                    stage="firebase_custom_token_generation",
                    outcome="succeeded",
                    auth_flow_id=auth_flow_id,
                    redirect_scheme=redirect_scheme,
                )
            except Exception as e:
                logger.error(f"Error generating custom token: {sanitize(str(e))}")
                _log_auth_event(
                    provider=provider,
                    stage="firebase_custom_token_generation",
                    outcome="failed",
                    auth_flow_id=auth_flow_id,
                    failure_class=e.__class__.__name__,
                    redirect_scheme=redirect_scheme,
                )
                _log_auth_event(
                    provider=provider,
                    stage="token_exchange_completed",
                    outcome="failed",
                    auth_flow_id=auth_flow_id,
                    failure_class="firebase_custom_token_generation_failed",
                    status_code=502,
                    redirect_scheme=redirect_scheme,
                    duration_seconds=time.monotonic() - started_at,
                )
                raise HTTPException(status_code=502, detail="Failed to generate authentication token")

        _log_auth_event(
            provider=provider,
            stage="token_exchange_completed",
            outcome="succeeded",
            auth_flow_id=auth_flow_id,
            redirect_scheme=redirect_scheme,
            duration_seconds=time.monotonic() - started_at,
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing OAuth credentials: {sanitize(str(e))}")
        _log_auth_event(
            provider=provider,
            stage="token_exchange_completed",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class=e.__class__.__name__,
            status_code=400,
            redirect_scheme=redirect_scheme,
            duration_seconds=time.monotonic() - started_at,
        )
        raise HTTPException(status_code=400, detail="Invalid OAuth credentials")


async def _google_auth_redirect(session_id: str):
    """
    Redirect to Google OAuth for authentication
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    api_base_url = os.getenv('BASE_API_URL')

    if not client_id:
        raise HTTPException(status_code=500, detail="Google client ID not configured")
    if not api_base_url:
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

    callback_url = f"{api_base_url}/v1/auth/callback/google"

    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={quote(client_id)}&"
        f"redirect_uri={quote(callback_url)}&"
        f"response_type=code&"
        f"scope={quote('openid email profile')}&"
        f"state={quote(session_id)}"
    )

    return RedirectResponse(url=google_auth_url)


async def _apple_auth_redirect(session_id: str):
    """
    Redirect to Apple OAuth for authentication
    """
    client_id = os.getenv('APPLE_CLIENT_ID')
    api_base_url = os.getenv('BASE_API_URL')

    if not client_id:
        raise HTTPException(status_code=500, detail="Apple client ID not configured")
    if not api_base_url:
        raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

    callback_url = f"{api_base_url}/v1/auth/callback/apple"

    apple_auth_url = (
        f"https://appleid.apple.com/auth/authorize?"
        f"client_id={client_id}&"
        f"redirect_uri={callback_url}&"
        f"response_type=code&"
        f"scope=name email&"
        f"response_mode=form_post&"
        f"state={session_id}"
    )

    return RedirectResponse(url=apple_auth_url)


async def _exchange_provider_code_for_oauth_credentials(provider: str, code: str, session_data: Dict[str, Any]) -> str:
    """
    Exchange provider-specific code for OAuth credentials
    """
    if provider == 'google':
        return await _exchange_google_code_for_oauth_credentials(code, session_data)
    elif provider == 'apple':
        return await _exchange_apple_code_for_oauth_credentials(code, session_data)
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")


async def _exchange_google_code_for_oauth_credentials(code: str, session_data: Dict[str, Any]) -> str:
    """
    Exchange Google authorization code for Google OAuth tokens
    """
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    api_base_url = os.getenv('BASE_API_URL')
    auth_flow_id = session_data.get('auth_flow_id')
    _log_auth_event(provider="google", stage="provider_token_exchange", outcome="started", auth_flow_id=auth_flow_id)

    if not all([client_id, client_secret, api_base_url]):
        _log_auth_event(
            provider="google",
            stage="provider_token_exchange",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="oauth_not_configured",
            status_code=500,
        )
        raise HTTPException(status_code=500, detail="Google OAuth not properly configured")

    callback_url = f"{api_base_url}/v1/auth/callback/google"

    # Exchange code for Google tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': callback_url,
        'grant_type': 'authorization_code',
    }

    client = get_auth_client()
    token_response = await client.post(token_url, data=token_data)
    if token_response.status_code != 200:
        logger.error(
            "Google token exchange failed: status=%s body=%s",
            token_response.status_code,
            sanitize(token_response.text),
        )
        _log_auth_event(
            provider="google",
            stage="provider_token_exchange",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="provider_http_error",
            status_code=token_response.status_code,
        )
        raise HTTPException(status_code=400, detail="Failed to exchange Google code")

    token_json = token_response.json()
    id_token = token_json.get('id_token')
    access_token = token_json.get('access_token')

    if not id_token or not access_token:
        _log_auth_event(
            provider="google",
            stage="provider_token_exchange",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class="missing_provider_token",
            status_code=400,
        )
        raise HTTPException(status_code=400, detail="Invalid Google token response")
    _log_auth_event(provider="google", stage="provider_token_exchange", outcome="succeeded", auth_flow_id=auth_flow_id)

    # Return OAuth credentials for client-side Firebase authentication
    oauth_credentials = {
        'provider': 'google',
        'id_token': id_token,
        'access_token': access_token,
        'provider_id': 'google.com',
    }

    return json.dumps(oauth_credentials)


async def _exchange_apple_code_for_oauth_credentials(code: str, session_data: Dict[str, Any]) -> str:
    """
    Exchange Apple authorization code for Apple OAuth tokens
    """
    auth_flow_id = session_data.get('auth_flow_id')
    _log_auth_event(provider="apple", stage="provider_token_exchange", outcome="started", auth_flow_id=auth_flow_id)
    try:
        # Get Apple configuration
        client_id = os.getenv('APPLE_CLIENT_ID')
        team_id = os.getenv('APPLE_TEAM_ID')
        key_id = os.getenv('APPLE_KEY_ID')
        private_key_content = os.getenv('APPLE_PRIVATE_KEY')

        if not all([client_id, team_id, key_id, private_key_content]):
            _log_auth_event(
                provider="apple",
                stage="provider_token_exchange",
                outcome="failed",
                auth_flow_id=auth_flow_id,
                failure_class="oauth_not_configured",
                status_code=500,
            )
            raise HTTPException(
                status_code=500, detail="Apple authentication not properly configured. Missing environment variables."
            )

        # Generate client secret JWT
        client_secret = _generate_apple_client_secret(
            cast(str, client_id), cast(str, team_id), cast(str, key_id), cast(str, private_key_content)
        )

        # Exchange authorization code for Apple tokens
        api_base_url = os.getenv('BASE_API_URL')
        if not api_base_url:
            _log_auth_event(
                provider="apple",
                stage="provider_token_exchange",
                outcome="failed",
                auth_flow_id=auth_flow_id,
                failure_class="base_api_url_not_configured",
                status_code=500,
            )
            raise HTTPException(status_code=500, detail="BASE_API_URL not configured")

        callback_url = f"{api_base_url}/v1/auth/callback/apple"

        token_url = "https://appleid.apple.com/auth/token"
        token_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': callback_url,
        }

        client = get_auth_client()
        token_response = await client.post(
            token_url, data=token_data, headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if token_response.status_code != 200:
            logger.error(f"Apple token exchange failed: {sanitize(token_response.text)}")
            _log_auth_event(
                provider="apple",
                stage="provider_token_exchange",
                outcome="failed",
                auth_flow_id=auth_flow_id,
                failure_class="provider_http_error",
                status_code=token_response.status_code,
            )
            raise HTTPException(status_code=400, detail="Failed to exchange Apple authorization code")

        token_json = token_response.json()
        id_token = token_json.get('id_token')
        access_token = token_json.get('access_token')  # Apple typically returns access_token

        if not id_token:
            _log_auth_event(
                provider="apple",
                stage="provider_token_exchange",
                outcome="failed",
                auth_flow_id=auth_flow_id,
                failure_class="missing_provider_token",
                status_code=400,
            )
            raise HTTPException(status_code=400, detail="No ID token received from Apple")
        _log_auth_event(
            provider="apple", stage="provider_token_exchange", outcome="succeeded", auth_flow_id=auth_flow_id
        )

        # Return OAuth credentials for client-side Firebase authentication
        oauth_credentials = {
            'provider': 'apple',
            'id_token': id_token,
            'access_token': access_token,
            'provider_id': 'apple.com',
        }

        return json.dumps(oauth_credentials)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exchanging Apple code for tokens: {sanitize(str(e))}")
        _log_auth_event(
            provider="apple",
            stage="provider_token_exchange",
            outcome="failed",
            auth_flow_id=auth_flow_id,
            failure_class=e.__class__.__name__,
            status_code=500,
        )
        raise HTTPException(status_code=500, detail="Failed to exchange Apple code for tokens")


async def _generate_custom_token(
    provider: str, id_token: str, access_token: Optional[str] = None, display_name: Optional[str] = None
) -> str:
    """
    Generate Firebase custom token by signing in with OAuth credentials
    This ensures we get the same Firebase UID that client-side auth would create
    Works with any bundle ID - perfect for multiple developers
    """
    try:
        # Get Firebase API Key from environment
        firebase_api_key = os.getenv('FIREBASE_API_KEY')
        if not firebase_api_key:
            raise Exception("FIREBASE_API_KEY not configured")

        # Sign in with OAuth credential using Firebase Auth REST API
        sign_in_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={firebase_api_key}"

        # Prepare the postBody based on provider
        if provider == 'google':
            post_body = f'id_token={id_token}&providerId=google.com'
            if access_token:
                post_body += f'&access_token={access_token}'
        elif provider == 'apple':
            post_body = f'id_token={id_token}&providerId=apple.com'
            if access_token:
                post_body += f'&access_token={access_token}'
        else:
            raise Exception(f"Unsupported provider: {provider}")

        payload = {
            'postBody': post_body,
            'requestUri': 'http://localhost',
            'returnIdpCredential': True,
            'returnSecureToken': True,
        }

        # Call Firebase Auth REST API to sign in
        client = get_auth_client()
        response = await client.post(sign_in_url, json=payload)

        if response.status_code != 200:
            logger.error(f"Firebase sign-in failed: {sanitize(response.text)}")
            raise Exception(f"Firebase sign-in failed: status={response.status_code}")

        result = response.json()
        firebase_uid = result.get('localId')

        if not firebase_uid:
            raise Exception("No Firebase UID returned from sign-in")

        logger.info(f"Firebase sign-in successful for {provider}, UID: {firebase_uid}")

        # Apple's id_token has no name and Firebase can't auto-populate it (unlike
        # Google), so persist the first-auth name onto the Firebase user. Only set
        # it when missing — Apple sends the name once, so later sign-ins pass None
        # and an already-named account is never overwritten.
        if display_name and not result.get('displayName'):
            try:
                await run_blocking(
                    critical_executor,
                    lambda: firebase_admin.auth.update_user(firebase_uid, display_name=display_name),
                )
                logger.info(f"Set Firebase display_name for {provider} UID {firebase_uid}")
            except Exception as e:
                logger.error(f"Failed to set Firebase display_name (non-fatal): {sanitize(str(e))}")

        # Create custom token for this UID
        custom_token: object = firebase_admin.auth.create_custom_token(firebase_uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped

        return custom_token.decode('utf-8') if isinstance(custom_token, bytes) else cast(str, custom_token)

    except Exception as e:
        logger.error(f"Error in _generate_custom_token: {sanitize(str(e))}")
        raise


def _generate_apple_client_secret(client_id: str, team_id: str, key_id: str, private_key_content: str) -> str:
    """
    Generate Apple client secret JWT as per Apple's requirements
    https://developer.apple.com/documentation/signinwithapplerestapi/generate_and_validate_tokens
    """
    try:
        # Load the private key from PEM content
        private_key = serialization.load_pem_private_key(
            private_key_content.encode('utf-8'),
            password=None,
        )

        # Create the JWT payload
        now = int(time.time())
        payload = {
            'iss': team_id,
            'iat': now,
            'exp': now + 3600,  # Token expires in 1 hour
            'aud': 'https://appleid.apple.com',
            'sub': client_id,
        }

        # Create the JWT headers
        headers = {
            'alg': 'ES256',
            'kid': key_id,
        }

        # Generate the client secret
        client_secret = jwt.encode(payload, cast(Any, private_key), algorithm='ES256', headers=headers)

        return client_secret

    except Exception as e:
        logger.error(f"Error generating Apple client secret: {sanitize(str(e))}")
        raise HTTPException(status_code=500, detail="Failed to generate Apple client secret")


async def _verify_apple_id_token(id_token: str, client_id: str) -> Dict[str, Any]:  # type: ignore[reportUnusedFunction]  # public verification helper, reserved for Apple ID token validation
    """
    Verify Apple ID token and extract user information
    """
    try:
        # Get Apple's public keys
        client = get_auth_client()
        apple_keys_response = await client.get('https://appleid.apple.com/auth/keys')
        if apple_keys_response.status_code != 200:
            raise Exception("Failed to fetch Apple's public keys")

        apple_keys = apple_keys_response.json()

        # Decode the token header to get the key ID
        unverified_header = jwt.get_unverified_header(id_token)
        key_id = unverified_header.get('kid')

        if not key_id:
            raise Exception("No key ID found in token header")

        # Find the matching public key
        public_key: Any = None
        for key in apple_keys['keys']:
            if key['kid'] == key_id:
                public_key = RSAAlgorithm.from_jwk(key)
                break

        if not public_key:
            raise Exception("No matching public key found")

        # Verify and decode the token
        decoded_token = jwt.decode(
            id_token, public_key, algorithms=['RS256'], audience=client_id, issuer='https://appleid.apple.com'
        )

        return decoded_token

    except Exception as e:
        logger.error(f"Error verifying Apple ID token: {e}")
        raise HTTPException(status_code=400, detail="Invalid Apple ID token")
