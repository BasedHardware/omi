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

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from database._client import db
from database.announcements import compare_versions
from database.cache import get_memory_cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute
_SUPPORTED_PLATFORMS = frozenset({"ios", "macos"})


def _clean_platform(platform: Optional[str]) -> str:
    """Normalize and sanitize platform identifier."""
    if not platform:
        return ""
    cleaned = platform.strip().lower()
    if "/" in cleaned or "\\" in cleaned or len(cleaned) > 64:
        return ""
    return cleaned


def _fetch_review_config(platform: str, *, firestore_client: Any = None) -> dict[str, Any]:
    """Fetch review config document from Firestore with fallback error boundary."""
    clean = _clean_platform(platform)
    if not clean:
        return {}

    client = firestore_client or db
    try:
        doc = client.collection("app_review_config").document(clean).get()
        if not getattr(doc, "exists", False):
            return {}
        raw: object = doc.to_dict()
        return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning("Failed to fetch app_review_config for platform '%s': %s", clean, e)
        return {}


def get_review_config(platform: str, *, firestore_client: Any = None) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    clean = _clean_platform(platform)
    if not clean:
        return {}

    # If an explicit client is passed, bypass global memory cache for hermeticity
    if firestore_client is not None:
        return _fetch_review_config(clean, firestore_client=firestore_client)

    cache_key = f"{_CACHE_KEY_PREFIX}{clean}"
    try:
        fetched = get_memory_cache().get_or_fetch(
            cache_key,
            lambda: _fetch_review_config(clean, firestore_client=None),
            ttl=_CACHE_TTL_SECONDS,
        )
        return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}
    except Exception as e:
        logger.warning("Cache access error for app_review_config '%s': %s", clean, e)
        return _fetch_review_config(clean, firestore_client=None)


def invalidate_review_config_cache(platform: Optional[str] = None) -> None:
    """Invalidate memory cache for a specific platform or all supported platforms."""
    try:
        cache = get_memory_cache()
        if platform:
            clean = _clean_platform(platform)
            if clean:
                cache.delete(f"{_CACHE_KEY_PREFIX}{clean}")
        else:
            for p in _SUPPORTED_PLATFORMS:
                cache.delete(f"{_CACHE_KEY_PREFIX}{p}")
    except Exception as e:
        logger.warning("Failed to invalidate app_review_config cache: %s", e)


def should_hide_subscription_ui(
    uid: str,
    platform: Optional[str],
    app_version: Optional[str],
    *,
    firestore_client: Any = None,
) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    normalized = _clean_platform(platform)
    if normalized not in _SUPPORTED_PLATFORMS:
        return False

    cfg = get_review_config(normalized, firestore_client=firestore_client) or {}

    clean_uid = uid.strip() if uid else ""
    if clean_uid:
        reviewer_uids_raw = cfg.get("reviewer_uids")
        reviewer_uids: list[object] = (
            cast(list[object], reviewer_uids_raw) if isinstance(reviewer_uids_raw, list) else []
        )
        if clean_uid in [r.strip() for r in reviewer_uids if isinstance(r, str) and r.strip()]:
            return True

    clean_version = app_version.strip() if app_version else ""
    if clean_version:
        hidden_versions_raw = cfg.get("hidden_versions")
        hidden_versions: list[object] = (
            cast(list[object], hidden_versions_raw) if isinstance(hidden_versions_raw, list) else []
        )
        for hidden in [v.strip() for v in hidden_versions if isinstance(v, str) and v.strip()]:
            try:
                if compare_versions(clean_version, hidden) == 0:
                    return True
            except Exception as e:
                logger.debug("Failed to compare app_version '%s' with hidden '%s': %s", clean_version, hidden, e)
                continue

    return False
