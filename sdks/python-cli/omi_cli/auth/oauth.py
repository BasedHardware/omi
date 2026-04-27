"""Browser-based Firebase OAuth flow for omi-cli.

Flow (RFC 8252 native-app pattern with CSRF state token):

1. Spin up an HTTP server bound to ``127.0.0.1`` on an ephemeral port.
2. Open the user's default browser at
   ``{api_base}/v1/auth/authorize?provider=...&redirect_uri=http://127.0.0.1:PORT/callback&state=<csrf>``.
3. The user signs in via Google (or Apple). The Omi backend's
   ``auth_callback.html`` template navigates the browser back to the
   loopback URL with ``?code=...&state=...``.
4. The localhost handler captures the code and validates the state token.
5. The CLI exchanges the code via ``POST /v1/auth/token`` to get a Firebase
   custom token, then calls Firebase's ``signInWithCustomToken`` REST endpoint
   to mint a long-lived refresh token + a short-lived ID token.
6. Tokens are persisted to the user's profile.

Refresh is implemented separately in :func:`refresh_id_token` and called
opportunistically by the HTTP client just before each request.
"""

from __future__ import annotations

import html
import http.server
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from typing import Any, Optional

import httpx

from omi_cli import config as cfg
from omi_cli.auth.store import store_oauth_tokens, update_oauth_id_token
from omi_cli.config import Profile
from omi_cli.errors import AuthError, UsageError

# Public Firebase Web API key for the ``based-hardware`` Firebase project.
# Firebase API keys are *not* secrets — they identify which project a
# REST request targets and are embedded in every public web/mobile build.
# See https://firebase.google.com/docs/projects/api-keys.
_FIREBASE_API_KEY = "AIzaSyAqRWo5RN8YhlzNzBEWJ3GxG3S_1SJlxx4"
_FIREBASE_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken" f"?key={_FIREBASE_API_KEY}"
)
_FIREBASE_REFRESH_URL = f"https://securetoken.googleapis.com/v1/token?key={_FIREBASE_API_KEY}"

_CALLBACK_PATH = "/callback"
_BROWSER_TIMEOUT_SECONDS = 300  # five minutes from "open browser" to "code in hand"
_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# Refresh slightly before the server-quoted expiry to absorb clock skew + the
# round-trip time of the upcoming API call.
_REFRESH_MARGIN_SECONDS = 60


# --- Browser flow ----------------------------------------------------------


def login_with_browser(
    profile_name: str,
    *,
    api_base: str,
    provider: str = "google",
    open_browser: bool = True,
) -> Profile:
    """Run the Firebase OAuth browser flow and persist the resulting tokens.

    Returns the updated :class:`Profile`.

    ``open_browser=False`` is useful in headless tests; the caller is then
    responsible for actually visiting the printed URL.
    """
    if provider not in {"google", "apple"}:
        raise UsageError(
            message=f"Unknown OAuth provider: {provider}",
            detail="Supported: google, apple.",
        )

    state = secrets.token_urlsafe(32)
    received: dict[str, Optional[str]] = {}
    received_event = threading.Event()

    handler_class = _make_callback_handler(received, received_event)

    # Bind to 127.0.0.1 explicitly (not "localhost" — some systems resolve that
    # to ::1 first, and we want the IPv4 loopback to be the canonical one we
    # tell the backend about).
    with _OneShotHTTPServer(("127.0.0.1", 0), handler_class) as server:
        port = server.server_address[1]
        redirect_uri = f"http://127.0.0.1:{port}{_CALLBACK_PATH}"
        auth_url = (
            f"{api_base.rstrip('/')}/v1/auth/authorize?"
            f"provider={urllib.parse.quote(provider)}&"
            f"redirect_uri={urllib.parse.quote(redirect_uri, safe='')}&"
            f"state={urllib.parse.quote(state)}"
        )

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        try:
            print(f"Opening browser for {provider} sign-in...")
            print(f"If your browser does not open, visit:\n  {auth_url}")
            if open_browser:
                # webbrowser.open returns False on failure but is otherwise
                # silent; we always print the URL above as a fallback.
                webbrowser.open(auth_url, new=2)

            if not received_event.wait(timeout=_BROWSER_TIMEOUT_SECONDS):
                raise AuthError(
                    message="OAuth flow timed out",
                    detail=(
                        f"No callback received within {_BROWSER_TIMEOUT_SECONDS // 60} minutes. "
                        "Try again, or use `omi auth login --api-key` instead."
                    ),
                )
        finally:
            server.shutdown()
            thread.join(timeout=2)

    if received.get("error"):
        raise AuthError(
            message="OAuth provider returned an error",
            detail=str(received["error"]),
        )

    if received.get("state") != state:
        # CSRF guard — refuse if the callback's state token doesn't match the
        # one we generated. A mismatch means either a buggy backend or someone
        # injected a different flow into our session.
        raise AuthError(
            message="OAuth state mismatch",
            detail="The browser callback did not match the original session token. Possible CSRF — aborting.",
        )

    code = received.get("code")
    if not code:
        raise AuthError(
            message="OAuth callback missing authorization code",
            detail="The browser callback URL did not include a `code` parameter.",
        )

    custom_token = _exchange_code_for_custom_token(api_base, code, redirect_uri)
    id_token, refresh_token, expires_in = _firebase_signin_with_custom_token(custom_token)

    return store_oauth_tokens(
        profile_name,
        id_token=id_token,
        refresh_token=refresh_token,
        expires_at=time.time() + expires_in - _REFRESH_MARGIN_SECONDS,
        api_base=api_base,
    )


# --- Refresh ---------------------------------------------------------------


def refresh_id_token(profile_name: str) -> str:
    """Mint a fresh Firebase ID token using the stored refresh token.

    Persists the new token + expiry to the profile and returns the new ID
    token so callers can use it immediately without re-loading config.
    """
    config = cfg.load()
    profile = config.get_profile(profile_name)

    if profile.auth_method != "oauth" or not profile.refresh_token:
        raise UsageError(
            message="Nothing to refresh",
            detail=(
                f"Profile '{profile_name}' is not configured for OAuth. "
                "API keys are long-lived and don't need refreshing."
            ),
        )

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            _FIREBASE_REFRESH_URL,
            data={"grant_type": "refresh_token", "refresh_token": profile.refresh_token},
        )
    if resp.status_code != 200:
        raise AuthError(
            message=f"Firebase refresh failed ({resp.status_code})",
            detail="Re-run `omi auth login --browser` to get fresh credentials.",
        )

    data = resp.json()
    new_id_token = data.get("id_token")
    new_refresh_token = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600) or 3600)

    if not new_id_token:
        raise AuthError(
            message="Firebase refresh response was missing id_token",
            detail=f"Received keys: {sorted(data.keys())}",
        )

    expires_at = time.time() + expires_in - _REFRESH_MARGIN_SECONDS

    # If Firebase rotated the refresh token, persist the new one too. Otherwise
    # we just bump the ID token + expiry in place.
    if new_refresh_token and new_refresh_token != profile.refresh_token:
        store_oauth_tokens(
            profile_name,
            id_token=new_id_token,
            refresh_token=new_refresh_token,
            expires_at=expires_at,
            api_base=profile.api_base,
        )
    else:
        update_oauth_id_token(
            profile_name,
            id_token=new_id_token,
            expires_at=expires_at,
        )

    return str(new_id_token)


def needs_refresh(profile: Profile, now: Optional[float] = None) -> bool:
    """Return True if the stored OAuth ID token is past (or near) its expiry."""
    if profile.auth_method != "oauth":
        return False
    if not profile.id_token_expires_at:
        # Token of unknown age — be safe and refresh.
        return True
    return (now or time.time()) >= profile.id_token_expires_at


# --- Internals -------------------------------------------------------------


def _exchange_code_for_custom_token(api_base: str, code: str, redirect_uri: str) -> str:
    """Hit ``POST /v1/auth/token`` and pull the Firebase custom token out of the response."""
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            f"{api_base.rstrip('/')}/v1/auth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "use_custom_token": "true",
            },
        )
    if resp.status_code != 200:
        raise AuthError(
            message=f"Token exchange failed ({resp.status_code})",
            detail="The Omi auth server rejected the OAuth code. Try `omi auth login --browser` again.",
        )

    body = resp.json()
    custom_token = body.get("custom_token")
    if not custom_token:
        raise AuthError(
            message="Server did not return a Firebase custom token",
            detail="The backend may not have FIREBASE_API_KEY configured.",
        )
    return str(custom_token)


def _firebase_signin_with_custom_token(custom_token: str) -> tuple[str, str, int]:
    """Sign into Firebase with the custom token and return ``(id_token, refresh_token, expires_in)``."""
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        resp = client.post(
            _FIREBASE_SIGNIN_URL,
            json={"token": custom_token, "returnSecureToken": True},
        )
    if resp.status_code != 200:
        raise AuthError(
            message=f"Firebase signInWithCustomToken failed ({resp.status_code})",
            detail="Verify the public Firebase API key matches the project this backend issues custom tokens for.",
        )
    data = resp.json()
    id_token = data.get("idToken")
    refresh_token = data.get("refreshToken")
    expires_in = int(data.get("expiresIn", 3600) or 3600)

    if not id_token or not refresh_token:
        raise AuthError(
            message="Firebase signin response missing tokens",
            detail=f"Received keys: {sorted(data.keys())}",
        )
    return id_token, refresh_token, expires_in


def _first(values: Optional[list[str]]) -> Optional[str]:
    """Return the first element of a list-or-None, or None if absent/empty."""
    if not values:
        return None
    return values[0]


def _make_callback_handler(
    received: dict[str, Optional[str]],
    received_event: threading.Event,
) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a handler class that captures ``code`` / ``state`` / ``error`` from the callback URL."""

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 — http.server uses do_VERB
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != _CALLBACK_PATH:
                # Browsers love to fetch ``/favicon.ico`` etc. Treat anything
                # other than the callback path as a 404 and keep waiting.
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(parsed.query)
            received["code"] = _first(params.get("code"))
            received["state"] = _first(params.get("state"))
            received["error"] = _first(params.get("error"))

            ok = received.get("code") is not None and received.get("error") is None

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            if ok:
                body = (
                    "<!DOCTYPE html><html><body style=\"font-family: -apple-system, sans-serif; "
                    "padding: 48px; max-width: 480px; margin: 0 auto; text-align: center;\">"
                    "<h1>✓ Logged in</h1>"
                    "<p>Authentication complete. You can close this tab and return to your terminal.</p>"
                    "</body></html>"
                )
            else:
                # ``html.escape`` is the right tool for inlining untrusted text
                # into HTML — ``urllib.parse.quote`` is a URL-percent-encoder
                # and would let through characters HTML treats specially.
                err = received.get("error") or "missing code"
                body = (
                    "<!DOCTYPE html><html><body style=\"font-family: -apple-system, sans-serif; "
                    "padding: 48px; max-width: 480px; margin: 0 auto; text-align: center;\">"
                    "<h1>Authentication failed</h1>"
                    f"<p>{html.escape(err)}</p>"
                    "<p>Close this tab and run <code>omi auth login --browser</code> again.</p>"
                    "</body></html>"
                )
            self.wfile.write(body.encode("utf-8"))
            received_event.set()

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — stdlib signature
            # Silence the default access-log noise. The CLI manages its own UX.
            return

    return _CallbackHandler


class _OneShotHTTPServer(socketserver.TCPServer):
    """``TCPServer`` with port-reuse so a previous botched login can't block this one."""

    allow_reuse_address = True
