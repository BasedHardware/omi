"""
Server-driven config for toggling subscription-surface visibility per
platform and app version.

Stored in Firestore so the flag can be flipped without a redeploy:

  Collection: app_review_config
  Document ID: ios | android | macos
  Fields:
    hidden_versions: list[str]   # e.g. ["1.0.531", "1.0.531+607"]
    reviewer_uids:   list[str]   # specific UIDs to always hide for

A version in `hidden_versions` matches the app version using the same
semantic-vs-build comparison the announcements module already uses, so an
entry like "1.0.531" matches every build of that semantic version.
"""

import logging
from typing import Any, Optional, cast

from database._client import db
from database.announcements import compare_versions
from database.cache import get_memory_cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute
_MAX_PLATFORM_LENGTH = 32
_UNSAFE_PLATFORM_CHARS = ("/", "\\")


def _clean_platform(platform: Any) -> Optional[str]:
    """Normalize a platform identifier, returning None when it is unsafe.

    The platform is used verbatim as a Firestore document ID, so only short,
    simple tokens are accepted: non-string, empty/whitespace-only, oversized,
    and path-separator-bearing values are rejected before any lookup.
    """
    if not isinstance(platform, str):
        return None
    normalized = platform.strip().lower()
    if not normalized or len(normalized) > _MAX_PLATFORM_LENGTH:
        return None
    if any(char in normalized for char in _UNSAFE_PLATFORM_CHARS):
        return None
    return normalized


def _fetch_review_config(platform: str, *, firestore_client: Any = None) -> dict[str, Any]:
    client = firestore_client if firestore_client is not None else db
    try:
        doc = client.collection("app_review_config").document(platform).get()
    except Exception:
        # Fail open: a transient Firestore outage must not turn a config lookup
        # into a user-visible 500 on hot read paths such as GET /v1/users/me.
        logger.exception("app_review_config fetch failed for platform=%s", platform)
        return {}
    if not getattr(doc, "exists", False):
        return {}
    raw: object = doc.to_dict()
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}


def get_review_config(platform: str, *, firestore_client: Any = None) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    cleaned = _clean_platform(platform)
    if cleaned is None:
        return {}
    cache_key = f"{_CACHE_KEY_PREFIX}{cleaned}"
    try:
        fetched = get_memory_cache().get_or_fetch(
            cache_key,
            lambda: _fetch_review_config(cleaned, firestore_client=firestore_client),
            ttl=_CACHE_TTL_SECONDS,
        )
    except Exception:
        # A failing cache must not take the config path down with it: fall back
        # to a direct fetch instead of propagating the error to the caller.
        logger.exception("app_review_config cache lookup failed for platform=%s", cleaned)
        fetched = _fetch_review_config(cleaned, firestore_client=firestore_client)
    return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}


def invalidate_review_config_cache(platform: str) -> None:
    """Drop the cached config for one platform after an admin flip."""
    cleaned = _clean_platform(platform)
    if cleaned is None:
        return
    try:
        get_memory_cache().delete(f"{_CACHE_KEY_PREFIX}{cleaned}")
    except Exception:
        logger.exception("app_review_config cache invalidation failed for platform=%s", cleaned)


_SUPPORTED_PLATFORMS = {"ios", "macos"}


def should_hide_subscription_ui(uid: str, platform: Optional[str], app_version: Optional[str]) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    normalized = _clean_platform(platform)
    if normalized is None or normalized not in _SUPPORTED_PLATFORMS:
        return False

    cfg = get_review_config(normalized) or {}

    if uid:
        reviewer_uids_raw = cfg.get("reviewer_uids")
        reviewer_uids: list[object] = (
            cast(list[object], reviewer_uids_raw) if isinstance(reviewer_uids_raw, list) else []
        )
        if uid in [r for r in reviewer_uids if isinstance(r, str)]:
            return True

    if app_version:
        hidden_versions_raw = cfg.get("hidden_versions")
        hidden_versions: list[object] = (
            cast(list[object], hidden_versions_raw) if isinstance(hidden_versions_raw, list) else []
        )
        for hidden in [v for v in hidden_versions if isinstance(v, str)]:
            try:
                if compare_versions(app_version, hidden) == 0:
                    return True
            except Exception:
                # A malformed version string must not crash the caller: skip it.
                logger.exception("compare_versions failed for app_version=%s hidden=%s", app_version, hidden)
                continue

    return False
