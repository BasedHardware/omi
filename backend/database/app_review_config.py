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

from typing import Any, Optional, cast
import logging

from database._client import db
from database.announcements import compare_versions
from database.cache import get_memory_cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute
_SUPPORTED_PLATFORMS = {"ios", "macos"}


def _fetch_review_config(platform: str, client: Any = None) -> dict[str, Any]:
    target_db = client if client is not None else db
    try:
        doc = target_db.collection("app_review_config").document(platform).get()
        if not getattr(doc, "exists", False):
            return {}
        raw: object = doc.to_dict()
        return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to fetch review config for platform {platform}: {e}")
        return {}


def get_review_config(platform: str, client: Any = None) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    cache_key = f"{_CACHE_KEY_PREFIX}{platform}"
    fetched = get_memory_cache().get_or_fetch(
        cache_key, lambda: _fetch_review_config(platform, client=client), ttl=_CACHE_TTL_SECONDS
    )
    return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}


def should_hide_subscription_ui(
    uid: str,
    platform: Optional[str],
    app_version: Optional[str],
    client: Any = None,
) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    normalized = (platform or "").strip().lower()
    if normalized not in _SUPPORTED_PLATFORMS:
        return False

    cfg = get_review_config(normalized, client=client) or {}

    clean_uid = uid.strip() if uid else ""
    if clean_uid:
        reviewer_uids_raw = cfg.get("reviewer_uids")
        if isinstance(reviewer_uids_raw, list):
            reviewer_set = {str(r).strip() for r in reviewer_uids_raw if r}
            if clean_uid in reviewer_set:
                return True

    clean_version = app_version.strip() if app_version else ""
    if clean_version:
        hidden_versions_raw = cfg.get("hidden_versions")
        if isinstance(hidden_versions_raw, list):
            for hidden in hidden_versions_raw:
                if isinstance(hidden, str) and hidden.strip():
                    try:
                        if compare_versions(clean_version, hidden.strip()) == 0:
                            return True
                    except Exception:
                        continue

    return False
