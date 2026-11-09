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

The config is advisory input to the App Store review flow, so a Firestore
outage must never turn into a 500 on `/v1/storefront` or `/v1/users/me`:
reads fail closed to an empty config and the raw exception is logged
server-side only.
"""

import logging
import re
from typing import Any, Optional, cast

from database._client import get_firestore_client
from database.announcements import compare_versions
from database.cache import get_memory_cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute

_SUPPORTED_PLATFORMS = {"ios", "macos"}

# Accepts `1`, `1.0`, `1.0.531`, `v1.0.531` and the build forms `1.0.531+607` /
# `v1.0.531+607`. Anything else is not a comparable version: `compare_versions`
# falls back to ((0, 0, 0), 0, False) for unparseable input, which would make two
# arbitrary identifiers compare equal and hide the UI for the wrong version.
_PLAUSIBLE_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+){0,2}(?:\+\d+)?$")


def _normalize_platform(platform: Optional[str]) -> str:
    """Canonical platform key: `X-App-Platform` headers arrive with stray whitespace."""
    return platform.strip().lower() if isinstance(platform, str) else ""


def _normalize_uid(uid: Optional[str]) -> str:
    return uid.strip() if isinstance(uid, str) else ""


def _is_plausible_version(version: Optional[str]) -> bool:
    """True when *version* can be compared without the parser's zero fallback."""
    if not isinstance(version, str):
        return False
    return bool(_PLAUSIBLE_VERSION_RE.match(version.strip()))


def _fetch_review_config(platform: str, firestore_client: Optional[Any] = None) -> dict[str, Any]:
    """Read the platform's config doc, failing closed to `{}` on any storage error."""
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        doc = client.collection("app_review_config").document(platform).get()
        if not getattr(doc, "exists", False):
            return {}
        raw: object = doc.to_dict()
        return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    except Exception as e:
        logger.warning("app_review_config: failed to fetch config for %r: %s", platform, e)
        return {}


def get_review_config(platform: str, firestore_client: Optional[Any] = None) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    normalized = _normalize_platform(platform)
    cache_key = f"{_CACHE_KEY_PREFIX}{normalized}"
    try:
        fetched = get_memory_cache().get_or_fetch(
            cache_key, lambda: _fetch_review_config(normalized, firestore_client), ttl=_CACHE_TTL_SECONDS
        )
    except Exception as e:
        logger.warning("app_review_config: cache read failed for %r: %s", normalized, e)
        fetched = _fetch_review_config(normalized, firestore_client)
    return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}


def should_hide_subscription_ui(uid: str, platform: Optional[str], app_version: Optional[str]) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    normalized_platform = _normalize_platform(platform)
    if normalized_platform not in _SUPPORTED_PLATFORMS:
        return False

    cfg = get_review_config(normalized_platform) or {}

    normalized_uid = _normalize_uid(uid)
    if normalized_uid:
        reviewer_uids_raw = cfg.get("reviewer_uids")
        reviewer_uids = cast(list[object], reviewer_uids_raw) if isinstance(reviewer_uids_raw, list) else []
        reviewer_uid_set = {item.strip() for item in reviewer_uids if isinstance(item, str)}
        if normalized_uid in reviewer_uid_set:
            return True

    normalized_version = app_version.strip() if isinstance(app_version, str) else ""
    if not _is_plausible_version(normalized_version):
        return False

    hidden_versions_raw = cfg.get("hidden_versions")
    hidden_versions = cast(list[object], hidden_versions_raw) if isinstance(hidden_versions_raw, list) else []
    for hidden in hidden_versions:
        if not isinstance(hidden, str):
            continue
        hidden_version = hidden.strip()
        if not _is_plausible_version(hidden_version):
            continue
        try:
            if compare_versions(normalized_version, hidden_version) == 0:
                return True
        except Exception as e:
            logger.warning(
                "app_review_config: version comparison failed for %r vs %r: %s",
                normalized_version,
                hidden_version,
                e,
            )
    return False
