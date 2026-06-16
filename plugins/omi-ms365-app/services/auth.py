"""Microsoft OAuth + MSAL token handling.

One MSAL ConfidentialClientApplication per process, token caches are per-user
and persisted via the TokenStore abstraction.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from msal import ConfidentialClientApplication, SerializableTokenCache

from config import GRAPH_SCOPES, get_settings
from services.storage import get_store

log = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when the user has no valid token or auth failed."""


def _build_msal_app(cache: SerializableTokenCache | None = None) -> ConfidentialClientApplication:
    settings = get_settings()
    return ConfidentialClientApplication(
        client_id=settings.microsoft_client_id,
        client_credential=settings.microsoft_client_secret,
        authority=settings.authority,
        token_cache=cache,
    )


async def _load_cache(user_id: str) -> SerializableTokenCache:
    cache = SerializableTokenCache()
    blob = await get_store().get(user_id)
    if blob:
        cache.deserialize(blob)
    return cache


async def _save_cache_if_dirty(user_id: str, cache: SerializableTokenCache) -> None:
    if cache.has_state_changed:
        await get_store().set(user_id, cache.serialize())


def build_auth_url(state: str) -> str:
    """Builds the Microsoft login URL the browser should redirect to."""
    settings = get_settings()
    app = _build_msal_app()
    return app.get_authorization_request_url(
        scopes=[s for s in GRAPH_SCOPES if s != "offline_access"],
        state=state,
        redirect_uri=settings.microsoft_redirect_uri,
        prompt="select_account",
    )


async def exchange_code_for_token(code: str, user_id: str) -> dict[str, Any]:
    """Exchanges an OAuth code for tokens and persists them for the user."""
    settings = get_settings()
    cache = await _load_cache(user_id)
    app = _build_msal_app(cache)
    result = app.acquire_token_by_authorization_code(
        code,
        scopes=[s for s in GRAPH_SCOPES if s != "offline_access"],
        redirect_uri=settings.microsoft_redirect_uri,
    )
    if "error" in result:
        raise AuthError(
            f"Token exchange failed: {result.get('error')} — {result.get('error_description')}"
        )
    await _save_cache_if_dirty(user_id, cache)
    return result


async def get_access_token(user_id: str) -> str:
    """Returns a valid access token for the given OMI user.

    Uses MSAL's silent flow. If no refresh token is available, raises AuthError
    so the caller can prompt the user to reconnect.
    """
    cache = await _load_cache(user_id)
    app = _build_msal_app(cache)

    accounts = app.get_accounts()
    if not accounts:
        raise AuthError("No Microsoft account linked — user must reconnect.")

    result = app.acquire_token_silent(
        scopes=[s for s in GRAPH_SCOPES if s != "offline_access"],
        account=accounts[0],
    )
    if not result or "access_token" not in result:
        raise AuthError("Silent token acquisition failed — user must reconnect.")

    await _save_cache_if_dirty(user_id, cache)
    return result["access_token"]


async def disconnect(user_id: str) -> None:
    await get_store().delete(user_id)


def build_setup_redirect(user_id: str) -> str:
    """Produces the URL the OMI setup screen should send the user to."""
    settings = get_settings()
    qs = urlencode({"uid": user_id})
    return f"{settings.app_base_url}/auth/microsoft?{qs}"
