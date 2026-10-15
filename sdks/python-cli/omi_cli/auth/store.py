"""Persistent storage for auth credentials inside :class:`omi_cli.config.Profile`.

This module is intentionally thin — the actual TOML I/O lives in
:mod:`omi_cli.config` so the on-disk layout is centralized. We provide
convenience helpers that the auth flows and command handlers call into.
"""

from __future__ import annotations

from typing import Optional

from omi_cli import config as cfg


FirebaseSession = tuple[str, str, float]
"""``(id_token, refresh_token, expires_at)`` of the signed-in user's Firebase session."""


def store_api_key(
    profile_name: str,
    api_key: str,
    *,
    api_base: Optional[str] = None,
    firebase_session: Optional[FirebaseSession] = None,
) -> cfg.Profile:
    """Persist an API key to the named profile and return the updated Profile.

    Browser sign-in mints the key from a Firebase session and passes that session
    along: the key authenticates the ``/v1/dev/*`` routes while the session stays
    on the profile for the user-identity routes (``omi chat``). A pasted key has no
    session, so any earlier one is dropped.
    """
    config = cfg.load()
    profile = config.get_profile(profile_name)
    profile.auth_method = "api_key"
    profile.api_key = api_key
    if firebase_session is None:
        profile.id_token = None
        profile.refresh_token = None
        profile.id_token_expires_at = None
    else:
        profile.id_token, profile.refresh_token, profile.id_token_expires_at = firebase_session
    if api_base:
        profile.api_base = api_base
    config.set_profile(profile)
    config.active_profile = profile_name
    cfg.save(config)
    return profile


def store_oauth_tokens(
    profile_name: str,
    *,
    id_token: str,
    refresh_token: str,
    expires_at: float,
    api_base: Optional[str] = None,
) -> cfg.Profile:
    """Persist OAuth tokens to the named profile and return the updated Profile."""
    config = cfg.load()
    profile = config.get_profile(profile_name)
    profile.auth_method = "oauth"
    profile.api_key = None
    profile.id_token = id_token
    profile.refresh_token = refresh_token
    profile.id_token_expires_at = expires_at
    if api_base:
        profile.api_base = api_base
    config.set_profile(profile)
    config.active_profile = profile_name
    cfg.save(config)
    return profile


def update_firebase_session(
    profile_name: str, *, id_token: str, expires_at: float, refresh_token: Optional[str] = None
) -> cfg.Profile:
    """Persist a refreshed Firebase session, keeping the profile's auth method and key.

    Used after a refresh round-trip for both an ``oauth`` profile and an ``api_key``
    profile that carries the session from browser sign-in. ``refresh_token`` is
    stored only when Firebase rotated it.
    """
    config = cfg.load()
    profile = config.get_profile(profile_name)
    if not profile.refresh_token and profile.auth_method != "oauth":
        # Refresh on a profile without a session is a programming error; raise loudly.
        raise RuntimeError(f"Profile '{profile_name}' has no Firebase session to refresh")
    profile.id_token = id_token
    profile.id_token_expires_at = expires_at
    if refresh_token:
        profile.refresh_token = refresh_token
    config.set_profile(profile)
    cfg.save(config)
    return profile


def update_oauth_id_token(profile_name: str, *, id_token: str, expires_at: float) -> cfg.Profile:
    """Update only the short-lived ID token after a refresh round-trip."""
    return update_firebase_session(profile_name, id_token=id_token, expires_at=expires_at)


def clear_credentials(profile_name: str) -> bool:
    """Wipe credentials from the named profile. Returns True if anything was cleared."""
    config = cfg.load()
    if profile_name not in config.profiles:
        return False
    profile = config.profiles[profile_name]
    had_creds = profile.is_authenticated()
    profile.auth_method = None
    profile.api_key = None
    profile.id_token = None
    profile.refresh_token = None
    profile.id_token_expires_at = None
    config.set_profile(profile)
    cfg.save(config)
    return had_creds
