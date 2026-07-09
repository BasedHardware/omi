from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, cast

from database.desktop_update_channels import get_channel_release, normalize_release_manifest
from database.redis_db import get_generic_cache, set_generic_cache
from utils.metrics import (
    DESKTOP_UPDATE_FEED_VALID,
    DESKTOP_UPDATE_LKG_AGE_SECONDS,
    DESKTOP_UPDATE_POINTER_AGE_SECONDS,
    DESKTOP_UPDATE_RESOLUTION_TOTAL,
)
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

LIVE_TTL_SECONDS = 300
LKG_TTL_SECONDS = 30 * 24 * 60 * 60


def _fallback_reason(reason: str) -> str:
    return 'config_incomplete' if reason == 'pointer_missing' else 'other'


def live_cache_key(platform: str, channel: str) -> str:
    return f"desktop_update_pointer:{platform}:{channel}"


def lkg_cache_key(platform: str, channel: str) -> str:
    return f"{live_cache_key(platform, channel)}:lkg"


def _timestamp_age_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds())


def _validate_cached_release(value: Any, platform: str, channel: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    narrowed = cast(dict[str, Any], value)
    pointer = narrowed.get("pointer")
    raw_manifest = narrowed.get("manifest")
    if not isinstance(pointer, dict) or not isinstance(raw_manifest, dict):
        return None
    pointer_data = cast(dict[str, Any], pointer)
    manifest_data = cast(dict[str, Any], raw_manifest)
    if pointer_data.get("platform") != platform or pointer_data.get("channel") != channel:
        return None
    manifest = normalize_release_manifest(manifest_data)
    if pointer_data.get("release_id") != manifest["release_id"]:
        raise ValueError("cached pointer and manifest release IDs differ")
    return {"pointer": pointer_data, "manifest": manifest}


def _record_success(platform: str, channel: str, source: str, release: dict[str, Any]) -> None:
    DESKTOP_UPDATE_RESOLUTION_TOTAL.labels(platform=platform, channel=channel, source=source).inc()
    DESKTOP_UPDATE_FEED_VALID.labels(platform=platform, channel=channel).set(1)
    pointer_age = _timestamp_age_seconds(release["pointer"].get("updated_at"))
    if pointer_age is not None:
        DESKTOP_UPDATE_POINTER_AGE_SECONDS.labels(platform=platform, channel=channel).set(pointer_age)
    if source == "pointer_lkg":
        lkg_age = _timestamp_age_seconds(release.get("cached_at"))
        if lkg_age is not None:
            DESKTOP_UPDATE_LKG_AGE_SECONDS.labels(platform=platform, channel=channel).set(lkg_age)


def resolve_pointer_release(platform: str, channel: str) -> tuple[dict[str, Any] | None, str, str | None]:
    """Resolve live cache -> Firestore pointer -> validated LKG.

    The caller owns the final legacy GitHub fallback because it is asynchronous.
    """
    live_key = live_cache_key(platform, channel)
    cached = get_generic_cache(live_key)
    try:
        release = _validate_cached_release(cached, platform, channel)
    except ValueError:
        release = None
    if release is not None:
        _record_success(platform, channel, "pointer_cache", release)
        return release, "pointer_cache", None

    reason = "pointer_missing"
    try:
        release = get_channel_release(platform, channel)
        if release is not None:
            cache_value = {**release, "cached_at": datetime.now(timezone.utc).isoformat()}
            set_generic_cache(live_key, cache_value, ttl=LIVE_TTL_SECONDS)
            set_generic_cache(lkg_cache_key(platform, channel), cache_value, ttl=LKG_TTL_SECONDS)
            _record_success(platform, channel, "pointer", release)
            return release, "pointer", None
    except Exception as exc:
        reason = "pointer_invalid"
        logger.warning(
            "desktop_update_pointer_error platform=%s channel=%s reason=%s error_type=%s",
            platform,
            channel,
            reason,
            type(exc).__name__,
        )

    lkg = get_generic_cache(lkg_cache_key(platform, channel))
    try:
        release = _validate_cached_release(lkg, platform, channel)
    except ValueError:
        release = None
        reason = "lkg_invalid"
    if release is not None:
        release["cached_at"] = lkg.get("cached_at") if isinstance(lkg, dict) else None
        record_fallback(
            component='other',
            from_mode='desktop_update_pointer',
            to_mode='desktop_update_lkg',
            reason=_fallback_reason(reason),
            outcome='recovered',
            log=logger,
        )
        _record_success(platform, channel, "pointer_lkg", release)
        return release, "pointer_lkg", reason

    DESKTOP_UPDATE_FEED_VALID.labels(platform=platform, channel=channel).set(0)
    return None, "none", reason
