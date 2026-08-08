"""Atomic incident-only mutations for the hard-coded macOS Beta pointer."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, cast

from database.store import get_document_store
from database.desktop_update_channels import (
    BETA_ADMISSION_COLLECTION,
    BETA_ADMISSION_DOCUMENT,
    CHANNELS_COLLECTION,
    MANIFESTS_COLLECTION,
    build_channel_pointer,
    normalize_release_manifest,
    parse_pointer_generation,
    validate_beta_admission_control,
)

BETA_BREAKGLASS_AUDITS_COLLECTION = "desktop_beta_breakglass_audits"
_INCIDENT_URL = re.compile(r"^https://github\.com/BasedHardware/omi/(?:issues|discussions)/[1-9][0-9]*(?:[/?#].*)?$")
_REQUEST_ID = re.compile(r"^https://github\.com/BasedHardware/omi/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*$")


def _store():
    return get_document_store()


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} is required")
    return value


def _request(request: dict[str, Any], operation: str) -> dict[str, Any]:
    current = _required(request.get("current_release_id"), "current_release_id")
    target = _required(request.get("target_release_id"), "target_release_id")
    actor = _required(request.get("actor"), "actor")
    reason = _required(request.get("reason"), "reason")
    incident_url = _required(request.get("incident_url"), "incident_url")
    request_id = _required(request.get("request_id"), "request_id")
    generation = request.get("expected_generation")
    if not _INCIDENT_URL.fullmatch(incident_url):
        raise ValueError("incident_url must identify an Omi GitHub incident")
    if not _REQUEST_ID.fullmatch(request_id):
        raise ValueError("request_id must identify this GitHub Actions attempt")
    if type(generation) is not int or generation < 0:
        raise ValueError("expected_generation is invalid")
    normal_path = request.get("normal_path_unavailable")
    if operation == "rollout":
        normal_path = _required(normal_path, "normal_path_unavailable")
    return {
        "current_release_id": current,
        "target_release_id": target,
        "expected_generation": generation,
        "actor": actor,
        "reason": reason,
        "incident_url": incident_url,
        "request_id": request_id,
        "normal_path_unavailable": normal_path,
    }


def _manifest(snapshot: Any, message: str) -> dict[str, Any]:
    if not getattr(snapshot, "exists", False):
        raise ValueError(message)
    raw = snapshot.to_dict()
    return normalize_release_manifest(cast(dict[str, Any], raw) if isinstance(raw, dict) else {})


def _digest(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _commit(
    tx: Any,
    control_path: str,
    pointer_path: str,
    audit_path: str,
    target_path: str,
    request: dict[str, Any],
    operation: str,
    emergency_manifest: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    control_snapshot = tx.get(control_path)
    pointer_snapshot = tx.get(pointer_path)
    audit_snapshot = tx.get(audit_path)
    target_snapshot = tx.get(target_path)
    if audit_snapshot.exists:
        raise ValueError("request was already used")

    control = validate_beta_admission_control(
        control_snapshot.to_dict() if control_snapshot.exists else {}
    )
    raw_pointer = pointer_snapshot.to_dict() if pointer_snapshot.exists else {}
    current = cast(dict[str, Any], raw_pointer) if isinstance(raw_pointer, dict) else {}
    if current.get("release_id") != request["current_release_id"]:
        raise ValueError("current release mismatch")
    if parse_pointer_generation(current.get("generation", 0)) != request["expected_generation"]:
        raise ValueError("generation mismatch")

    target_exists = target_snapshot.exists
    if operation == "rollback":
        target = _manifest(target_snapshot, "rollback target manifest does not exist")
        if target["qualification_tier"] != "T2" or target["qualification_passed"] is not True:
            raise ValueError("rollback target must be retained and T2-qualified")
    else:
        if emergency_manifest is None:
            raise ValueError("emergency manifest is required")
        target = emergency_manifest
        if target_exists and _manifest(target_snapshot, "invalid target manifest") != target:
            raise ValueError("emergency target immutable manifest collision")
        if target["qualification_tier"] != "emergency" or target["qualification_passed"] is not False:
            raise ValueError("emergency target must preserve failed qualification truth")
        if target["build_number"] <= parse_pointer_generation(current.get("build_number")):
            raise ValueError("emergency target must have a higher build")

    pointer = build_channel_pointer(
        current,
        target,
        transition="breakglass",
        platform="macos",
        channel="beta",
        release_id=request["target_release_id"],
        expected_current_release_id=request["current_release_id"],
        expected_generation=request["expected_generation"],
    )
    audit = {
        "schema_version": 1,
        "operation": operation,
        "platform": "macos",
        "channel": "beta",
        **request,
        "target_manifest_sha256": _digest(target),
        "resulting_generation": pointer["generation"],
        "created_at": now.isoformat().replace("+00:00", "Z"),
    }
    paused = {
        **control,
        "promotion_enabled": False,
        "control_generation": control["control_generation"] + 1,
        "admission_updated_at": now,
    }
    tx.set(audit_path, audit)
    if operation == "rollout" and not target_exists:
        tx.set(target_path, target)
    tx.set(control_path, paused)
    tx.set(pointer_path, pointer)
    return {"pointer": pointer, "audit": audit, "admission": paused}


def _execute(
    operation: str,
    request: dict[str, Any],
    *,
    emergency_manifest: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    validated = _request(request, operation)
    manifest = normalize_release_manifest(emergency_manifest) if emergency_manifest is not None else None
    if manifest is not None and manifest["release_id"] != validated["target_release_id"]:
        raise ValueError("emergency target identity mismatch")
    audit_id = hashlib.sha256(validated["request_id"].encode()).hexdigest()
    control_path = f"{BETA_ADMISSION_COLLECTION}/{BETA_ADMISSION_DOCUMENT}"
    pointer_path = f"{CHANNELS_COLLECTION}/macos-beta"
    audit_path = f"{BETA_BREAKGLASS_AUDITS_COLLECTION}/{audit_id}"
    target_path = f"{MANIFESTS_COLLECTION}/{validated['target_release_id']}"
    committed_now = now or datetime.now(timezone.utc)
    return _store().run_transaction(
        lambda tx: _commit(
            tx,
            control_path,
            pointer_path,
            audit_path,
            target_path,
            validated,
            operation,
            manifest,
            committed_now,
        )
    )


def rollback_beta(request: dict[str, Any], *, now: datetime | None = None):
    return _execute("rollback", request, now=now)


def emergency_rollout_beta(request: dict[str, Any], manifest: dict[str, Any], *, now: datetime | None = None):
    return _execute("rollout", request, emergency_manifest=manifest, now=now)
