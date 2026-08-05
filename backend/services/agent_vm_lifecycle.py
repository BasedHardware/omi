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
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
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
        or reconcile.get("state") in {"draining", "deferred"}
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
    uid: str,
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
    uid: str, vm_name: str, auth_token: str, owner: str, release_id: str | None = None, now: float | None = None
) -> bool:
    now = time.time() if now is None else now
    client = get_firestore_client()
    return bool(
        _claim_vm_lease_txn(
            client.transaction(),
            client.collection("account_deletions").document(uid),
            client.collection("users").document(uid),
            uid,
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


def clear_vm_reconcile_lease_fields() -> dict[str, Any]:
    return {
        "lease": DELETE_FIELD,
        "startRequested": DELETE_FIELD,
        "startRequestedAt": DELETE_FIELD,
        "drainRequested": DELETE_FIELD,
        "drainRequestedAt": DELETE_FIELD,
    }


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
        for _ in range(60):
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

    async def stop(self, vm_name: str) -> None:
        await self._mutate("POST", self.instance_url(vm_name) + "/stop")

    async def start(self, vm_name: str) -> None:
        await self._mutate("POST", self.instance_url(vm_name) + "/start")

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

    async def wait_for_runtime(self, ip: str, auth_token: str, release: AgentVmRelease, timeout: int = 300) -> None:
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
                    ):
                        return
                except (httpx.HTTPError, ValueError):
                    pass
                await asyncio.sleep(5)
        raise RuntimeError("Agent VM did not report the activated release before the readiness timeout")

    async def runtime_is_current(self, ip: str, auth_token: str, release: AgentVmRelease) -> bool:
        runtime_url = self._trusted_runtime_url(ip)
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    runtime_url,
                    headers={"Authorization": f"Bearer {auth_token}"},
                )
            payload = response.json()
            return response.status_code == 200 and isinstance(payload, Mapping) and runtime_matches(payload, release)
        except (httpx.HTTPError, ValueError):
            return False


__all__ = [
    "AgentVmLeaseLost",
    "AgentVmNotFound",
    "AgentVmRelease",
    "AgentVmReleaseError",
    "DEFAULT_ZONE",
    "GceAgentVmClient",
    "LEASE_HEARTBEAT_SECONDS",
    "RECONCILER_SCHEMA_VERSION",
    "TrustedAgentVmHealthChannelUnavailable",
    "active_session_count",
    "claim_reconciler_run_lease",
    "claim_session_lease",
    "claim_vm_lease",
    "clear_vm_reconcile_lease_fields",
    "drift_reasons",
    "expected_release_metadata",
    "heartbeat_session_lease",
    "reconcile_requested",
    "release_manifest_bytes",
    "release_reconciler_run_lease",
    "request_vm_start",
    "renew_reconciler_run_lease",
    "renew_vm_lease",
    "release_session_lease",
    "retry_delay_seconds",
    "rollout_selected",
    "runtime_matches",
    "startup_wrapper",
    "update_vm_reconcile",
    "validate_release_manifest",
]
