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

from database.announcements import compare_versions
from database.cache import get_memory_cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute
_SUPPORTED_PLATFORMS = {"ios", "macos", "android"}


def _fetch_review_config(platform: str, firestore_client: Any = None) -> dict[str, Any]:
    try:
        if firestore_client is not None:
            client = firestore_client
        else:
            from database._client import db
            client = db
        doc = client.collection("app_review_config").document(platform).get()
        if not getattr(doc, "exists", False):
            return {}
        raw: object = doc.to_dict()
        return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to fetch app_review_config for platform '{platform}': {e}")
        return {}


def get_review_config(platform: str, firestore_client: Any = None) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    cache_key = f"{_CACHE_KEY_PREFIX}{platform}"
    try:
        fetched = get_memory_cache().get_or_fetch(
            cache_key,
            lambda: _fetch_review_config(platform, firestore_client=firestore_client),
            ttl=_CACHE_TTL_SECONDS,
        )
        return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}
    except Exception as e:
        logger.warning(f"Cache error in get_review_config for platform '{platform}': {e}")
        return _fetch_review_config(platform, firestore_client=firestore_client)


def invalidate_review_config_cache(platform: Optional[str] = None) -> None:
    """Invalidate memory cache for a specific platform or all supported platforms."""
    cache = get_memory_cache()
    platforms = [platform] if platform else list(_SUPPORTED_PLATFORMS)
    for p in platforms:
        try:
            cache.delete(f"{_CACHE_KEY_PREFIX}{p}")
        except Exception:
            pass


def should_hide_subscription_ui(
    uid: str,
    platform: Optional[str],
    app_version: Optional[str],
    firestore_client: Any = None,
) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    try:
        normalized = (platform or "").strip().lower()
        if normalized not in _SUPPORTED_PLATFORMS:
            return False

        cfg = get_review_config(normalized, firestore_client=firestore_client) or {}

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
                    continue

        return False
    except Exception as e:
        logger.warning(f"Error evaluating should_hide_subscription_ui: {e}")
        return False

