from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, cast
from urllib.parse import urlparse

from google.cloud.firestore import transactional

from database._client import get_firestore_client

CHANNELS_COLLECTION = "desktop_update_channels"
MANIFESTS_COLLECTION = "desktop_release_manifests"
VALID_CHANNELS = frozenset({"stable", "beta"})
VALID_PLATFORMS = frozenset({"macos", "windows", "linux"})
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip() or None


def _https_url(data: dict[str, Any], key: str, *, required: bool) -> str | None:
    value = _required_string(data, key) if required else _optional_string(data, key)
    if value is None:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{key} must be an https URL")
    return value


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a positive integer")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError as exc:
            raise ValueError(f"{key} must be a positive integer") from exc
    else:
        raise ValueError(f"{key} must be a positive integer")
    if result <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return result


def _generation(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("pointer generation must be a non-negative integer")


def _digest(data: dict[str, Any], key: str, pattern: re.Pattern[str], *, required: bool) -> str | None:
    value = _required_string(data, key) if required else _optional_string(data, key)
    if value is not None and not pattern.fullmatch(value):
        raise ValueError(f"{key} has an invalid digest")
    return value.lower() if value is not None else None


def normalize_release_manifest(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and narrow the immutable release manifest contract."""
    platform = _required_string(data, "platform").lower()
    if platform not in VALID_PLATFORMS:
        raise ValueError("platform must be macos, windows, or linux")

    changelog_raw = data.get("changelog", [])
    if not isinstance(changelog_raw, list):
        raise ValueError("changelog must be a list of strings")
    changelog_values = cast(list[object], changelog_raw)
    if any(not isinstance(item, str) for item in changelog_values):
        raise ValueError("changelog must be a list of strings")
    changelog = [item for item in changelog_values if isinstance(item, str)]

    qualification = data.get("qualification", {})
    if not isinstance(qualification, dict):
        raise ValueError("qualification must be an object")

    published_at = _required_string(data, "published_at")
    try:
        datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("published_at must be an ISO-8601 timestamp") from exc

    release_id = _required_string(data, "release_id")
    if "/" in release_id:
        raise ValueError("release_id must not contain a slash")

    manifest = {
        "release_id": release_id,
        "platform": platform,
        "version": _required_string(data, "version"),
        "build_number": _positive_int(data, "build_number"),
        "zip_url": _https_url(data, "zip_url", required=True),
        "dmg_url": _https_url(data, "dmg_url", required=platform == "macos"),
        "ed_signature": _required_string(data, "ed_signature"),
        "published_at": published_at,
        "changelog": [item.strip() for item in changelog if item.strip()],
        "mandatory": data.get("mandatory") is True,
        "source_sha": _digest(data, "source_sha", SHA40_RE, required=True),
        "zip_sha256": _digest(data, "zip_sha256", SHA256_RE, required=False),
        "dmg_sha256": _digest(data, "dmg_sha256", SHA256_RE, required=False),
        "qualification": cast(dict[str, Any], qualification),
    }
    return manifest


def register_release_manifest(data: dict[str, Any], *, firestore_client: Any = None) -> dict[str, Any]:
    """Create an immutable release manifest, allowing exact idempotent retries."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    manifest = normalize_release_manifest(data)
    ref = client.collection(MANIFESTS_COLLECTION).document(manifest["release_id"])
    snapshot = ref.get()
    if getattr(snapshot, "exists", False):
        existing_raw: object = snapshot.to_dict()
        existing_data = cast(dict[str, Any], existing_raw) if isinstance(existing_raw, dict) else {}
        existing = normalize_release_manifest(existing_data)
        if existing != manifest:
            raise ValueError("release_id already exists with different immutable metadata")
        return existing

    ref.create({**manifest, "created_at": datetime.now(timezone.utc)})
    return manifest


#: Pointer transitions differ only in which preconditions they enforce, so the
#: policy is data and :func:`_build_pointer` is the single mutation authority.
#: ``direction`` is the permitted build-number movement; every transition
#: requires the manifest's passed T2 qualification evidence.
TRANSITIONS: dict[str, dict[str, Any]] = {
    "promote": {"direction": "forward", "require_qualified": True, "require_current_release_id": False},
    "repoint": {"direction": "either", "require_qualified": True, "require_current_release_id": True},
}


def _build_pointer(
    current: dict[str, Any],
    manifest: dict[str, Any],
    *,
    transition: str,
    platform: str,
    channel: str,
    release_id: str,
    expected_generation: int | None,
    expected_current_release_id: str | None = None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the next channel pointer under the named transition policy.

    This is the only place a channel pointer is constructed. A repoint is an
    explicit compare-and-swap to an existing qualified manifest.
    """
    policy = TRANSITIONS[transition]

    if manifest["platform"] != platform:
        raise ValueError("release manifest platform does not match pointer platform")
    if policy["require_qualified"]:
        qualification = cast(dict[str, Any], manifest["qualification"])
        if qualification.get("passed") is not True or str(qualification.get("tier", "")).upper() != "T2":
            raise ValueError("release manifest is missing passed T2 qualification evidence")

    current_release_id = current.get("release_id")
    # An acknowledged pointer target is a safe exact retry. It still had to
    # resolve to this qualified immutable manifest above, but does not require
    # callers to guess the generation created by a lost response.
    if current_release_id == release_id:
        return current

    if policy["require_current_release_id"] or expected_current_release_id is not None:
        if current_release_id != expected_current_release_id:
            raise ValueError(
                f"current release mismatch: expected {expected_current_release_id}, "
                f"current {current_release_id or 'missing'}"
            )

    current_generation = _generation(current.get("generation", 0))
    if expected_generation is not None and expected_generation != current_generation:
        raise ValueError(f"generation mismatch: expected {expected_generation}, current {current_generation}")

    current_build_raw = current.get("build_number")
    if policy["direction"] == "forward":
        if current_build_raw is not None and manifest["build_number"] <= _generation(current_build_raw):
            raise ValueError(
                f"channel pointers are roll-forward only: current build {_generation(current_build_raw)}, "
                f"requested build {manifest['build_number']}"
            )

    pointer = {
        "platform": platform,
        "channel": channel,
        "release_id": release_id,
        "version": manifest["version"],
        "build_number": manifest["build_number"],
        "generation": current_generation + 1,
        "updated_at": updated_at or datetime.now(timezone.utc),
    }
    return pointer


@transactional
def _promote_channel_transaction(
    transaction: Any,
    pointer_ref: Any,
    manifest_ref: Any,
    *,
    transition: str,
    platform: str,
    channel: str,
    release_id: str,
    expected_generation: int | None,
    expected_current_release_id: str | None = None,
) -> dict[str, Any]:
    manifest_snapshot = manifest_ref.get(transaction=transaction)
    if not getattr(manifest_snapshot, "exists", False):
        raise ValueError("release manifest does not exist")
    raw_manifest: object = manifest_snapshot.to_dict()
    manifest_data = cast(dict[str, Any], raw_manifest) if isinstance(raw_manifest, dict) else {}
    manifest = normalize_release_manifest(manifest_data)

    pointer_snapshot = pointer_ref.get(transaction=transaction)
    current_raw: object = pointer_snapshot.to_dict() if getattr(pointer_snapshot, "exists", False) else {}
    current = cast(dict[str, Any], current_raw) if isinstance(current_raw, dict) else {}
    pointer = _build_pointer(
        current,
        manifest,
        transition=transition,
        platform=platform,
        channel=channel,
        release_id=release_id,
        expected_generation=expected_generation,
        expected_current_release_id=expected_current_release_id,
    )
    if pointer is not current:
        transaction.set(pointer_ref, pointer)
    return pointer


def promote_channel(
    platform: str,
    channel: str,
    release_id: str,
    *,
    expected_generation: int | None = None,
    expected_current_release_id: str | None = None,
    operation: str = "promote",
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Advance or explicitly repoint a channel pointer to a qualified manifest."""
    platform = platform.strip().lower()
    channel = channel.strip().lower()
    release_id = release_id.strip()
    if platform not in VALID_PLATFORMS:
        raise ValueError("invalid platform")
    if channel not in VALID_CHANNELS:
        raise ValueError("invalid channel")
    if not release_id:
        raise ValueError("release_id is required")
    if operation not in TRANSITIONS:
        raise ValueError("invalid pointer operation")
    if operation == "repoint" and (expected_current_release_id is None or expected_generation is None):
        raise ValueError("repoint requires expected_current_release_id and expected_generation")

    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_ref = client.collection(CHANNELS_COLLECTION).document(f"{platform}-{channel}")
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(release_id)
    transaction = client.transaction()
    return _promote_channel_transaction(
        transaction,
        pointer_ref,
        manifest_ref,
        transition=operation,
        platform=platform,
        channel=channel,
        release_id=release_id,
        expected_generation=expected_generation,
        expected_current_release_id=expected_current_release_id,
    )


def get_channel_release(platform: str, channel: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """Resolve one explicit channel pointer to its immutable manifest."""
    if platform not in VALID_PLATFORMS or channel not in VALID_CHANNELS:
        raise ValueError("invalid platform or channel")
    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_snapshot = client.collection(CHANNELS_COLLECTION).document(f"{platform}-{channel}").get()
    if not getattr(pointer_snapshot, "exists", False):
        return None
    raw_pointer: object = pointer_snapshot.to_dict()
    pointer = cast(dict[str, Any], raw_pointer) if isinstance(raw_pointer, dict) else {}
    release_id = pointer.get("release_id")
    if not isinstance(release_id, str) or not release_id:
        raise ValueError("channel pointer is missing release_id")

    manifest_snapshot = client.collection(MANIFESTS_COLLECTION).document(release_id).get()
    if not getattr(manifest_snapshot, "exists", False):
        raise ValueError("channel pointer references a missing manifest")
    raw_manifest: object = manifest_snapshot.to_dict()
    manifest_data = cast(dict[str, Any], raw_manifest) if isinstance(raw_manifest, dict) else {}
    manifest = normalize_release_manifest(manifest_data)
    if manifest["platform"] != platform:
        raise ValueError("channel pointer references another platform")
    return {
        "pointer": {
            "platform": platform,
            "channel": channel,
            "release_id": release_id,
            "version": pointer.get("version"),
            "build_number": pointer.get("build_number"),
            "generation": _generation(pointer.get("generation", 0)),
            "updated_at": pointer.get("updated_at"),
        },
        "manifest": manifest,
    }
