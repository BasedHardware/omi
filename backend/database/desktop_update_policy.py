from typing import Any, Optional, cast
from urllib.parse import urlparse

from database._client import get_firestore_client

# Keep the default live until the stable-promotion workflow has published the
# static repair page. Operators can point an active recovery policy at that
# immutable page once it exists; an absent or malformed policy must not send
# clients to a not-yet-published route.
DEFAULT_DESKTOP_DOWNLOAD_URL = "https://api.omi.me/v2/desktop/download/latest?channel=stable"
VALID_DESKTOP_UPDATE_SEVERITIES = {"none", "banner", "required"}


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _as_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    narrowed: list[object] = cast(list[object], value)
    return [item.strip() for item in narrowed if isinstance(item, str) and item.strip()]


def _as_download_url(value: Any) -> Optional[str]:
    candidate = _as_string(value)
    if candidate is None:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def default_desktop_update_policy() -> dict[str, Any]:
    return {
        "id": "current",
        "active": False,
        "severity": "none",
        "maximum_build_number": None,
        "latest_build_number": None,
        "title": None,
        "message": None,
        "cta_text": "Download latest",
        "download_url": DEFAULT_DESKTOP_DOWNLOAD_URL,
        "can_dismiss": True,
    }


def _normalize_policy(data: dict[str, Any]) -> dict[str, Any]:
    policy = default_desktop_update_policy()

    severity = _as_string(data.get("severity")) or "none"
    if severity not in VALID_DESKTOP_UPDATE_SEVERITIES:
        severity = "none"
    maximum_build_number = _as_int(data.get("maximum_build_number"))
    if maximum_build_number is None:
        maximum_build_number = _as_int(data.get("minimum_build_number"))

    policy.update(
        {
            "id": _as_string(data.get("id")) or policy["id"],
            "active": _as_bool(data.get("active")),
            "severity": severity,
            "maximum_build_number": maximum_build_number,
            "latest_build_number": _as_int(data.get("latest_build_number")),
            "title": _as_string(data.get("title")),
            "message": _as_string(data.get("message")),
            "cta_text": _as_string(data.get("cta_text")) or policy["cta_text"],
            "download_url": _as_download_url(data.get("download_url")) or policy["download_url"],
            "can_dismiss": _as_bool(data.get("can_dismiss"), default=True),
            "platforms": _as_string_list(data.get("platforms")),
        }
    )
    return policy


def _applies_to_platform(policy: dict[str, Any], platform: str) -> bool:
    raw_platforms = policy.get("platforms")
    platforms: list[object] = cast(list[object], raw_platforms) if isinstance(raw_platforms, list) else []
    if not platforms:
        return True
    return platform in [p for p in platforms if isinstance(p, str)]


def get_desktop_update_policy(
    current_build: Optional[int], platform: str = "macos", *, firestore_client: Any = None
) -> dict[str, Any]:
    client: Any = firestore_client if firestore_client is not None else get_firestore_client()
    doc = client.collection("desktop_update_policy").document("current").get()
    if not getattr(doc, "exists", False):
        return default_desktop_update_policy()

    raw_doc: object = doc.to_dict()
    raw: dict[str, Any] = cast(dict[str, Any], raw_doc) if isinstance(raw_doc, dict) else {}
    policy = _normalize_policy(raw)
    if not _applies_to_platform(policy, platform):
        return default_desktop_update_policy()

    maximum_build = policy.get("maximum_build_number")
    if current_build is not None and maximum_build is not None and current_build > maximum_build:
        return default_desktop_update_policy()

    if not policy["active"]:
        return default_desktop_update_policy()

    return policy
