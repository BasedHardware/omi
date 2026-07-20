from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

from google.cloud.firestore import transactional

from database._client import get_firestore_client

CHANNELS_COLLECTION = "desktop_update_channels"
MANIFESTS_COLLECTION = "desktop_release_manifests"
ROLLBACK_AUDITS_COLLECTION = "desktop_update_channel_rollback_audits"
EMERGENCY_PROMOTION_AUDITS_COLLECTION = "desktop_update_channel_emergency_promotion_audits"
VALID_CHANNELS = frozenset({"stable", "beta"})
VALID_PLATFORMS = frozenset({"macos", "windows", "linux"})
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")


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


def _emergency_expiry(value: str, *, now: datetime) -> datetime:
    """Parse the deliberately short-lived break-glass authorization."""
    try:
        expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("expires_at must be an ISO-8601 timestamp") from exc
    if expires_at.tzinfo is None:
        raise ValueError("expires_at must include a timezone")
    expires_at = expires_at.astimezone(timezone.utc)
    if expires_at <= now:
        raise ValueError("emergency promotion authorization has expired")
    if expires_at - now > timedelta(hours=4):
        raise ValueError("emergency promotion authorization may not exceed four hours")
    return expires_at


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


def _build_channel_pointer(
    current: dict[str, Any],
    manifest: dict[str, Any],
    *,
    platform: str,
    channel: str,
    release_id: str,
    expected_generation: int | None,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    if manifest["platform"] != platform:
        raise ValueError("release manifest platform does not match pointer platform")
    qualification = cast(dict[str, Any], manifest["qualification"])
    if qualification.get("passed") is not True or str(qualification.get("tier", "")).upper() != "T2":
        raise ValueError("release manifest is missing passed T2 qualification evidence")

    current_generation = _generation(current.get("generation", 0))
    if expected_generation is not None and expected_generation != current_generation:
        raise ValueError(f"generation mismatch: expected {expected_generation}, current {current_generation}")
    if current.get("release_id") == release_id:
        return current
    current_build_raw = current.get("build_number")
    if current_build_raw is not None:
        current_build = _generation(current_build_raw)
        if manifest["build_number"] <= current_build:
            raise ValueError(
                f"channel pointers are roll-forward only: current build {current_build}, "
                f"requested build {manifest['build_number']}"
            )

    return {
        "platform": platform,
        "channel": channel,
        "release_id": release_id,
        "version": manifest["version"],
        "build_number": manifest["build_number"],
        "generation": current_generation + 1,
        "updated_at": updated_at or datetime.now(timezone.utc),
    }


def _build_beta_rollback_pointer(
    current: dict[str, Any],
    manifest: dict[str, Any],
    *,
    release_id: str,
    expected_current_release_id: str,
    expected_generation: int,
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the sole permitted non-monotonic pointer transition: macOS beta rollback."""
    if manifest["platform"] != "macos":
        raise ValueError("rollback target must be a macos release manifest")
    qualification = cast(dict[str, Any], manifest["qualification"])
    if qualification.get("passed") is not True or str(qualification.get("tier", "")).upper() != "T2":
        raise ValueError("rollback target is missing passed T2 qualification evidence")

    current_release_id = current.get("release_id")
    if current_release_id != expected_current_release_id:
        raise ValueError(
            f"current release mismatch: expected {expected_current_release_id}, current {current_release_id or 'missing'}"
        )
    current_generation = _generation(current.get("generation", 0))
    if expected_generation != current_generation:
        raise ValueError(f"generation mismatch: expected {expected_generation}, current {current_generation}")

    current_build = _generation(current.get("build_number"))
    if release_id == current_release_id or manifest["build_number"] >= current_build:
        raise ValueError("rollback target must be an earlier qualified beta release")

    return {
        "platform": "macos",
        "channel": "beta",
        "release_id": release_id,
        "version": manifest["version"],
        "build_number": manifest["build_number"],
        "generation": current_generation + 1,
        "updated_at": updated_at or datetime.now(timezone.utc),
    }


@transactional
def _promote_channel_transaction(
    transaction: Any,
    pointer_ref: Any,
    manifest_ref: Any,
    *,
    platform: str,
    channel: str,
    release_id: str,
    expected_generation: int | None,
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
    pointer = _build_channel_pointer(
        current,
        manifest,
        platform=platform,
        channel=channel,
        release_id=release_id,
        expected_generation=expected_generation,
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
    firestore_client: Any = None,
) -> dict[str, Any]:
    platform = platform.strip().lower()
    channel = channel.strip().lower()
    release_id = release_id.strip()
    if platform not in VALID_PLATFORMS:
        raise ValueError("invalid platform")
    if channel not in VALID_CHANNELS:
        raise ValueError("invalid channel")
    if not release_id:
        raise ValueError("release_id is required")

    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_ref = client.collection(CHANNELS_COLLECTION).document(f"{platform}-{channel}")
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(release_id)
    transaction = client.transaction()
    return _promote_channel_transaction(
        transaction,
        pointer_ref,
        manifest_ref,
        platform=platform,
        channel=channel,
        release_id=release_id,
        expected_generation=expected_generation,
    )


@transactional
def _rollback_macos_beta_transaction(
    transaction: Any,
    pointer_ref: Any,
    manifest_ref: Any,
    audit_ref: Any,
    *,
    release_id: str,
    expected_current_release_id: str,
    expected_generation: int,
    audit_id: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    manifest_snapshot = manifest_ref.get(transaction=transaction)
    if not getattr(manifest_snapshot, "exists", False):
        raise ValueError("rollback target release manifest does not exist")
    raw_manifest: object = manifest_snapshot.to_dict()
    manifest_data = cast(dict[str, Any], raw_manifest) if isinstance(raw_manifest, dict) else {}
    manifest = normalize_release_manifest(manifest_data)

    pointer_snapshot = pointer_ref.get(transaction=transaction)
    if not getattr(pointer_snapshot, "exists", False):
        raise ValueError("current macos beta pointer does not exist")
    current_raw: object = pointer_snapshot.to_dict()
    current = cast(dict[str, Any], current_raw) if isinstance(current_raw, dict) else {}
    pointer = _build_beta_rollback_pointer(
        current,
        manifest,
        release_id=release_id,
        expected_current_release_id=expected_current_release_id,
        expected_generation=expected_generation,
        updated_at=occurred_at,
    )
    audit = {
        "audit_id": audit_id,
        "operation": "macos_beta_rollback",
        "platform": "macos",
        "channel": "beta",
        "previous_release_id": expected_current_release_id,
        "previous_generation": expected_generation,
        "target_release_id": release_id,
        "generation": pointer["generation"],
        "occurred_at": occurred_at,
    }
    # create() provides an immutable, append-only audit record. All reads above
    # occur before this first transactional write.
    transaction.create(audit_ref, audit)
    transaction.set(pointer_ref, pointer)
    return {"pointer": pointer, "audit": audit}


def rollback_macos_beta_channel(
    release_id: str,
    *,
    expected_current_release_id: str,
    expected_generation: int,
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Atomically roll macOS beta back to an earlier, qualified registered release only."""
    release_id = release_id.strip()
    expected_current_release_id = expected_current_release_id.strip()
    if not release_id:
        raise ValueError("release_id is required")
    if not expected_current_release_id:
        raise ValueError("expected_current_release_id is required")
    if expected_generation < 0:
        raise ValueError("expected_generation must be a non-negative integer")

    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_ref = client.collection(CHANNELS_COLLECTION).document("macos-beta")
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(release_id)
    audit_id = uuid4().hex
    audit_ref = client.collection(ROLLBACK_AUDITS_COLLECTION).document(audit_id)
    return _rollback_macos_beta_transaction(
        client.transaction(),
        pointer_ref,
        manifest_ref,
        audit_ref,
        release_id=release_id,
        expected_current_release_id=expected_current_release_id,
        expected_generation=expected_generation,
        audit_id=audit_id,
        occurred_at=datetime.now(timezone.utc),
    )


def _build_emergency_macos_beta_pointer(
    current: dict[str, Any],
    manifest: dict[str, Any],
    *,
    release_id: str,
    source_sha: str,
    expected_current_release_id: str,
    expected_generation: int,
    evidence: dict[str, str],
    updated_at: datetime,
) -> dict[str, Any]:
    """Build the sole break-glass forward transition; it is never reusable for Stable."""
    if manifest["platform"] != "macos":
        raise ValueError("emergency promotion target must be a macos release manifest")
    if manifest["source_sha"] != source_sha:
        raise ValueError("emergency promotion source SHA does not match the immutable manifest")
    if not manifest.get("zip_sha256") or not manifest.get("dmg_sha256"):
        raise ValueError("emergency promotion target is missing immutable ZIP/DMG digests")
    if evidence["zip_sha256"] != manifest["zip_sha256"] or evidence["dmg_sha256"] != manifest["dmg_sha256"]:
        raise ValueError("emergency promotion artifact evidence does not match the immutable manifest")

    current_release_id = current.get("release_id")
    if current_release_id != expected_current_release_id:
        raise ValueError(
            f"current release mismatch: expected {expected_current_release_id}, current {current_release_id or 'missing'}"
        )
    current_generation = _generation(current.get("generation", 0))
    if expected_generation != current_generation:
        raise ValueError(f"generation mismatch: expected {expected_generation}, current {current_generation}")
    current_build = _generation(current.get("build_number"))
    if release_id == current_release_id or manifest["build_number"] <= current_build:
        raise ValueError("emergency promotion target must be a newer macOS beta release")

    return {
        "platform": "macos",
        "channel": "beta",
        "release_id": release_id,
        "version": manifest["version"],
        "build_number": manifest["build_number"],
        "generation": current_generation + 1,
        "updated_at": updated_at,
    }


def _require_bound_emergency_manifest_decision(
    manifest: dict[str, Any],
    *,
    release_id: str,
    source_sha: str,
    incident_id: str,
    reason: str,
    operator: str,
    expires_at: datetime,
    approvers: list[str],
    evidence: dict[str, str],
    occurred_at: datetime,
) -> None:
    """Require the server request to match the registered break-glass decision exactly."""
    qualification = cast(dict[str, Any], manifest["qualification"])
    if qualification.get("passed") is not False or qualification.get("tier") != "emergency":
        raise ValueError("release manifest is missing an explicit emergency beta decision")
    decision = qualification.get("emergency_evidence")
    if not isinstance(decision, dict) or decision.get("emergencyPromotion") is not True:
        raise ValueError("release manifest emergency decision is incomplete")
    if decision.get("release_tag") != release_id or str(decision.get("source_sha", "")).lower() != source_sha:
        raise ValueError("emergency decision does not bind this release tag and source SHA")
    if str(decision.get("incident_id")) != incident_id or decision.get("reason") != reason:
        raise ValueError("emergency decision does not match the incident and reason")
    if str(decision.get("operator", "")).lstrip("@") != operator:
        raise ValueError("emergency decision does not match the operator")
    decision_expiry = _emergency_expiry(_required_string(cast(dict[str, Any], decision), "expires_at"), now=occurred_at)
    if decision_expiry != expires_at:
        raise ValueError("emergency decision does not match the authorization expiry")
    decision_approvers = decision.get("approvers")
    if not isinstance(decision_approvers, list) or decision_approvers != approvers:
        raise ValueError("emergency decision does not match the approvers")
    decision_evidence = decision.get("evidence")
    if not isinstance(decision_evidence, dict) or decision_evidence != evidence:
        raise ValueError("emergency decision evidence does not match the immutable manifest")


@transactional
def _emergency_promote_macos_beta_transaction(
    transaction: Any,
    pointer_ref: Any,
    manifest_ref: Any,
    audit_ref: Any,
    *,
    release_id: str,
    source_sha: str,
    expected_current_release_id: str,
    expected_generation: int,
    incident_id: str,
    reason: str,
    operator: str,
    expires_at: datetime,
    approvers: list[str],
    evidence: dict[str, str],
    audit_id: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    manifest_snapshot = manifest_ref.get(transaction=transaction)
    if not getattr(manifest_snapshot, "exists", False):
        raise ValueError("emergency promotion target release manifest does not exist")
    raw_manifest: object = manifest_snapshot.to_dict()
    manifest_data = cast(dict[str, Any], raw_manifest) if isinstance(raw_manifest, dict) else {}
    manifest = normalize_release_manifest(manifest_data)
    _require_bound_emergency_manifest_decision(
        manifest,
        release_id=release_id,
        source_sha=source_sha,
        incident_id=incident_id,
        reason=reason,
        operator=operator,
        expires_at=expires_at,
        approvers=approvers,
        evidence=evidence,
        occurred_at=occurred_at,
    )

    pointer_snapshot = pointer_ref.get(transaction=transaction)
    if not getattr(pointer_snapshot, "exists", False):
        raise ValueError("current macos beta pointer does not exist")
    current_raw: object = pointer_snapshot.to_dict()
    current = cast(dict[str, Any], current_raw) if isinstance(current_raw, dict) else {}
    pointer = _build_emergency_macos_beta_pointer(
        current,
        manifest,
        release_id=release_id,
        source_sha=source_sha,
        expected_current_release_id=expected_current_release_id,
        expected_generation=expected_generation,
        evidence=evidence,
        updated_at=occurred_at,
    )
    audit = {
        "audit_id": audit_id,
        "operation": "macos_beta_emergency_forward_promotion",
        "platform": "macos",
        "channel": "beta",
        "emergencyPromotion": True,
        "previous_release_id": expected_current_release_id,
        "previous_generation": expected_generation,
        "target_release_id": release_id,
        "source_sha": source_sha,
        "generation": pointer["generation"],
        "incident_id": incident_id,
        "reason": reason,
        "operator": operator,
        "expires_at": expires_at,
        "approvers": approvers,
        "evidence": evidence,
        "occurred_at": occurred_at,
    }
    # The create-only audit makes this exception append-only; all reads are
    # intentionally complete before either transactional mutation occurs.
    transaction.create(audit_ref, audit)
    transaction.set(pointer_ref, pointer)
    return {"pointer": pointer, "audit": audit}


def emergency_promote_macos_beta_channel(
    release_id: str,
    *,
    source_sha: str,
    expected_current_release_id: str,
    expected_generation: int,
    incident_id: str,
    reason: str,
    operator: str,
    expires_at: str,
    approvers: list[str],
    evidence: dict[str, str],
    firestore_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Emergency-only forward promotion of a newer immutable macOS beta candidate."""
    release_id = release_id.strip()
    source_sha = source_sha.strip().lower()
    expected_current_release_id = expected_current_release_id.strip()
    incident_id = incident_id.strip()
    reason = reason.strip()
    operator = operator.strip().lstrip("@")
    occurred_at = now or datetime.now(timezone.utc)
    if not release_id or not expected_current_release_id or not incident_id or not reason or not operator:
        raise ValueError("release_id, expected_current_release_id, incident_id, reason, and operator are required")
    if not GITHUB_LOGIN_RE.fullmatch(operator):
        raise ValueError("operator must be a GitHub login")
    if not SHA40_RE.fullmatch(source_sha):
        raise ValueError("source_sha has an invalid digest")
    if expected_generation < 0:
        raise ValueError("expected_generation must be a non-negative integer")
    normalized_approvers = [approver.strip().lstrip("@") for approver in approvers if approver.strip()]
    if len(normalized_approvers) != 2 or len({approver.lower() for approver in normalized_approvers}) != 2:
        raise ValueError("emergency promotion requires exactly two distinct approvers")
    required_evidence = {
        "signed_smoke_url",
        "signed_smoke_sha256",
        "behavioral_url",
        "behavioral_sha256",
        "source_gate_url",
        "zip_sha256",
        "dmg_sha256",
    }
    if set(evidence) != required_evidence:
        raise ValueError("emergency promotion evidence is incomplete")
    normalized_evidence: dict[str, str] = {}
    for key, value in evidence.items():
        if not value.strip():
            raise ValueError(f"emergency promotion evidence {key} is required")
        normalized_evidence[key] = value.strip()
    for key in ("signed_smoke_url", "behavioral_url", "source_gate_url"):
        _https_url(normalized_evidence, key, required=True)
    for key in ("signed_smoke_sha256", "behavioral_sha256", "zip_sha256", "dmg_sha256"):
        normalized_evidence[key] = _digest(normalized_evidence, key, SHA256_RE, required=True) or ""
    expiry = _emergency_expiry(expires_at, now=occurred_at)

    client = firestore_client if firestore_client is not None else get_firestore_client()
    pointer_ref = client.collection(CHANNELS_COLLECTION).document("macos-beta")
    manifest_ref = client.collection(MANIFESTS_COLLECTION).document(release_id)
    audit_id = uuid4().hex
    audit_ref = client.collection(EMERGENCY_PROMOTION_AUDITS_COLLECTION).document(audit_id)
    return _emergency_promote_macos_beta_transaction(
        client.transaction(),
        pointer_ref,
        manifest_ref,
        audit_ref,
        release_id=release_id,
        source_sha=source_sha,
        expected_current_release_id=expected_current_release_id,
        expected_generation=expected_generation,
        incident_id=incident_id,
        reason=reason,
        operator=operator,
        expires_at=expiry,
        approvers=normalized_approvers,
        evidence=normalized_evidence,
        audit_id=audit_id,
        occurred_at=occurred_at,
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
