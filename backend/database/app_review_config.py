"""
Backend-controlled config for hiding subscription UI in specific app versions
(e.g. during App Store review, while we wait to ship full IAP).

Stored in Firestore so the flag can be flipped without a redeploy:

  Collection: app_review_config
  Document ID: ios | android
  Fields:
    hidden_versions: list[str]   # e.g. ["1.0.531", "1.0.531+607"]
    reviewer_uids:   list[str]   # demo accounts that should always be hidden

A version in `hidden_versions` matches the app version using the same
semantic-vs-build comparison the announcements module already uses, so an
entry like "1.0.531" matches every build of that semantic version.
"""

from typing import Optional

from database._client import db
from database.announcements import _compare_versions
from database.cache import get_memory_cache

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute


def _fetch_review_config(platform: str) -> dict:
    doc = db.collection("app_review_config").document(platform).get()
    return doc.to_dict() if doc.exists else {}


def get_review_config(platform: str) -> dict:
    """Return the review-config doc for a platform, cached for 60s."""
    cache_key = f"{_CACHE_KEY_PREFIX}{platform}"
    return get_memory_cache().get_or_fetch(cache_key, lambda: _fetch_review_config(platform), ttl=_CACHE_TTL_SECONDS)


def should_hide_subscription_ui(uid: str, platform: Optional[str], app_version: Optional[str]) -> bool:
    """True when the iOS subscription UI must be hidden for this caller."""
    if not platform or platform.lower() != "ios":
        return False

    cfg = get_review_config("ios") or {}

    if uid and uid in (cfg.get("reviewer_uids") or []):
        return True

    if app_version:
        for hidden in cfg.get("hidden_versions") or []:
            if _compare_versions(app_version, hidden) == 0:
                return True

    return False
