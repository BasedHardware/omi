from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from google.cloud.firestore import transactional

from database._client import get_firestore_client
from desktop_release_manifest import ManifestError, validate_manifest

CHANNELS_COLLECTION = "desktop_update_channels"
MANIFESTS_COLLECTION = "desktop_release_manifests"
VALID_CHANNELS = frozenset({"stable", "beta"})


def _generation(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("pointer generation must be a non-negative integer")


def normalize_release_manifest(data: dict[str, Any]) -> dict[str, Any]:
    """Use the one v1 executable contract for every persisted manifest."""
    try:
        return validate_manifest(data)
    except ManifestError as exc:
        raise ValueError(str(exc)) from exc


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

    # ``created_at`` is part of the canonical manifest and its RFC3339 bytes
    # participate in the immutable digest. Firestore must retain it unchanged.
    ref.create(manifest)
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
        if manifest["qualification_passed"] is not True or manifest["qualification_tier"] != "T2":
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
    if platform != "macos":
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


@transactional
def _admit_qualified_beta_transaction(
    transaction: Any, pointer_ref: Any, manifest_ref: Any, manifest: dict[str, Any]
) -> dict[str, Any]:
    """Atomically retain one canonical manifest and advance only macOS Beta."""
    manifest_snapshot = manifest_ref.get(transaction=transaction)
    manifest_exists = getattr(manifest_snapshot, "exists", False)
    if manifest_exists:
        raw_existing: object = manifest_snapshot.to_dict()
        existing = normalize_release_manifest(
            cast(dict[str, Any], raw_existing) if isinstance(raw_existing, dict) else {}
        )
        if existing != manifest:
            raise ValueError("release_id already exists with different immutable metadata")
    pointer_snapshot = pointer_ref.get(transaction=transaction)
    raw_pointer: object = pointer_snapshot.to_dict() if getattr(pointer_snapshot, "exists", False) else {}
    current = cast(dict[str, Any], raw_pointer) if isinstance(raw_pointer, dict) else {}
    pointer = _build_pointer(
        current,
        manifest,
        transition="promote",
        platform="macos",
        channel="beta",
        release_id=manifest["release_id"],
        expected_generation=None,
    )
    if not manifest_exists:
        transaction.create(manifest_ref, manifest)
    if pointer is not current:
        transaction.set(pointer_ref, pointer)
    return {"manifest": manifest, "pointer": pointer, "idempotent": manifest_exists and pointer is current}


def admit_qualified_beta_manifest(data: dict[str, Any], *, firestore_client: Any = None) -> dict[str, Any]:
    """Commit the narrow server-owned Beta transaction after admission succeeds."""
    manifest = normalize_release_manifest(data)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_ref = client.collection(CHANNELS_COLLECTION).document("macos-beta")
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(manifest["release_id"])
    return _admit_qualified_beta_transaction(client.transaction(), pointer_ref, manifest_ref, manifest)


def get_channel_release(platform: str, channel: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """Resolve one explicit channel pointer to its immutable manifest."""
    if platform != "macos" or channel not in VALID_CHANNELS:
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


def get_release_manifest(release_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """Read one retained immutable manifest without consulting release metadata."""
    release_id = release_id.strip()
    if not release_id:
        raise ValueError("release_id is required")
    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = client.collection(MANIFESTS_COLLECTION).document(release_id).get()
    if not getattr(snapshot, "exists", False):
        return None
    raw: object = snapshot.to_dict()
    data = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    return normalize_release_manifest(data)
