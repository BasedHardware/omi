"""Shared lifecycle primitives for the Agent VM fleet reconciler.

The reconciler is deliberately declarative.  A release is identified by an
immutable image digest and an immutable startup artifact; Firestore owns the
account/deletion fence and short-lived leases; GCE is only the provider state
being converged.  Request-path code uses the same lease and admission helpers
as the scheduled job, so a repair cannot silently replace a newer owner.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import shlex
import time
from dataclasses import dataclass
from typing import Any, Mapping

import google.auth
import google.auth.transport.requests
import httpx
from google.cloud.firestore import DELETE_FIELD, transactional

from database._client import get_firestore_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

RECONCILER_SCHEMA_VERSION = 1
DEFAULT_ZONE = "us-central1-a"
LEASE_TTL_SECONDS = 900
LEASE_HEARTBEAT_SECONDS = 60
SESSION_LEASE_TTL_SECONDS = 90
MAX_RETRY_DELAY_SECONDS = 3600
STATE_DISK_DEVICE_NAME = "omi-agent-state"
STATE_SOURCE_DEVICE_NAME = "omi-agent-state-source"
STATE_SOURCE_REQUIRED_METADATA = "omi-agent-state-source-required"
ACTIVE_BOOT_IMAGE_MIGRATION_STATES = frozenset(
    {"candidate_creating", "candidate_ready", "candidate_deleted", "cutover", "retiring"}
)
PRE_CUTOVER_BOOT_IMAGE_MIGRATION_STATES = frozenset({"candidate_creating", "candidate_ready", "candidate_deleted"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_MIGRATION_ID = re.compile(r"^[0-9a-f]{24}$")
_IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
_SERVICE_ACCOUNT = re.compile(r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$")


class AgentVmReleaseError(ValueError):
    """Raised when a release manifest is malformed or unsafe to activate."""


class AgentVmLeaseLost(RuntimeError):
    """Raised when a stale worker no longer owns the Firestore lease."""


class AgentVmNotFound(RuntimeError):
    """Raised when the Firestore owner points at a missing GCE instance."""


class TrustedAgentVmHealthChannelUnavailable(RuntimeError):
    """Raised before a VM bearer token could cross an untrusted network."""


@dataclass(frozen=True)
class AgentVmRelease:
    environment: str
    source_sha: str
    image_digest: str
    startup_uri: str
    startup_sha256: str
    boot_image: str
    service_account: str
    schema_version: int = RECONCILER_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AgentVmRelease":
        def required_string(name: str) -> str:
            value = raw.get(name)
            if not isinstance(value, str) or not value.strip():
                raise AgentVmReleaseError(f"release field {name!r} must be a non-empty string")
            return value.strip()

        schema_version = raw.get("schemaVersion", RECONCILER_SCHEMA_VERSION)
        if schema_version != RECONCILER_SCHEMA_VERSION:
            raise AgentVmReleaseError(f"unsupported release schemaVersion: {schema_version!r}")
        environment = required_string("environment")
        source_sha = required_string("sourceSha")
        image_digest = required_string("imageDigest")
        startup_uri = required_string("startupUri")
        startup_sha256 = required_string("startupSha256")
        boot_image = required_string("bootImage")
        service_account = required_string("serviceAccount")

        if not _SOURCE_SHA.fullmatch(source_sha):
            raise AgentVmReleaseError("sourceSha must be a lowercase 40-character commit SHA")
        if not _IMAGE_DIGEST.fullmatch(image_digest):
            raise AgentVmReleaseError("imageDigest must be an immutable @sha256 image reference")
        if not (startup_uri.startswith("gs://") or startup_uri.startswith("https://storage.googleapis.com/")):
            raise AgentVmReleaseError("startupUri must use gs:// or storage.googleapis.com")
        if not _SHA256.fullmatch(startup_sha256):
            raise AgentVmReleaseError("startupSha256 must be a lowercase SHA-256 digest")
        if not _SERVICE_ACCOUNT.fullmatch(service_account):
            raise AgentVmReleaseError("serviceAccount must be a Google service-account email")
        return cls(
            environment=environment,
            source_sha=source_sha,
            image_digest=image_digest,
            startup_uri=startup_uri,
            startup_sha256=startup_sha256,
            boot_image=boot_image,
            service_account=service_account,
            schema_version=schema_version,
        )

    @property
    def release_id(self) -> str:
        return self.source_sha

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "environment": self.environment,
            "sourceSha": self.source_sha,
            "imageDigest": self.image_digest,
            "startupUri": self.startup_uri,
            "startupSha256": self.startup_sha256,
            "bootImage": self.boot_image,
            "serviceAccount": self.service_account,
        }


def release_manifest_bytes(raw: Mapping[str, Any]) -> bytes:
    """Return canonical bytes used by publication and hash tests."""
    return (json.dumps(dict(raw), sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def validate_release_manifest(raw: Mapping[str, Any]) -> AgentVmRelease:
    release = AgentVmRelease.from_mapping(raw)
    declared_hash = raw.get("manifestSha256")
    if declared_hash is not None:
        if not isinstance(declared_hash, str) or not _SHA256.fullmatch(declared_hash):
            raise AgentVmReleaseError("manifestSha256 must be a lowercase SHA-256 digest")
        unsigned = dict(raw)
        unsigned.pop("manifestSha256", None)
        if hashlib.sha256(release_manifest_bytes(unsigned)).hexdigest() != declared_hash:
            raise AgentVmReleaseError("manifestSha256 does not match the release contents")
    return release


def metadata_items(instance: Mapping[str, Any]) -> dict[str, str]:
    metadata = instance.get("metadata")
    items = metadata.get("items") if isinstance(metadata, Mapping) else None
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("key")): str(item.get("value", ""))
        for item in items
        if isinstance(item, Mapping) and isinstance(item.get("key"), str)
    }


def startup_wrapper(startup_uri: str, startup_sha256: str | None = None) -> str:
    """Build a GCE wrapper that verifies the immutable startup artifact."""
    if startup_uri.startswith("gs://"):
        bucket, _, object_name = startup_uri[5:].partition("/")
        startup_uri = f"https://storage.googleapis.com/{bucket}/{object_name}"
    quoted_uri = shlex.quote(startup_uri)
    checksum_check = ""
    if startup_sha256:
        checksum_check = (
            f"expected_startup_sha256={shlex.quote(startup_sha256)}\n"
            "actual_startup_sha256=\"$(sha256sum /tmp/omi-startup.sh | awk '{print $1}')\"\n"
            "if [[ \"$actual_startup_sha256\" != \"$expected_startup_sha256\" ]]; then\n"
            "  echo 'Agent VM startup artifact checksum mismatch' >&2\n"
            "  exit 1\n"
            "fi\n"
        )
    return (
        "#!/bin/bash\nset -euo pipefail\n"
        f"curl -fsS {quoted_uri} -o /tmp/omi-startup.sh\n"
        f"{checksum_check}exec bash /tmp/omi-startup.sh\n"
    )


def expected_release_metadata(release: AgentVmRelease) -> dict[str, str]:
    return {
        "startup-script": startup_wrapper(release.startup_uri, release.startup_sha256),
        "omi-agent-release": release.release_id,
        "omi-agent-image-digest": release.image_digest,
        "omi-agent-startup-sha256": release.startup_sha256,
        "omi-agent-boot-image": release.boot_image,
        "omi-agent-reconciler-schema": str(release.schema_version),
    }


def drift_reasons(instance: Mapping[str, Any], release: AgentVmRelease) -> list[str]:
    """Return provider drift reasons; absent metadata is intentionally drift."""
    metadata = metadata_items(instance)
    reasons: list[str] = []
    service_accounts = instance.get("serviceAccounts")
    actual_service_account = ""
    if isinstance(service_accounts, list) and service_accounts and isinstance(service_accounts[0], Mapping):
        actual_service_account = str(service_accounts[0].get("email") or "")
    if actual_service_account != release.service_account:
        reasons.append("service_account")
    expected = expected_release_metadata(release)
    for key in (
        "omi-agent-release",
        "omi-agent-image-digest",
        "omi-agent-startup-sha256",
        "omi-agent-boot-image",
        "omi-agent-reconciler-schema",
    ):
        if metadata.get(key) != expected[key]:
            reasons.append(key)
    if metadata.get("startup-script") != expected["startup-script"]:
        reasons.append("startup_script")
    return reasons


def runtime_matches(payload: Mapping[str, Any], release: AgentVmRelease) -> bool:
    return (
        payload.get("status") == "ok"
        and payload.get("release") == release.release_id
        and payload.get("imageDigest") == release.image_digest
        and payload.get("startupSha256") == release.startup_sha256
    )


def state_runtime_matches(payload: Mapping[str, Any], migration_id: str) -> bool:
    """Require the receipt and the database it says was durable to be open."""
    return state_runtime_ready(payload) and payload.get("stateMigrationId") == migration_id


def state_runtime_ready(payload: Mapping[str, Any]) -> bool:
    """Require mounted durable state and any receipt-declared database."""
    database_expected = payload.get("stateDatabaseExpected")
    return (
        payload.get("stateReady") is True
        and isinstance(database_expected, bool)
        and (not database_expected or payload.get("databaseReady") is True)
    )


def retry_delay_seconds(attempt: int) -> int:
    return min(MAX_RETRY_DELAY_SECONDS, 60 * (2 ** max(0, min(attempt, 6))))


def rollout_selected(uid: str, release_id: str, target_percent: int) -> bool:
    """Deterministically select a stable cohort for a rollout percentage."""
    if target_percent >= 100:
        return True
    if target_percent <= 0:
        return False
    bucket = int(hashlib.sha256(f"{release_id}:{uid}".encode()).hexdigest()[:8], 16) % 100
    return bucket < target_percent


def reconcile_requested(vm: Mapping[str, Any], now: float | None = None) -> bool:
    reconcile = vm.get("reconcile")
    if not isinstance(reconcile, Mapping):
        return False
    lease = reconcile.get("lease")
    lease_active = isinstance(lease, Mapping) and float(lease.get("expiresAt", 0) or 0) > (
        time.time() if now is None else now
    )
    return (
        bool(reconcile.get("startRequested"))
        or bool(reconcile.get("drainRequested"))
        or reconcile.get("state")
        in {"claimed", "draining", "deferred", "migration_claimed", "migration_soaking", "missing"}
        or lease_active
    )


@transactional
def _claim_run_lease_txn(transaction: Any, lease_ref: Any, owner: str, now: float, ttl: int) -> bool:
    snapshot = lease_ref.get(transaction=transaction)
    current = snapshot.to_dict() if snapshot.exists else {}
    if isinstance(current, dict) and float(current.get("expiresAt", 0) or 0) > now and current.get("owner") != owner:
        return False
    transaction.set(lease_ref, {"owner": owner, "claimedAt": now, "expiresAt": now + ttl}, merge=True)
    return True


def claim_reconciler_run_lease(
    environment: str, owner: str, now: float | None = None, ttl: int = LEASE_TTL_SECONDS
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _claim_run_lease_txn(
            client.transaction(),
            client.collection("agent_vm_reconciler_leases").document(environment),
            owner,
            now,
            ttl,
        )
    )


@transactional
def _renew_run_lease_txn(transaction: Any, lease_ref: Any, owner: str, now: float, ttl: int) -> bool:
    snapshot = lease_ref.get(transaction=transaction)
    current = snapshot.to_dict() if snapshot.exists else {}
    if not isinstance(current, dict) or current.get("owner") != owner:
        return False
    if float(current.get("expiresAt", 0) or 0) <= now:
        return False
    transaction.update(lease_ref, {"expiresAt": now + ttl, "heartbeatAt": now})
    return True


def renew_reconciler_run_lease(
    environment: str, owner: str, now: float | None = None, ttl: int = LEASE_TTL_SECONDS
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _renew_run_lease_txn(
            client.transaction(),
            client.collection("agent_vm_reconciler_leases").document(environment),
            owner,
            now,
            ttl,
        )
    )


@transactional
def _release_run_lease_txn(transaction: Any, lease_ref: Any, owner: str) -> bool:
    snapshot = lease_ref.get(transaction=transaction)
    current = snapshot.to_dict() if snapshot.exists else {}
    if not isinstance(current, dict) or current.get("owner") != owner:
        return False
    transaction.update(lease_ref, {"owner": DELETE_FIELD, "expiresAt": 0, "releasedAt": time.time()})
    return True


def release_reconciler_run_lease(environment: str, owner: str) -> bool:
    client = get_firestore_client()
    return bool(
        _release_run_lease_txn(
            client.transaction(), client.collection("agent_vm_reconciler_leases").document(environment), owner
        )
    )


@transactional
def _claim_vm_lease_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    recovery_ref: Any | None,
    recovery_migration_id: str | None,
    vm_name: str,
    auth_token: str,
    owner: str,
    release_id: str | None,
    now: float,
    ttl: int,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(vm, dict) or vm.get("vmName") != vm_name or vm.get("authToken") != auth_token:
        return False
    reconcile_raw = vm.get("reconcile")
    reconcile: dict[str, Any] = reconcile_raw if isinstance(reconcile_raw, dict) else {}
    release_changed = release_id is not None and reconcile.get("releaseId") != release_id
    same_release = release_id is None or not release_changed
    if reconcile.get("state") == "quarantined" and same_release:
        recovery_snapshot = recovery_ref.get(transaction=transaction) if recovery_ref is not None else None
        recovery = recovery_snapshot.to_dict() if recovery_snapshot is not None and recovery_snapshot.exists else None
        recorded_instance_id = str(vm.get("instanceId") or "")
        if (
            not isinstance(recovery, dict)
            or recovery_migration_id != reconcile.get("durableMigration")
            or recovery.get("migrationId") != recovery_migration_id
            or recovery.get("state") not in PRE_CUTOVER_BOOT_IMAGE_MIGRATION_STATES
            or recovery.get("oldVmName") != vm_name
            or recovery.get("oldAuthToken") != auth_token
            or recovery.get("targetRelease") != release_id
            or (recorded_instance_id and str(recovery.get("oldInstanceId") or "") != recorded_instance_id)
        ):
            return False
    if float(reconcile.get("retryAt", 0) or 0) > now and same_release:
        return False
    lease_raw = reconcile.get("lease")
    lease: dict[str, Any] = lease_raw if isinstance(lease_raw, dict) else {}
    if float(lease.get("expiresAt", 0) or 0) > now and lease.get("owner") != owner:
        return False
    update: dict[str, Any] = {
        "agentVm.reconcile.lease": {"owner": owner, "claimedAt": now, "expiresAt": now + ttl},
        "agentVm.reconcile.state": "claimed",
        "agentVm.reconcile.schemaVersion": RECONCILER_SCHEMA_VERSION,
    }
    if release_id is not None:
        update["agentVm.reconcile.releaseId"] = release_id
    if release_changed:
        update.update(
            {
                "agentVm.reconcile.retryCount": 0,
                "agentVm.reconcile.retryAt": DELETE_FIELD,
                "agentVm.reconcile.lastError": DELETE_FIELD,
                "agentVm.reconcile.driftReasons": DELETE_FIELD,
            }
        )
    transaction.update(user_ref, update)
    return True


def claim_vm_lease(
    uid: str,
    vm_name: str,
    auth_token: str,
    owner: str,
    release_id: str | None = None,
    recovery_migration_id: str | None = None,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    recovery_ref = (
        user_ref.collection("agentVmMigrations").document(recovery_migration_id)
        if isinstance(recovery_migration_id, str) and _MIGRATION_ID.fullmatch(recovery_migration_id)
        else None
    )
    return bool(
        _claim_vm_lease_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            recovery_ref,
            recovery_migration_id,
            vm_name,
            auth_token,
            owner,
            release_id,
            now,
            LEASE_TTL_SECONDS,
        )
    )


@transactional
def _renew_vm_lease_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    vm_name: str,
    auth_token: str,
    owner: str,
    now: float,
    ttl: int,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(vm, dict) or vm.get("vmName") != vm_name or vm.get("authToken") != auth_token:
        return False
    reconcile_raw = vm.get("reconcile")
    reconcile: dict[str, Any] = reconcile_raw if isinstance(reconcile_raw, dict) else {}
    lease_raw = reconcile.get("lease")
    lease: dict[str, Any] = lease_raw if isinstance(lease_raw, dict) else {}
    if lease.get("owner") != owner or float(lease.get("expiresAt", 0) or 0) <= now:
        return False
    reconcile_raw = vm.get("reconcile")
    reconcile = reconcile_raw if isinstance(reconcile_raw, dict) else {}
    if reconcile.get("state") == "quarantined":
        return False
    transaction.update(
        user_ref, {"agentVm.reconcile.lease.expiresAt": now + ttl, "agentVm.reconcile.lease.heartbeatAt": now}
    )
    return True


def renew_vm_lease(uid: str, vm_name: str, auth_token: str, owner: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _renew_vm_lease_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            client.collection("users").document(uid),
            vm_name,
            auth_token,
            owner,
            now,
            LEASE_TTL_SECONDS,
        )
    )


@transactional
def _update_vm_reconcile_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    vm_name: str,
    auth_token: str,
    owner: str,
    fields: Mapping[str, Any],
    vm_fields: Mapping[str, Any] | None = None,
    now: float | None = None,
    consume_start_request_at: float | None = None,
    force_consume_start_request: bool = False,
) -> bool:
    now = time.time() if now is None else now
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(vm, dict) or vm.get("vmName") != vm_name or vm.get("authToken") != auth_token:
        return False
    reconcile_raw = vm.get("reconcile")
    reconcile: dict[str, Any] = reconcile_raw if isinstance(reconcile_raw, dict) else {}
    lease_raw = reconcile.get("lease")
    lease: dict[str, Any] = lease_raw if isinstance(lease_raw, dict) else {}
    if lease.get("owner") != owner or float(lease.get("expiresAt", 0) or 0) <= now:
        return False
    update: dict[str, Any] = {}
    reconciled_fields = _reconcile_update_fields(
        fields, reconcile, consume_start_request_at, force_consume_start_request
    )
    for key, value in reconciled_fields.items():
        update[f"agentVm.reconcile.{key}"] = value
    for key, value in (vm_fields or {}).items():
        update[f"agentVm.{key}"] = value
    transaction.update(user_ref, update)
    return True


def _reconcile_update_fields(
    fields: Mapping[str, Any],
    reconcile: Mapping[str, Any],
    consume_start_request_at: float | None,
    force_consume_start_request: bool = False,
) -> dict[str, Any]:
    """Do not erase a start request that arrived after a worker's observation."""
    result = dict(fields)
    requested_at = reconcile.get("startRequestedAt")
    current_request_at = float(requested_at) if isinstance(requested_at, (int, float)) else None
    clears_start_request = (
        result.get("startRequested") is DELETE_FIELD or result.get("startRequestedAt") is DELETE_FIELD
    )
    if (
        not force_consume_start_request
        and clears_start_request
        and (
            consume_start_request_at is None
            or current_request_at is None
            or current_request_at > consume_start_request_at
        )
    ):
        result.pop("startRequested", None)
        result.pop("startRequestedAt", None)
    return result


def update_vm_reconcile(
    uid: str,
    vm_name: str,
    auth_token: str,
    owner: str,
    fields: Mapping[str, Any],
    vm_fields: Mapping[str, Any] | None = None,
    now: float | None = None,
    consume_start_request_at: float | None = None,
    force_consume_start_request: bool = False,
) -> bool:
    client = get_firestore_client()
    return bool(
        _update_vm_reconcile_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            client.collection("users").document(uid),
            vm_name,
            auth_token,
            owner,
            fields,
            vm_fields,
            now,
            consume_start_request_at,
            force_consume_start_request,
        )
    )


@transactional
def _clear_missing_vm_if_current_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    expected_missing_since: float,
    now: float,
) -> bool:
    """Remove one terminal VM pointer only while this worker still owns it.

    A prior reconcile lease prevents a new session admission. The caller must
    separately observe that no pre-existing session lease remains before this
    compare-and-swap deletes the pointer.
    """
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if (
        not isinstance(vm, dict)
        or vm.get("vmName") != vm_name
        or (vm.get("zone") or DEFAULT_ZONE) != zone
        or vm.get("authToken") != auth_token
        or vm.get("status") not in {"ready", "stopped"}
    ):
        return False
    reconcile_raw = vm.get("reconcile")
    reconcile: dict[str, Any] = reconcile_raw if isinstance(reconcile_raw, dict) else {}
    lease_raw = reconcile.get("lease")
    lease: dict[str, Any] = lease_raw if isinstance(lease_raw, dict) else {}
    if (
        reconcile.get("state") != "claimed"
        or lease.get("owner") != owner
        or float(lease.get("expiresAt", 0) or 0) <= now
        or bool(reconcile.get("startRequested"))
        or bool(reconcile.get("drainRequested"))
    ):
        return False
    missing_since = reconcile.get("missingSince")
    if not isinstance(missing_since, (int, float)) or float(missing_since) != expected_missing_since:
        return False
    transaction.update(user_ref, {"agentVm": DELETE_FIELD})
    return True


def clear_missing_vm_if_current(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    expected_missing_since: float,
    now: float | None = None,
) -> bool:
    """Delete a proven-abandoned missing VM record with deletion and owner fences."""
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _clear_missing_vm_if_current_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            client.collection("users").document(uid),
            vm_name,
            zone,
            auth_token,
            owner,
            expected_missing_since,
            now,
        )
    )


def clear_vm_reconcile_lease_fields() -> dict[str, Any]:
    return {
        "lease": DELETE_FIELD,
        "startRequested": DELETE_FIELD,
        "startRequestedAt": DELETE_FIELD,
        "drainRequested": DELETE_FIELD,
        "drainRequestedAt": DELETE_FIELD,
    }


def _migration_matches(
    vm: Mapping[str, Any],
    *,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    now: float,
    instance_id: str | None = None,
) -> bool:
    """Validate the active pointer and reconciler lease for a migration CAS."""
    reconcile = vm.get("reconcile")
    reconcile = reconcile if isinstance(reconcile, Mapping) else {}
    if (
        vm.get("vmName") != vm_name
        or (vm.get("zone") or DEFAULT_ZONE) != zone
        or vm.get("authToken") != auth_token
        or (instance_id is not None and str(vm.get("instanceId") or "") != instance_id)
        or bool(reconcile.get("startRequested"))
        or bool(reconcile.get("drainRequested"))
    ):
        return False
    lease = reconcile.get("lease")
    return isinstance(lease, Mapping) and lease.get("owner") == owner and float(lease.get("expiresAt", 0) or 0) > now


def active_boot_image_migration(
    uid: str,
    vm_name: str,
    instance_id: str,
    migration_id: str,
    *,
    firestore_client: Any | None = None,
) -> dict[str, Any] | None:
    """Find the durable migration belonging to this provider VM identity.

    Matching both predecessor and candidate identities lets a retry recover a
    crash before cutover while leaving the post-cutover retirement path fenced
    by the same durable journal.
    """
    client = firestore_client or get_firestore_client()
    snapshot = client.collection("users").document(uid).collection("agentVmMigrations").document(migration_id).get()
    migration = snapshot.to_dict() if snapshot.exists else None
    if (
        not isinstance(migration, dict)
        or migration.get("migrationId") != migration_id
        or migration.get("state") not in ACTIVE_BOOT_IMAGE_MIGRATION_STATES
    ):
        return None
    predecessor_matches = (
        migration.get("oldVmName") == vm_name and str(migration.get("oldInstanceId") or "") == instance_id
    )
    candidate_matches = (
        migration.get("candidateVmName") == vm_name and str(migration.get("candidateInstanceId") or "") == instance_id
    )
    return migration if predecessor_matches or candidate_matches else None


@transactional
def _begin_boot_image_migration_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration: Mapping[str, Any],
    now: float,
) -> dict[str, Any] | None:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return None
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(vm, dict) or not _migration_matches(
        vm, vm_name=vm_name, zone=zone, auth_token=auth_token, owner=owner, now=now
    ):
        return None
    durable_migration_id = migration.get("migrationId")
    old_instance_id = str(migration.get("oldInstanceId") or "")
    if not isinstance(durable_migration_id, str) or not durable_migration_id or not old_instance_id:
        return None
    recorded_instance_id = str(vm.get("instanceId") or "")
    if recorded_instance_id and recorded_instance_id != old_instance_id:
        return None
    if str(vm.get("status") or "") not in {"stopped", "ready"}:
        return None
    existing = migration_ref.get(transaction=transaction)
    if existing.exists:
        current = existing.to_dict() or {}
        if not (
            current.get("oldVmName") == vm_name
            and current.get("oldAuthToken") == auth_token
            and current.get("oldInstanceId") == migration.get("oldInstanceId")
            and current.get("candidateVmName") == migration.get("candidateVmName")
            and current.get("targetRelease") == migration.get("targetRelease")
        ):
            return None
        # A terminal candidate cleanup is explicitly retryable.  Reuse the
        # durable candidate name/token but remove its old provider identity so
        # the next creation can be recorded under the same fenced journal.
        if current.get("state") == "candidate_deleted":
            transaction.update(
                migration_ref,
                {"state": "candidate_creating", "candidateInstanceId": DELETE_FIELD, "updatedAt": now},
            )
            return {**current, "state": "candidate_creating"}
        return current
    record = {**migration, "state": "candidate_creating", "createdAt": now, "updatedAt": now}
    transaction.set(migration_ref, record)
    update = {
        "agentVm.reconcile.state": "migration_claimed",
        "agentVm.reconcile.durableMigration": durable_migration_id,
    }
    if not recorded_instance_id:
        # Legacy owner records predate the explicit GCE ID field. Bind it only
        # inside this stopped-only, owner-token-and-lease CAS, then every
        # subsequent journal transition requires that exact provider identity.
        update["agentVm.instanceId"] = old_instance_id
    transaction.update(user_ref, update)
    return record


def begin_boot_image_migration(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    migration: Mapping[str, Any],
    now: float | None = None,
) -> dict[str, Any] | None:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    result = _begin_boot_image_migration_txn(
        client.transaction(),
        client.collection("account_deletions").document(uid),
        user_ref,
        user_ref.collection("agentVmMigrations").document(migration_id),
        vm_name,
        zone,
        auth_token,
        owner,
        migration,
        now,
    )
    return result if isinstance(result, dict) else None


@transactional
def _record_boot_image_candidate_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    candidate_instance_id: str,
    now: float,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration_snapshot = migration_ref.get(transaction=transaction)
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or not _migration_matches(
            vm,
            vm_name=vm_name,
            zone=zone,
            auth_token=auth_token,
            owner=owner,
            now=now,
            instance_id=str(migration.get("oldInstanceId") or ""),
        )
    ):
        return False
    if migration.get("state") == "candidate_ready":
        return migration.get("candidateInstanceId") == candidate_instance_id
    if migration.get("state") != "candidate_creating":
        return False
    transaction.update(
        migration_ref,
        {"state": "candidate_ready", "candidateInstanceId": candidate_instance_id, "updatedAt": now},
    )
    return True


def record_boot_image_candidate(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate_instance_id: str,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _record_boot_image_candidate_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmMigrations").document(migration_id),
            vm_name,
            zone,
            auth_token,
            owner,
            candidate_instance_id,
            now,
        )
    )


@transactional
def _record_boot_image_state_disks_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    state: Mapping[str, Any],
    now: float,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = user_ref.get(transaction=transaction)
    migration_snapshot = migration_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or migration.get("state") not in {"candidate_creating", "candidate_ready"}
        or not _migration_matches(vm, vm_name=vm_name, zone=zone, auth_token=auth_token, owner=owner, now=now)
        or migration.get("stateDiskName") != state.get("stateDiskName")
        or migration.get("sourceCloneDiskName") != state.get("sourceCloneDiskName")
    ):
        return False
    state_disk_id = state.get("stateDiskId")
    if not isinstance(state_disk_id, str) or not state_disk_id:
        return False
    update = {
        "stateDiskId": state_disk_id,
        "stateDiskReused": state.get("stateDiskReused") is True,
        "updatedAt": now,
    }
    source_clone_id = state.get("sourceCloneDiskId")
    if isinstance(source_clone_id, str) and source_clone_id:
        update["sourceCloneDiskId"] = source_clone_id
    transaction.update(migration_ref, update)
    return True


def record_boot_image_state_disks(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    state: Mapping[str, Any],
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _record_boot_image_state_disks_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmMigrations").document(migration_id),
            vm_name,
            zone,
            auth_token,
            owner,
            state,
            now,
        )
    )


@transactional
def _mark_boot_image_migration_candidate_deleted_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    candidate_instance_id: str,
    now: float,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = user_ref.get(transaction=transaction)
    migration_snapshot = migration_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or migration.get("state") != "candidate_ready"
        or migration.get("candidateInstanceId") != candidate_instance_id
        or not _migration_matches(vm, vm_name=vm_name, zone=zone, auth_token=auth_token, owner=owner, now=now)
    ):
        return False
    transaction.update(
        migration_ref,
        {"state": "candidate_deleted", "candidateDeletedAt": now, "updatedAt": now},
    )
    return True


def mark_boot_image_migration_candidate_deleted(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate_instance_id: str,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _mark_boot_image_migration_candidate_deleted_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmMigrations").document(migration_id),
            vm_name,
            zone,
            auth_token,
            owner,
            candidate_instance_id,
            now,
        )
    )


@transactional
def _recover_missing_boot_image_candidate_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    now: float,
) -> bool:
    """Permit recreation only after GCE has confirmed the candidate is gone."""
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = user_ref.get(transaction=transaction)
    migration_snapshot = migration_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or migration.get("state") not in {"candidate_creating", "candidate_ready", "candidate_deleted"}
        or not _migration_matches(vm, vm_name=vm_name, zone=zone, auth_token=auth_token, owner=owner, now=now)
    ):
        return False
    if migration.get("state") != "candidate_creating":
        transaction.update(
            migration_ref,
            {"state": "candidate_creating", "candidateInstanceId": DELETE_FIELD, "updatedAt": now},
        )
    return True


def recover_missing_boot_image_candidate(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    now: float | None = None,
) -> bool:
    """Fence a retry after a candidate has been observed absent in GCE."""
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _recover_missing_boot_image_candidate_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmMigrations").document(migration_id),
            vm_name,
            zone,
            auth_token,
            owner,
            now,
        )
    )


@transactional
def _cutover_boot_image_migration_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    candidate: Mapping[str, Any],
    now: float,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration_snapshot = migration_ref.get(transaction=transaction)
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or migration.get("state") not in {"candidate_creating", "candidate_ready"}
        or not _migration_matches(
            vm,
            vm_name=vm_name,
            zone=zone,
            auth_token=auth_token,
            owner=owner,
            now=now,
            instance_id=str(migration.get("oldInstanceId") or ""),
        )
    ):
        return False
    if migration.get("candidateVmName") != candidate.get("vmName") or migration.get(
        "candidateInstanceId"
    ) != candidate.get("instanceId"):
        return False
    soak_seconds = migration.get("soakSeconds")
    if not isinstance(soak_seconds, int) or soak_seconds < 60:
        return False
    transaction.update(user_ref, {"agentVm": dict(candidate)})
    transaction.update(
        migration_ref,
        {
            "state": "cutover",
            "cutoverAt": now,
            "retireAfter": now + soak_seconds,
            "updatedAt": now,
        },
    )
    return True


@transactional
def _claim_boot_image_migration_retirement_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate_instance_id: str,
    now: float,
) -> dict[str, Any] | None:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return None
    snapshot = user_ref.get(transaction=transaction)
    migration_snapshot = migration_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    reconcile = vm.get("reconcile") if isinstance(vm, Mapping) else None
    active_migration = reconcile.get("migration") if isinstance(reconcile, Mapping) else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or not isinstance(active_migration, Mapping)
        or migration.get("migrationId") != migration_id
        or active_migration.get("migrationId") != migration_id
        or active_migration.get("oldVmName") != migration.get("oldVmName")
        or active_migration.get("oldInstanceId") != migration.get("oldInstanceId")
        or migration.get("candidateInstanceId") != candidate_instance_id
        or not _migration_matches(
            vm,
            vm_name=vm_name,
            zone=zone,
            auth_token=auth_token,
            owner=owner,
            now=now,
            instance_id=candidate_instance_id,
        )
    ):
        return None
    if migration.get("state") == "cutover":
        retire_after = migration.get("retireAfter")
        if not isinstance(retire_after, (int, float)):
            return None
        if now < float(retire_after):
            return {**migration, "state": "soaking"}
        transaction.update(migration_ref, {"state": "retiring", "retirementClaimedAt": now, "updatedAt": now})
        return {**migration, "state": "retiring"}
    return migration if migration.get("state") == "retiring" else None


def claim_boot_image_migration_retirement(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate_instance_id: str,
    now: float | None = None,
) -> dict[str, Any] | None:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    result = _claim_boot_image_migration_retirement_txn(
        client.transaction(),
        client.collection("account_deletions").document(uid),
        user_ref,
        user_ref.collection("agentVmMigrations").document(migration_id),
        vm_name,
        zone,
        auth_token,
        owner,
        migration_id,
        candidate_instance_id,
        now,
    )
    return result if isinstance(result, dict) else None


@transactional
def _complete_boot_image_migration_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    migration_ref: Any,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate_instance_id: str,
    now: float,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = user_ref.get(transaction=transaction)
    migration_snapshot = migration_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    reconcile = vm.get("reconcile") if isinstance(vm, Mapping) else None
    active_migration = reconcile.get("migration") if isinstance(reconcile, Mapping) else None
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or not isinstance(active_migration, Mapping)
        or migration.get("state") != "retiring"
        or migration.get("migrationId") != migration_id
        or active_migration.get("migrationId") != migration_id
        or active_migration.get("oldVmName") != migration.get("oldVmName")
        or active_migration.get("oldInstanceId") != migration.get("oldInstanceId")
        or migration.get("candidateInstanceId") != candidate_instance_id
        or not _migration_matches(
            vm,
            vm_name=vm_name,
            zone=zone,
            auth_token=auth_token,
            owner=owner,
            now=now,
            instance_id=candidate_instance_id,
        )
    ):
        return False
    completion = {
        "agentVm.reconcile.migration": DELETE_FIELD,
        "agentVm.reconcile.durableMigration": DELETE_FIELD,
        "agentVm.reconcile.state": "ready",
    }
    completion.update({f"agentVm.reconcile.{key}": value for key, value in clear_vm_reconcile_lease_fields().items()})
    transaction.update(user_ref, completion)
    transaction.update(migration_ref, {"state": "completed", "completedAt": now, "updatedAt": now})
    return True


def complete_boot_image_migration(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate_instance_id: str,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _complete_boot_image_migration_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmMigrations").document(migration_id),
            vm_name,
            zone,
            auth_token,
            owner,
            migration_id,
            candidate_instance_id,
            now,
        )
    )


def cutover_boot_image_migration(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    candidate: Mapping[str, Any],
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _cutover_boot_image_migration_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmMigrations").document(migration_id),
            vm_name,
            zone,
            auth_token,
            owner,
            candidate,
            now,
        )
    )


@transactional
def _request_vm_start_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    expected_vm_name: str,
    expected_auth_token: str,
    now: float,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(vm, dict) or vm.get("vmName") != expected_vm_name or vm.get("authToken") != expected_auth_token:
        return False
    transaction.update(
        user_ref,
        {
            "agentVm.reconcile.startRequested": True,
            "agentVm.reconcile.startRequestedAt": now,
        },
    )
    return True


def request_vm_start(uid: str, vm_name: str, auth_token: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _request_vm_start_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            client.collection("users").document(uid),
            vm_name,
            auth_token,
            now,
        )
    )


@transactional
def _claim_session_lease_txn(
    transaction: Any,
    deletion_ref: Any,
    user_ref: Any,
    lease_ref: Any,
    vm_name: str,
    auth_token: str,
    lease_id: str,
    now: float,
    ttl: int,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(vm, dict) or vm.get("vmName") != vm_name or vm.get("authToken") != auth_token:
        return False
    if reconcile_requested(vm, now):
        return False
    transaction.set(
        lease_ref,
        {"leaseId": lease_id, "vmName": vm_name, "claimedAt": now, "heartbeatAt": now, "expiresAt": now + ttl},
    )
    return True


def claim_session_lease(uid: str, vm_name: str, auth_token: str, lease_id: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    return bool(
        _claim_session_lease_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            user_ref,
            user_ref.collection("agentVmLeases").document(lease_id),
            vm_name,
            auth_token,
            lease_id,
            now,
            SESSION_LEASE_TTL_SECONDS,
        )
    )


@transactional
def _heartbeat_session_lease_txn(transaction: Any, lease_ref: Any, now: float, ttl: int) -> bool:
    snapshot = lease_ref.get(transaction=transaction)
    lease = snapshot.to_dict() if snapshot.exists else {}
    if not isinstance(lease, dict) or float(lease.get("expiresAt", 0) or 0) <= now:
        return False
    transaction.update(lease_ref, {"heartbeatAt": now, "expiresAt": now + ttl})
    return True


def heartbeat_session_lease(uid: str, lease_id: str, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _heartbeat_session_lease_txn(
            client.transaction(),
            client.collection("users").document(uid).collection("agentVmLeases").document(lease_id),
            now,
            SESSION_LEASE_TTL_SECONDS,
        )
    )


def release_session_lease(uid: str, lease_id: str) -> None:
    client = get_firestore_client()
    client.collection("users").document(uid).collection("agentVmLeases").document(lease_id).delete()


def active_session_count(uid: str, vm_name: str, now: float | None = None) -> int:
    now = time.time() if now is None else now
    client = get_firestore_client()
    leases = client.collection("users").document(uid).collection("agentVmLeases").stream()
    return sum(
        1
        for snapshot in leases
        if isinstance(snapshot.to_dict(), dict)
        and snapshot.to_dict().get("vmName") == vm_name
        and float(snapshot.to_dict().get("expiresAt", 0) or 0) > now
    )


class GceAgentVmClient:
    """Small async Compute API client used by the scheduled reconciler."""

    def __init__(self, project: str, zone: str = DEFAULT_ZONE) -> None:
        self.project = project
        self.zone = zone

    @staticmethod
    def access_token() -> str:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
        if not credentials.token:
            raise RuntimeError("GCE credentials did not produce an access token")
        return str(credentials.token)

    async def request(self, method: str, url: str, body: Mapping[str, Any] | None = None) -> httpx.Response:
        token = await asyncio.to_thread(self.access_token)
        async with httpx.AsyncClient(timeout=180) as client:
            return await client.request(method, url, headers={"Authorization": f"Bearer {token}"}, json=body)

    def instance_url(self, vm_name: str) -> str:
        return (
            f"https://compute.googleapis.com/compute/v1/projects/{self.project}/zones/{self.zone}/instances/{vm_name}"
        )

    async def get_instance(self, vm_name: str) -> dict[str, Any] | None:
        response = await self.request("GET", self.instance_url(vm_name))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    async def wait_operation(self, operation: Mapping[str, Any]) -> None:
        name = operation.get("name")
        if not isinstance(name, str) or not name:
            raise RuntimeError("GCE operation response omitted name")
        scope = "global" if operation.get("selfLink", "").endswith("/global/operations/" + name) else self.zone
        if scope == "global":
            url = f"https://compute.googleapis.com/compute/v1/projects/{self.project}/global/operations/{name}"
        else:
            url = (
                f"https://compute.googleapis.com/compute/v1/projects/{self.project}/zones/{self.zone}/operations/{name}"
            )
        for _ in range(150):
            await asyncio.sleep(2)
            response = await self.request("GET", url)
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "DONE":
                if result.get("error"):
                    raise RuntimeError("GCE operation failed")
                return
        raise RuntimeError("GCE operation timed out")

    async def _mutate(self, method: str, url: str, body: Mapping[str, Any] | None = None) -> None:
        response = await self.request(method, url, body)
        response.raise_for_status()
        await self.wait_operation(response.json())

    async def set_service_account(self, vm_name: str, service_account: str) -> None:
        await self._mutate(
            "POST",
            self.instance_url(vm_name) + "/setServiceAccount",
            {"email": service_account, "scopes": ["https://www.googleapis.com/auth/cloud-platform"]},
        )

    async def set_metadata(
        self,
        vm_name: str,
        instance: Mapping[str, Any],
        release: AgentVmRelease,
        auth_token: str | None = None,
        extra_metadata: Mapping[str, str] | None = None,
    ) -> None:
        metadata = dict(instance.get("metadata") or {})
        items = metadata.get("items")
        current: dict[str, str] = {}
        if isinstance(items, list):
            current = {
                str(item.get("key")): str(item.get("value", ""))
                for item in items
                if isinstance(item, Mapping) and isinstance(item.get("key"), str)
            }
        current.update(expected_release_metadata(release))
        if auth_token:
            current["auth-token"] = auth_token
        current.update(extra_metadata or {})
        fingerprint = metadata.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise RuntimeError("GCE instance metadata fingerprint missing")
        await self._mutate(
            "POST",
            self.instance_url(vm_name) + "/setMetadata",
            {
                "fingerprint": fingerprint,
                "items": [{"key": key, "value": value} for key, value in sorted(current.items())],
            },
        )

    async def set_migration_labels(self, vm_name: str, instance: Mapping[str, Any], migration_id: str) -> None:
        fingerprint = instance.get("labelFingerprint")
        if not isinstance(fingerprint, str) or not fingerprint:
            raise RuntimeError("GCE instance label fingerprint missing")
        labels = instance.get("labels")
        current = dict(labels) if isinstance(labels, Mapping) else {}
        current["omi-agent-migration"] = migration_id
        current["omi-agent-predecessor"] = str(instance.get("id") or "")
        await self._mutate(
            "POST", self.instance_url(vm_name) + "/setLabels", {"labelFingerprint": fingerprint, "labels": current}
        )

    async def stop(self, vm_name: str) -> None:
        await self._mutate("POST", self.instance_url(vm_name) + "/stop")

    async def start(self, vm_name: str) -> None:
        await self._mutate("POST", self.instance_url(vm_name) + "/start")

    def disk_url(self, disk_name: str) -> str:
        return f"https://compute.googleapis.com/compute/v1/projects/{self.project}/zones/{self.zone}/disks/{disk_name}"

    async def get_disk(self, disk_name: str) -> dict[str, Any] | None:
        response = await self.request("GET", self.disk_url(disk_name))
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    async def create_disk(
        self,
        disk_name: str,
        *,
        migration_id: str,
        role: str,
        owner_hash: str,
        source_disk: str | None = None,
        size_gb: int = 50,
    ) -> dict[str, Any]:
        """Create or recover one deterministic, migration-labelled disk."""
        existing = await self.get_disk(disk_name)
        if existing is None:
            body: dict[str, Any] = {
                "name": disk_name,
                "labels": {
                    "omi-agent-migration": migration_id,
                    "omi-agent-role": role,
                    "omi-agent-owner": owner_hash,
                },
            }
            if source_disk:
                body["sourceDisk"] = source_disk
            else:
                body.update(
                    {
                        "sizeGb": str(size_gb),
                        "type": f"zones/{self.zone}/diskTypes/pd-balanced",
                    }
                )
            await self._mutate(
                "POST",
                f"https://compute.googleapis.com/compute/v1/projects/{self.project}/zones/{self.zone}/disks",
                body,
            )
            existing = await self.get_disk(disk_name)
        if existing is None:
            raise RuntimeError("created Agent VM state disk is unavailable")
        labels = existing.get("labels")
        if (
            str(existing.get("id") or "") == ""
            or existing.get("status") != "READY"
            or not isinstance(labels, Mapping)
            or labels.get("omi-agent-migration") != migration_id
            or labels.get("omi-agent-role") != role
            or labels.get("omi-agent-owner") != owner_hash
        ):
            raise RuntimeError("Agent VM state disk identity is ambiguous")
        if source_disk:
            actual_source = str(existing.get("sourceDisk") or "")
            if actual_source.rstrip("/").split("/compute/v1/")[-1] != source_disk.rstrip("/").split("/compute/v1/")[-1]:
                raise RuntimeError("Agent VM source clone does not match the predecessor disk")
        return existing

    async def set_disk_auto_delete(self, vm_name: str, device_name: str, auto_delete: bool) -> None:
        value = "true" if auto_delete else "false"
        await self._mutate(
            "POST",
            self.instance_url(vm_name) + f"/setDiskAutoDelete?deviceName={device_name}&autoDelete={value}",
        )

    async def detach_disk(self, vm_name: str, device_name: str) -> None:
        await self._mutate("POST", self.instance_url(vm_name) + f"/detachDisk?deviceName={device_name}")

    async def attach_disk(
        self,
        vm_name: str,
        disk_source: str,
        *,
        device_name: str = STATE_DISK_DEVICE_NAME,
        read_only: bool = False,
        auto_delete: bool = False,
    ) -> None:
        await self._mutate(
            "POST",
            self.instance_url(vm_name) + "/attachDisk",
            {
                "source": disk_source,
                "deviceName": device_name,
                "mode": "READ_ONLY" if read_only else "READ_WRITE",
                "autoDelete": auto_delete,
            },
        )

    async def delete_disk(
        self,
        disk_name: str,
        expected_disk_id: str,
        migration_id: str | None,
        role: str,
        owner_hash: str,
    ) -> bool:
        disk = await self.get_disk(disk_name)
        if disk is None:
            return True
        labels = disk.get("labels")
        migration_matches = isinstance(labels, Mapping) and labels.get("omi-agent-migration") == migration_id
        # A reused owner state disk predates the migration journal and therefore
        # has no migration label. Its numeric provider ID, role, and owner label
        # are the complete rollback fence; migration-created source disks still
        # require their journal label.
        if (
            str(disk.get("id") or "") != expected_disk_id
            or not isinstance(labels, Mapping)
            or labels.get("omi-agent-role") != role
            or labels.get("omi-agent-owner") != owner_hash
            or (role != "state" and not migration_matches)
        ):
            return False
        users = disk.get("users")
        if isinstance(users, list) and users:
            return False
        await self._mutate("DELETE", self.disk_url(disk_name))
        return True

    async def create_replacement(
        self,
        vm_name: str,
        predecessor: Mapping[str, Any],
        release: AgentVmRelease,
        auth_token: str,
        migration_id: str,
        state_disk_source: str,
        source_clone_disk_source: str | None = None,
        owner_hash: str = "",
    ) -> None:
        """Create a labelled replacement from the pinned immutable boot image.

        The caller first writes a journal record, making a create retry find the
        same deterministic VM name.  We deliberately do not copy a private IP,
        disk, token, or arbitrary metadata from the predecessor.
        """
        if not owner_hash:
            raise RuntimeError("replacement owner identity is unavailable")
        machine_type = predecessor.get("machineType")
        if not isinstance(machine_type, str) or not machine_type:
            raise RuntimeError("predecessor machine type is unavailable")
        interfaces = predecessor.get("networkInterfaces")
        first = interfaces[0] if isinstance(interfaces, list) and interfaces else None
        if not isinstance(first, Mapping) or not isinstance(first.get("network"), str):
            raise RuntimeError("predecessor network is unavailable")
        subnet = first.get("subnetwork")
        interface: dict[str, Any] = {"subnetwork": subnet} if isinstance(subnet, str) else {"network": first["network"]}
        if isinstance(first.get("accessConfigs"), list) and first["accessConfigs"]:
            interface["accessConfigs"] = [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}]
        predecessor_id = str(predecessor.get("id") or "")
        if not predecessor_id:
            raise RuntimeError("predecessor instance ID is unavailable")
        disks: list[dict[str, Any]] = [
            {
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": release.boot_image,
                    "diskSizeGb": "50",
                    "diskType": f"zones/{self.zone}/diskTypes/pd-balanced",
                },
            },
            {
                "boot": False,
                "autoDelete": False,
                "deviceName": STATE_DISK_DEVICE_NAME,
                "mode": "READ_WRITE",
                "source": state_disk_source,
            },
        ]
        if source_clone_disk_source:
            disks.append(
                {
                    "boot": False,
                    "autoDelete": False,
                    "deviceName": STATE_SOURCE_DEVICE_NAME,
                    "mode": "READ_ONLY",
                    "source": source_clone_disk_source,
                }
            )
        body = {
            "name": vm_name,
            "machineType": machine_type,
            "disks": disks,
            "serviceAccounts": [
                {"email": release.service_account, "scopes": ["https://www.googleapis.com/auth/cloud-platform"]}
            ],
            "networkInterfaces": [interface],
            "tags": {"items": ["omi-agent-vm"]},
            "labels": {
                "omi-agent-migration": migration_id,
                "omi-agent-predecessor": predecessor_id,
                "omi-agent-owner": owner_hash,
            },
            "metadata": {
                "items": [
                    *[{"key": key, "value": value} for key, value in expected_release_metadata(release).items()],
                    {"key": "auth-token", "value": auth_token},
                    {"key": "omi-agent-migration", "value": migration_id},
                    {"key": "omi-agent-state-required", "value": "true"},
                    {
                        "key": STATE_SOURCE_REQUIRED_METADATA,
                        "value": "true" if source_clone_disk_source else "false",
                    },
                ]
            },
        }
        await self._mutate(
            "POST",
            f"https://compute.googleapis.com/compute/v1/projects/{self.project}/zones/{self.zone}/instances",
            body,
        )

    async def delete_replacement(self, vm_name: str, expected_instance_id: str, migration_id: str) -> bool:
        """Delete only the labelled, numeric-ID-matched predecessor/candidate."""
        instance = await self.get_instance(vm_name)
        if instance is None:
            return True
        labels = instance.get("labels")
        if (
            str(instance.get("id") or "") != expected_instance_id
            or not isinstance(labels, Mapping)
            or labels.get("omi-agent-migration") != migration_id
        ):
            return False
        await self._mutate("DELETE", self.instance_url(vm_name))
        return True

    @staticmethod
    def instance_ip(instance: Mapping[str, Any]) -> str | None:
        try:
            value = str(instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"])
            ipaddress.ip_address(value)
            return value
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @staticmethod
    def private_instance_ip(instance: Mapping[str, Any]) -> str | None:
        try:
            value = str(instance["networkInterfaces"][0]["networkIP"])
            address = ipaddress.ip_address(value)
            return value if GceAgentVmClient._is_rfc1918(address) else None
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @staticmethod
    def _is_rfc1918(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        if not isinstance(address, ipaddress.IPv4Address):
            return False
        return any(
            address in network
            for network in (
                ipaddress.ip_network("10.0.0.0/8"),
                ipaddress.ip_network("172.16.0.0/12"),
                ipaddress.ip_network("192.168.0.0/16"),
            )
        )

    @staticmethod
    def _trusted_runtime_url(ip: str) -> str:
        """Return an HTTP URL only when routing itself is a trusted boundary.

        The VM runtime does not currently terminate TLS. Production therefore
        requires a private VPC path; local development may explicitly opt into
        loopback. Any other address/channel fails before auth_token is used.
        """
        try:
            address = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise TrustedAgentVmHealthChannelUnavailable("Agent VM readiness address is invalid") from exc
        channel = os.getenv("AGENT_VM_TRUSTED_HEALTH_CHANNEL", "").strip().lower()
        if channel == "private-vpc" and GceAgentVmClient._is_rfc1918(address):
            return f"http://{address}:8080/health"
        if channel == "loopback-dev" and address.is_loopback and os.getenv("ENVIRONMENT") != "production":
            return f"http://{address}:8080/health"
        raise TrustedAgentVmHealthChannelUnavailable(
            "Agent VM readiness requires AGENT_VM_TRUSTED_HEALTH_CHANNEL=private-vpc and private VPC reachability"
        )

    async def wait_for_runtime(
        self,
        ip: str,
        auth_token: str,
        release: AgentVmRelease,
        timeout: int = 300,
        *,
        expected_state_migration_id: str | None = None,
        require_state: bool = False,
    ) -> None:
        deadline = time.monotonic() + timeout
        runtime_url = self._trusted_runtime_url(ip)
        headers = {"Authorization": f"Bearer {auth_token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            while time.monotonic() < deadline:
                try:
                    response = await client.get(runtime_url, headers=headers)
                    payload = response.json()
                    if (
                        response.status_code == 200
                        and isinstance(payload, Mapping)
                        and runtime_matches(payload, release)
                        and (
                            expected_state_migration_id is None
                            or state_runtime_matches(payload, expected_state_migration_id)
                        )
                        and (not require_state or state_runtime_ready(payload))
                    ):
                        return
                except (httpx.HTTPError, ValueError):
                    pass
                await asyncio.sleep(5)
        raise RuntimeError("Agent VM did not report the activated release before the readiness timeout")

    async def runtime_is_current(
        self,
        ip: str,
        auth_token: str,
        release: AgentVmRelease,
        *,
        expected_state_migration_id: str | None = None,
        require_state: bool = False,
    ) -> bool:
        runtime_url = self._trusted_runtime_url(ip)
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    runtime_url,
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
            payload = response.json()
            return (
                response.status_code == 200
                and isinstance(payload, Mapping)
                and runtime_matches(payload, release)
                and (expected_state_migration_id is None or state_runtime_matches(payload, expected_state_migration_id))
                and (not require_state or state_runtime_ready(payload))
            )
        except (httpx.HTTPError, ValueError):
            return False


__all__ = [
    "AgentVmLeaseLost",
    "AgentVmNotFound",
    "AgentVmRelease",
    "AgentVmReleaseError",
    "ACTIVE_BOOT_IMAGE_MIGRATION_STATES",
    "DEFAULT_ZONE",
    "GceAgentVmClient",
    "STATE_DISK_DEVICE_NAME",
    "STATE_SOURCE_DEVICE_NAME",
    "STATE_SOURCE_REQUIRED_METADATA",
    "PRE_CUTOVER_BOOT_IMAGE_MIGRATION_STATES",
    "LEASE_HEARTBEAT_SECONDS",
    "RECONCILER_SCHEMA_VERSION",
    "TrustedAgentVmHealthChannelUnavailable",
    "active_session_count",
    "active_boot_image_migration",
    "begin_boot_image_migration",
    "claim_reconciler_run_lease",
    "claim_boot_image_migration_retirement",
    "claim_session_lease",
    "claim_vm_lease",
    "clear_missing_vm_if_current",
    "clear_vm_reconcile_lease_fields",
    "complete_boot_image_migration",
    "cutover_boot_image_migration",
    "drift_reasons",
    "expected_release_metadata",
    "heartbeat_session_lease",
    "mark_boot_image_migration_candidate_deleted",
    "reconcile_requested",
    "release_manifest_bytes",
    "record_boot_image_candidate",
    "record_boot_image_state_disks",
    "recover_missing_boot_image_candidate",
    "release_reconciler_run_lease",
    "request_vm_start",
    "renew_reconciler_run_lease",
    "renew_vm_lease",
    "release_session_lease",
    "retry_delay_seconds",
    "rollout_selected",
    "runtime_matches",
    "state_runtime_matches",
    "startup_wrapper",
    "update_vm_reconcile",
    "validate_release_manifest",
]
