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


def _fetch_review_config(platform: str) -> dict[str, Any]:
    if not isinstance(platform, str) or not platform.strip():
        return {}
    clean_platform = platform.strip().lower()
    try:
        doc = db.collection("app_review_config").document(clean_platform).get()
    except Exception as exc:
        logger.warning(f"Failed to fetch app_review_config for {clean_platform}: {exc}")
        return {}
    if not getattr(doc, "exists", False):
        return {}
    raw: object = doc.to_dict()
    return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}


def get_review_config(platform: str) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    if not isinstance(platform, str) or not platform.strip():
        return {}
    clean_platform = platform.strip().lower()
    cache_key = f"{_CACHE_KEY_PREFIX}{clean_platform}"
    fetched = get_memory_cache().get_or_fetch(
        cache_key,
        lambda: _fetch_review_config(clean_platform),
        ttl=_CACHE_TTL_SECONDS,
    )
    return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}


_SUPPORTED_PLATFORMS = {"ios", "macos"}


def should_hide_subscription_ui(uid: str, platform: Optional[str], app_version: Optional[str]) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    if not isinstance(platform, str) or not platform.strip():
        return False
    normalized = platform.strip().lower()
    if normalized not in _SUPPORTED_PLATFORMS:
        return False

    cfg = get_review_config(normalized) or {}

    if isinstance(uid, str) and uid.strip():
        clean_uid = uid.strip()
        reviewer_uids_raw = cfg.get("reviewer_uids")
        reviewer_uids: list[object] = (
            cast(list[object], reviewer_uids_raw) if isinstance(reviewer_uids_raw, list) else []
        )
        if clean_uid in {str(r).strip() for r in reviewer_uids if isinstance(r, str)}:
            return True

    if isinstance(app_version, str) and app_version.strip():
        clean_version = app_version.strip()
        hidden_versions_raw = cfg.get("hidden_versions")
        hidden_versions: list[object] = (
            cast(list[object], hidden_versions_raw) if isinstance(hidden_versions_raw, list) else []
        )
        for hidden in [v.strip() for v in hidden_versions if isinstance(v, str) and v.strip()]:
            try:
                if compare_versions(clean_version, hidden) == 0:
                    return True
            except Exception:
                continue

    return False

