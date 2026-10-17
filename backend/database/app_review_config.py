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

from database._client import db
from database.announcements import parse_version, compare_versions
from database.cache import get_memory_cache

_CACHE_KEY_PREFIX = "app_review_config:"
_CACHE_TTL_SECONDS = 60  # short so flag flips propagate within a minute


def _fetch_review_config(platform: str, firestore_client: Optional[Any] = None) -> dict[str, Any]:
    try:
        client = firestore_client if firestore_client is not None else db
        doc = client.collection("app_review_config").document(platform).get()
        if not getattr(doc, "exists", False):
            return {}
        raw: object = doc.to_dict()
        return cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    except Exception:
        # A transient Firestore failure must not 500 the callers — treat as
        # no review config (visible subscription surfaces, same as missing doc).
        return {}


def get_review_config(platform: str, firestore_client: Optional[Any] = None) -> dict[str, Any]:
    """Return the review-config doc for a platform, cached for 60s."""
    if firestore_client is not None:
        return _fetch_review_config(platform, firestore_client)
    cache_key = f"{_CACHE_KEY_PREFIX}{platform}"
    fetched = get_memory_cache().get_or_fetch(cache_key, lambda: _fetch_review_config(platform), ttl=_CACHE_TTL_SECONDS)
    return cast(dict[str, Any], fetched) if isinstance(fetched, dict) else {}


_SUPPORTED_PLATFORMS = {"ios", "macos"}


def _is_plausible_version(version: str) -> bool:
    """True when ``version`` parses to something other than the zero fallback.

    ``parse_version`` returns ``((0, 0, 0), 0, False)`` for unparseable
    input, so two malformed strings collide at compare==0. Guarding the
    comparison keeps "malformed..version" from hiding subscription surfaces
    for every other malformed entry.
    """
    try:
        semantic, _build, has_build = parse_version(version)
    except Exception:
        return False
    return semantic != (0, 0, 0) or has_build


def _version_matches(app_version: str, hidden: str) -> bool:
    """Exact match first; semantic comparison only for plausible versions."""
    if app_version == hidden:
        return True
    if not (_is_plausible_version(app_version) and _is_plausible_version(hidden)):
        return False
    try:
        return compare_versions(app_version, hidden) == 0
    except Exception:
        return False


def should_hide_subscription_ui(
    uid: str,
    platform: Optional[str],
    app_version: Optional[str],
    firestore_client: Optional[Any] = None,
) -> bool:
    """True when subscription surfaces should be hidden for this caller."""
    normalized = (platform or "").strip().lower()
    if normalized not in _SUPPORTED_PLATFORMS:
        return False

    cfg = get_review_config(normalized, firestore_client) or {}

    uid_clean = (uid or "").strip()
    if uid_clean:
        reviewer_uids_raw = cfg.get("reviewer_uids")
        reviewer_uids: list[object] = (
            cast(list[object], reviewer_uids_raw) if isinstance(reviewer_uids_raw, list) else []
        )
        reviewers = {r.strip() for r in reviewer_uids if isinstance(r, str) and r.strip()}
        if uid_clean in reviewers:
            return True

    if app_version:
        version_clean = app_version.strip()
        hidden_versions_raw = cfg.get("hidden_versions")
        hidden_versions: list[object] = (
            cast(list[object], hidden_versions_raw) if isinstance(hidden_versions_raw, list) else []
        )
        for hidden in [v.strip() for v in hidden_versions if isinstance(v, str)]:
            if _version_matches(version_clean, hidden):
                return True

    return False
