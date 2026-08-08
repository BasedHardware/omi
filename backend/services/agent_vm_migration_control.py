"""Agent VM boot-image migration control and supersession fences."""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from database.store import get_document_store, sentinels
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from services.agent_vm_lifecycle import AgentVmRelease, DEFAULT_ZONE, clear_vm_reconcile_lease_fields
from utils.executors import db_executor, run_blocking

_MIGRATION_ID = re.compile(r"^[0-9a-f]{24}$")
PRODUCTION_MIGRATION_APPROVAL_POLICY = "state-preserving-v1"
PRODUCTION_MIGRATION_MIN_ADMISSION_SOAK_SECONDS = 10 * 60
PRODUCTION_MIGRATION_MIN_RETENTION_SECONDS = 7 * 24 * 60 * 60


def _store():
    return get_document_store()


@dataclass(frozen=True)
class BootImageMigrationPlan:
    """An explicit, environment-fenced plan for boot-image drift."""

    allowed_uids: frozenset[str]
    max_concurrency: int
    soak_seconds: int
    drain_running: bool = False
    retention_seconds: int | None = None


def boot_image_migration_plan(raw: Mapping[str, Any], release: AgentVmRelease) -> BootImageMigrationPlan | None:
    migration = raw.get("bootImageMigration")
    if not isinstance(migration, Mapping) or migration.get("enabled") is not True:
        return None
    environment = os.getenv("AGENT_VM_ENVIRONMENT", "").strip()
    project = os.getenv("GCE_PROJECT_ID", "").strip()
    if release.environment != environment:
        raise ValueError("boot-image migration release and job environments must match")
    if environment == "development":
        if project != "based-hardware-dev":
            raise ValueError("boot-image migration requires the approved development project")
    elif environment == "production":
        if project != "based-hardware":
            raise ValueError("boot-image migration requires the approved production project")
    else:
        raise ValueError("boot-image migration requires an approved environment")
    owners = migration.get("allowedUids")
    if not isinstance(owners, list) or not owners or not all(isinstance(uid, str) and uid.strip() for uid in owners):
        raise ValueError("boot-image migration requires a non-empty allowedUids list")
    max_concurrency = migration.get("maxConcurrency", 1)
    soak_seconds = migration.get("soakSeconds", 600)
    retention_seconds = migration.get("retentionSeconds", soak_seconds)
    drain_running = migration.get("drainRunning", False)
    if not isinstance(max_concurrency, int) or max_concurrency != 1:
        raise ValueError("boot-image migration maxConcurrency must be exactly 1")
    if not isinstance(soak_seconds, int) or soak_seconds < 60:
        raise ValueError("boot-image migration soakSeconds must be at least 60")
    if not isinstance(retention_seconds, int) or retention_seconds < soak_seconds:
        raise ValueError("boot-image migration retentionSeconds must be at least soakSeconds")
    if not isinstance(drain_running, bool):
        raise ValueError("boot-image migration drainRunning must be a boolean")
    normalized_owners = frozenset(uid.strip() for uid in owners)
    if environment == "production":
        if migration.get("approvalPolicy") != PRODUCTION_MIGRATION_APPROVAL_POLICY:
            raise ValueError("production boot-image migration requires the approved state-preserving policy")
        if len(normalized_owners) != 1:
            raise ValueError("production boot-image migration requires exactly one allowlisted canary owner")
        if soak_seconds < PRODUCTION_MIGRATION_MIN_ADMISSION_SOAK_SECONDS:
            raise ValueError("production boot-image migration requires at least ten minutes of admission soak")
        if retention_seconds < PRODUCTION_MIGRATION_MIN_RETENTION_SECONDS:
            raise ValueError("production boot-image migration requires at least seven days of rollback retention")
        if not drain_running:
            raise ValueError("production boot-image migration requires fenced running-owner drain")
    return BootImageMigrationPlan(
        normalized_owners,
        max_concurrency,
        soak_seconds,
        drain_running,
        retention_seconds,
    )


def boot_image_migration_id(uid: str, vm_name: str, instance_id: str, release_id: str) -> str:
    return hashlib.sha256(f"{uid}:{vm_name}:{instance_id}:{release_id}".encode()).hexdigest()[:24]


def boot_image_candidate_name(vm_name: str, migration_id: str) -> str:
    if not _MIGRATION_ID.fullmatch(migration_id):
        raise ValueError("boot-image migration id is invalid")
    suffix = f"-m-{migration_id[:12]}"
    return f"{vm_name[: 63 - len(suffix)]}{suffix}"


def state_disk_name(migration_id: str) -> str:
    return f"omi-agent-state-{migration_id[:16]}"


def source_clone_disk_name(migration_id: str) -> str:
    return f"omi-agent-source-{migration_id[:16]}"


def owner_disk_label(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()[:20]


def _owner_lease_matches(
    vm: Mapping[str, Any],
    *,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    instance_id: str,
    now: float,
) -> bool:
    reconcile = vm.get("reconcile")
    reconcile = reconcile if isinstance(reconcile, Mapping) else {}
    lease = reconcile.get("lease")
    return (
        vm.get("vmName") == vm_name
        and (vm.get("zone") or DEFAULT_ZONE) == zone
        and vm.get("authToken") == auth_token
        and str(vm.get("instanceId") or "") == instance_id
        and not bool(reconcile.get("startRequested"))
        and not bool(reconcile.get("drainRequested"))
        and isinstance(lease, Mapping)
        and lease.get("owner") == owner
        and float(lease.get("expiresAt", 0) or 0) > now
    )


def _supersede_failed_boot_image_migration_txn(
    tx: Any,
    deletion_path: str,
    user_path: str,
    migration_path: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    replacement_release_id: str,
    now: float,
) -> bool:
    deletion = tx.get(deletion_path)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    if account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    ):
        return False
    snapshot = tx.get(user_path)
    migration_snapshot = tx.get(migration_path)
    vm = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    migration = migration_snapshot.to_dict() if migration_snapshot.exists else None
    reconcile = vm.get("reconcile") if isinstance(vm, Mapping) else None
    old_instance_id = str(migration.get("oldInstanceId") or "") if isinstance(migration, Mapping) else ""
    if (
        not isinstance(vm, dict)
        or not isinstance(migration, dict)
        or not isinstance(reconcile, Mapping)
        or migration.get("migrationId") != migration_id
        or migration.get("state") != "candidate_deleted"
        or not isinstance(migration.get("candidateDeletedAt"), (int, float))
        or migration.get("targetRelease") == replacement_release_id
        or migration.get("oldVmName") != vm_name
        or migration.get("oldAuthToken") != auth_token
        or not old_instance_id
        or reconcile.get("durableMigration") != migration_id
        or not _owner_lease_matches(
            vm,
            vm_name=vm_name,
            zone=zone,
            auth_token=auth_token,
            owner=owner,
            instance_id=old_instance_id,
            now=now,
        )
    ):
        return False
    owner_update: dict[str, Any] = {
        "agentVm.reconcile.durableMigration": sentinels.DELETE,
        "agentVm.reconcile.state": "ready",
        "agentVm.reconcile.retryCount": 0,
        "agentVm.reconcile.retryAt": sentinels.DELETE,
        "agentVm.reconcile.lastError": sentinels.DELETE,
        "agentVm.reconcile.driftReasons": sentinels.DELETE,
    }
    owner_update.update({f"agentVm.reconcile.{key}": value for key, value in clear_vm_reconcile_lease_fields().items()})
    tx.update(user_path, owner_update)
    tx.update(
        migration_path,
        {
            "state": "superseded",
            "supersededAt": now,
            "supersededByRelease": replacement_release_id,
            "updatedAt": now,
        },
    )
    return True


def supersede_failed_boot_image_migration(
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    migration_id: str,
    replacement_release_id: str,
    now: float | None = None,
) -> bool:
    now = time.time() if now is None else now
    return bool(
        _store().run_transaction(
            lambda tx: _supersede_failed_boot_image_migration_txn(
                tx,
                f"account_deletions/{uid}",
                f"users/{uid}",
                f"users/{uid}/agentVmMigrations/{migration_id}",
                vm_name,
                zone,
                auth_token,
                owner,
                migration_id,
                replacement_release_id,
                now,
            )
        )
    )


async def supersede_rolled_back_boot_image_migration(
    *,
    uid: str,
    vm_name: str,
    zone: str,
    auth_token: str,
    owner: str,
    old_instance_id: str,
    replacement_release_id: str,
    recovery_journal: Mapping[str, Any],
    owner_label: str,
    cleanup_context: MutableMapping[str, str],
    rollback: Callable[[Mapping[str, str]], Awaitable[bool]],
) -> str | None:
    """Revalidate and supersede a failed journal from an older release."""
    if recovery_journal.get("targetRelease") == replacement_release_id:
        return None
    migration_id = str(recovery_journal.get("migrationId") or "")
    candidate_name = str(recovery_journal.get("candidateVmName") or "")
    candidate_id = str(recovery_journal.get("candidateInstanceId") or "")
    state_disk_name_value = str(recovery_journal.get("stateDiskName") or "")
    state_disk_id = str(recovery_journal.get("stateDiskId") or "")
    state_disk_reused = recovery_journal.get("stateDiskReused") is True
    source_clone_name_value = str(recovery_journal.get("sourceCloneDiskName") or "")
    source_clone_id = str(recovery_journal.get("sourceCloneDiskId") or "")
    if (
        recovery_journal.get("state") != "candidate_deleted"
        or not _MIGRATION_ID.fullmatch(migration_id)
        or recovery_journal.get("oldVmName") != vm_name
        or str(recovery_journal.get("oldInstanceId") or "") != old_instance_id
        or not candidate_name
        or not candidate_id
        or not state_disk_name_value
        or not state_disk_id
        or (not state_disk_reused and (not source_clone_name_value or not source_clone_id))
    ):
        raise RuntimeError("durable boot-image migration journal is not recoverable by the active release")
    cleanup_context.update(
        {
            "vmName": candidate_name,
            "instanceId": candidate_id,
            "oldInstanceId": old_instance_id,
            "migrationId": migration_id,
            "stateDiskName": state_disk_name_value,
            "stateDiskId": state_disk_id,
            "stateDiskReused": "true" if state_disk_reused else "false",
            "ownerLabel": owner_label,
            "sourceCloneDiskName": source_clone_name_value,
            "sourceCloneDiskId": source_clone_id,
        }
    )
    if not await rollback(cleanup_context):
        raise RuntimeError("rolled-back boot-image migration provider state is ambiguous")
    superseded = await run_blocking(
        db_executor,
        supersede_failed_boot_image_migration,
        uid,
        vm_name,
        zone,
        auth_token,
        owner,
        migration_id,
        replacement_release_id,
    )
    cleanup_context.clear()
    return "superseded" if superseded else "stale"


__all__ = [
    "BootImageMigrationPlan",
    "PRODUCTION_MIGRATION_APPROVAL_POLICY",
    "PRODUCTION_MIGRATION_MIN_ADMISSION_SOAK_SECONDS",
    "PRODUCTION_MIGRATION_MIN_RETENTION_SECONDS",
    "boot_image_candidate_name",
    "boot_image_migration_id",
    "boot_image_migration_plan",
    "owner_disk_label",
    "source_clone_disk_name",
    "state_disk_name",
    "supersede_failed_boot_image_migration",
    "supersede_rolled_back_boot_image_migration",
]
