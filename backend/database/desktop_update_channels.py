from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, cast

from google.cloud.firestore import transactional

from database._client import get_firestore_client
from desktop_release_manifest import ManifestError, validate_manifest

CHANNELS_COLLECTION = "desktop_update_channels"
MANIFESTS_COLLECTION = "desktop_release_manifests"
VALID_CHANNELS = frozenset({"stable", "beta"})
BETA_ADMISSION_COLLECTION = "desktop_beta_admission"
BETA_ADMISSION_DOCUMENT = "control"
_BETA_TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)\+(?P<build>[1-9][0-9]*)-macos$")
_BETA_ADMISSION_FIELDS = frozenset(
    {
        "schema_version",
        "promotion_enabled",
        "latest_reserved_tag",
        "latest_reserved_build_number",
        "control_generation",
        "latest_reserved_at",
        "admission_updated_at",
    }
)


def _generation(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValueError("pointer generation must be a non-negative integer")


def _canonical_beta_tag(tag: object) -> tuple[str, tuple[int, int, int], int]:
    if not isinstance(tag, str):
        raise ValueError("candidate tag must be a canonical macOS tag")
    match = _BETA_TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError("candidate tag must be a canonical macOS tag")
    raw_version = match.group("version").split(".")
    version = tuple(int(part) for part in (*raw_version, "0")[:3])
    return tag, cast(tuple[int, int, int], version), int(match.group("build"))


def _timestamp(value: object) -> datetime:
    # Firestore returns native datetime values (including its datetime subclass).
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("beta admission control timestamps are invalid")
    return value


def _validate_beta_admission_control(data: object) -> dict[str, Any]:
    """Decode the sole Beta admission document exactly; unknown schemas fail closed."""
    if not isinstance(data, dict) or frozenset(data.keys()) != _BETA_ADMISSION_FIELDS:
        raise ValueError("beta admission control schema is invalid")
    schema_version = data.get("schema_version")
    enabled = data.get("promotion_enabled")
    generation = data.get("control_generation")
    tag = data.get("latest_reserved_tag")
    build = data.get("latest_reserved_build_number")
    if isinstance(schema_version, bool) or schema_version != 1:
        raise ValueError("beta admission control schema is invalid")
    if not isinstance(enabled, bool):
        raise ValueError("beta admission control schema is invalid")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
        raise ValueError("beta admission control schema is invalid")
    if tag is None:
        if build is not None or data.get("latest_reserved_at") is not None:
            raise ValueError("beta admission control schema is invalid")
        _timestamp(data.get("admission_updated_at"))
    else:
        _, _, parsed_build = _canonical_beta_tag(tag)
        if not isinstance(build, int) or isinstance(build, bool) or build <= 0 or build != parsed_build:
            raise ValueError("beta admission control schema is invalid")
        _timestamp(data.get("latest_reserved_at"))
        _timestamp(data.get("admission_updated_at"))
    return cast(dict[str, Any], data)


def _beta_admission_ref(client: Any) -> Any:
    return client.collection(BETA_ADMISSION_COLLECTION).document(BETA_ADMISSION_DOCUMENT)


def _control_now() -> datetime:
    return datetime.now(timezone.utc)


@transactional
def _reserve_beta_candidate_transaction(transaction: Any, control_ref: Any, tag: str) -> dict[str, Any]:
    snapshot = control_ref.get(transaction=transaction)
    target_tag, target_version, target_build = _canonical_beta_tag(tag)
    now = _control_now()
    if not getattr(snapshot, "exists", False):
        control = {
            "schema_version": 1,
            "promotion_enabled": False,
            "latest_reserved_tag": target_tag,
            "latest_reserved_build_number": target_build,
            "control_generation": 1,
            "latest_reserved_at": now,
            "admission_updated_at": now,
        }
        transaction.set(control_ref, control)
        return control
    raw: object = snapshot.to_dict()
    current = _validate_beta_admission_control(raw)
    current_tag = current["latest_reserved_tag"]
    if current_tag == target_tag:
        return current
    if current_tag is not None:
        _, current_version, current_build = _canonical_beta_tag(current_tag)
        if target_build <= current_build or target_version < current_version:
            raise ValueError("candidate reservation must roll forward")
    control = {
        **current,
        "latest_reserved_tag": target_tag,
        "latest_reserved_build_number": target_build,
        "control_generation": current["control_generation"] + 1,
        "latest_reserved_at": now,
        "admission_updated_at": now,
    }
    transaction.set(control_ref, control)
    return control


def reserve_beta_candidate(tag: str, *, firestore_client: Any = None) -> dict[str, Any]:
    """Reserve one higher immutable candidate without enabling its promotion."""
    _canonical_beta_tag(tag)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _reserve_beta_candidate_transaction(client.transaction(), _beta_admission_ref(client), tag)


@transactional
def _set_beta_admission_enabled_transaction(transaction: Any, control_ref: Any, enabled: bool) -> dict[str, Any]:
    snapshot = control_ref.get(transaction=transaction)
    if not getattr(snapshot, "exists", False):
        if enabled:
            raise ValueError("beta admission cannot resume without a reservation")
        # An explicit initial pause is a state transition, even before a candidate.
        now = _control_now()
        control = {
            "schema_version": 1,
            "promotion_enabled": False,
            "latest_reserved_tag": None,
            "latest_reserved_build_number": None,
            "control_generation": 1,
            "latest_reserved_at": None,
            "admission_updated_at": now,
        }
        transaction.set(control_ref, control)
        return control
    raw: object = snapshot.to_dict()
    current = _validate_beta_admission_control(raw)
    if current["promotion_enabled"] is enabled:
        return current
    if enabled and current["latest_reserved_tag"] is None:
        raise ValueError("beta admission cannot resume without a reservation")
    control = {
        **current,
        "promotion_enabled": enabled,
        "control_generation": current["control_generation"] + 1,
        "admission_updated_at": _control_now(),
    }
    transaction.set(control_ref, control)
    return control


def set_beta_admission_enabled(enabled: bool, *, firestore_client: Any = None) -> dict[str, Any]:
    if type(enabled) is not bool:
        raise ValueError("beta admission enabled must be a boolean")
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return _set_beta_admission_enabled_transaction(client.transaction(), _beta_admission_ref(client), enabled)


def capture_beta_admission(tag: str, *, firestore_client: Any = None) -> dict[str, Any]:
    """Capture the server-owned generation before untrusted, expensive GitHub reads."""
    tag, _, build = _canonical_beta_tag(tag)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = _beta_admission_ref(client).get()
    if not getattr(snapshot, "exists", False):
        raise ValueError("beta admission control is unavailable")
    raw: object = snapshot.to_dict()
    control = _validate_beta_admission_control(raw)
    if not control["promotion_enabled"]:
        raise ValueError("beta admission is disabled")
    if control["latest_reserved_tag"] != tag or control["latest_reserved_build_number"] != build:
        raise ValueError("beta admission reservation does not match candidate")
    return control


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
    # Private to desktop_beta_breakglass.  The public generic promotion API
    # rejects it, so an emergency manifest can never become Stable or bypass
    # the dedicated audit/admission-pause transaction.
    "breakglass": {"direction": "either", "require_qualified": False, "require_current_release_id": True},
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
    if channel != "stable":
        raise ValueError("generic channel promotion is stable-only")
    if channel not in VALID_CHANNELS:
        raise ValueError("invalid channel")
    if not release_id:
        raise ValueError("release_id is required")
    if operation not in {"promote", "repoint"}:
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
    transaction: Any,
    control_ref: Any,
    pointer_ref: Any,
    manifest_ref: Any,
    manifest: dict[str, Any],
    control_generation: int,
) -> dict[str, Any]:
    """Atomically retain one canonical manifest and advance only macOS Beta."""
    # Firestore requires every read before the first write. Read the control
    # document first so a reservation/pause committed during evidence validation
    # necessarily conflicts or fails this generation check before any mutation.
    control_snapshot = control_ref.get(transaction=transaction)
    if not getattr(control_snapshot, "exists", False):
        raise ValueError("beta admission control is unavailable")
    control_raw: object = control_snapshot.to_dict()
    control = _validate_beta_admission_control(control_raw)
    tag, _, build = _canonical_beta_tag(manifest["release_id"])
    if not control["promotion_enabled"]:
        raise ValueError("beta admission is disabled")
    if control["control_generation"] != control_generation:
        raise ValueError("beta admission generation changed")
    if control["latest_reserved_tag"] != tag or control["latest_reserved_build_number"] != build:
        raise ValueError("beta admission reservation does not match candidate")
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


def admit_qualified_beta_manifest(
    data: dict[str, Any], *, control_generation: int, firestore_client: Any = None
) -> dict[str, Any]:
    """Commit the narrow server-owned Beta transaction after admission succeeds."""
    manifest = normalize_release_manifest(data)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    if type(control_generation) is not int or control_generation < 0:
        raise ValueError("beta admission generation is invalid")
    control_ref = _beta_admission_ref(client)
    pointer_ref = client.collection(CHANNELS_COLLECTION).document("macos-beta")
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(manifest["release_id"])
    return _admit_qualified_beta_transaction(
        client.transaction(), control_ref, pointer_ref, manifest_ref, manifest, control_generation
    )


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


# Public reuse surface for the dedicated Beta break-glass transaction. Keeping
# these aliases here preserves one pointer/admission implementation without
# requiring another module to import private names or duplicate safety logic.
parse_pointer_generation = _generation
validate_beta_admission_control = _validate_beta_admission_control
build_channel_pointer = _build_pointer
