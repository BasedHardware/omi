"""Persistent storage for auth credentials inside :class:`omi_cli.config.Profile`.

This module is intentionally thin — the actual TOML I/O lives in
:mod:`omi_cli.config` so the on-disk layout is centralized. We provide
convenience helpers that the auth flows and command handlers call into.
"""

from __future__ import annotations

import contextlib
import os
import sys
from typing import Optional

from omi_cli import config as cfg


@contextlib.contextmanager
def config_lock():
    """Serialize concurrent read-modify-write cycles on the config file.

    ``store_*`` functions and config commands load the whole config, mutate
    one profile, then save the whole config. Without a lock, two concurrent
    calls both read the same stale config, each overwrites a different
    profile, and the last ``save()`` wins — silently dropping the other.
    """
    lock_path = cfg.default_config_path().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        import msvcrt

        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)
    else:
        import fcntl

        with open(lock_path, "a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def store_api_key(profile_name: str, api_key: str, *, api_base: Optional[str] = None) -> cfg.Profile:
    """Persist an API key to the named profile and return the updated Profile."""
    with config_lock():
        config = cfg.load()
        profile = config.get_profile(profile_name)
        profile.auth_method = "api_key"
        profile.api_key = api_key
        profile.id_token = None
        profile.refresh_token = None
        profile.id_token_expires_at = None
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
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
) -> cfg.Profile:
    """Persist OAuth tokens to the named profile and return the updated Profile.

    ``api_key`` optionally keeps a minted developer key alongside the OAuth
    session — the ``/v1/dev/*`` endpoints authenticate with the key while
    ``omi chat`` requires the oauth session, so a browser login needs both.
    """
    with config_lock():
        config = cfg.load()
        profile = config.get_profile(profile_name)
        profile.auth_method = "oauth"
        profile.api_key = api_key
        profile.id_token = id_token
        profile.refresh_token = refresh_token
        profile.id_token_expires_at = expires_at
        if api_base:
            profile.api_base = api_base
        config.set_profile(profile)
        config.active_profile = profile_name
        cfg.save(config)
        return profile


def update_oauth_id_token(profile_name: str, *, id_token: str, expires_at: float) -> cfg.Profile:
    """Update only the short-lived ID token after a refresh round-trip."""
    with config_lock():
        config = cfg.load()
        profile = config.get_profile(profile_name)
        if profile.auth_method != "oauth":
            # Refresh on a non-oauth profile is a programming error; raise loudly.
            raise RuntimeError(f"Profile '{profile_name}' is not configured for OAuth")
        profile.id_token = id_token
        profile.id_token_expires_at = expires_at
        config.set_profile(profile)
        cfg.save(config)
        return profile


def clear_credentials(profile_name: str) -> bool:
    """Wipe credentials from the named profile. Returns True if anything was cleared."""
    with config_lock():
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