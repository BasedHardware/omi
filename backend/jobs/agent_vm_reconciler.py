"""Cloud Run Job entrypoint for declarative Agent VM fleet convergence.

The job is safe to run from Cloud Scheduler every five minutes.  A Firestore
lease prevents overlapping executions, per-owner leases prevent duplicate GCE
mutations, and session leases turn an image/service-account migration into a
drain rather than an unsolicited disconnect.  The default rollout is 100%;
operators can stage a release with ``AGENT_VM_ROLLOUT_TARGET_PERCENT`` or the
manifest's ``rollout.targetPercent``.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import firebase_admin
from google.cloud import storage
from google.cloud.firestore import DELETE_FIELD
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import get_firestore_client
from services.agent_vm_lifecycle import (
    DEFAULT_ZONE,
    LEASE_HEARTBEAT_SECONDS,
    AgentVmLeaseLost,
    AgentVmRelease,
    GceAgentVmClient,
    STATE_DISK_DEVICE_NAME,
    STATE_SOURCE_DEVICE_NAME,
    active_session_count,
    begin_boot_image_migration,
    claim_boot_image_migration_retirement,
    claim_reconciler_run_lease,
    claim_vm_lease,
    clear_missing_vm_if_current,
    clear_vm_reconcile_lease_fields,
    complete_boot_image_migration,
    cutover_boot_image_migration,
    drift_reasons,
    mark_boot_image_migration_candidate_deleted,
    recover_missing_boot_image_candidate,
    release_reconciler_run_lease,
    renew_reconciler_run_lease,
    renew_vm_lease,
    record_boot_image_candidate,
    record_boot_image_state_disks,
    retry_delay_seconds,
    rollout_selected,
    update_vm_reconcile,
    validate_release_manifest,
)
from utils.env_loader import firebase_admin_options
from utils.observability.fallback import record_fallback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROLLOUT_PHASES: dict[str, tuple[int, int, str | None]] = {
    "sentinel": (1, 1, "canary"),
    "canary": (5, 2, "quarter"),
    "quarter": (25, 5, "remainder"),
    "remainder": (100, 5, None),
}
ROLLOUT_STABLE_RUNS = 3
OWNER_DISCOVERY_LIMIT = 10_000
OWNER_FALLBACK_SCAN_LIMIT = 1_000
FAILED_JOB_STATES = {"retry", "quarantined", "missing", "stale", "recreate_required"}
DEFAULT_MISSING_CLEANUP_GRACE_SECONDS = 24 * 60 * 60
MIN_MISSING_CLEANUP_GRACE_SECONDS = 60
_IMMUTABLE_BOOT_IMAGE = re.compile(r"^projects/[^/]+/global/images/[^/]+$")
_MIGRATION_ID = re.compile(r"^[0-9a-f]{24}$")


@dataclass(frozen=True)
class ReconcileResult:
    uid: str
    state: str
    detail: str = ""


@dataclass(frozen=True)
class BootImageMigrationPlan:
    """An explicit, dev-only plan for replacing stopped boot-image-drift VMs.

    This plan deliberately does not inherit the normal release rollout.  A
    release publication must never become a destructive migration merely
    because it happens to carry a new immutable boot image.
    """

    allowed_uids: frozenset[str]
    max_concurrency: int
    soak_seconds: int


def _boot_image_migration_plan(raw: Mapping[str, Any], release: AgentVmRelease) -> BootImageMigrationPlan | None:
    """Return a safe replacement plan, or ``None`` when migration is disabled.

    The plan lives in a separately named manifest section and is accepted only
    for development.  Production is hard-disabled in code even if a manifest
    is malformed or accidentally promoted with this section present.
    """
    migration = raw.get("bootImageMigration")
    if not isinstance(migration, Mapping) or migration.get("enabled") is not True:
        return None
    if release.environment != "development" or os.getenv("AGENT_VM_ENVIRONMENT", "").strip() != "development":
        raise ValueError("boot-image migration is development-only")
    if os.getenv("GCE_PROJECT_ID", "").strip() != "based-hardware-dev":
        raise ValueError("boot-image migration requires the approved development project")
    owners = migration.get("allowedUids")
    if not isinstance(owners, list) or not owners or not all(isinstance(uid, str) and uid.strip() for uid in owners):
        raise ValueError("boot-image migration requires a non-empty allowedUids list")
    max_concurrency = migration.get("maxConcurrency", 1)
    soak_seconds = migration.get("soakSeconds", 600)
    if not isinstance(max_concurrency, int) or max_concurrency != 1:
        raise ValueError("boot-image migration maxConcurrency must be exactly 1")
    if not isinstance(soak_seconds, int) or soak_seconds < 60:
        raise ValueError("boot-image migration soakSeconds must be at least 60")
    return BootImageMigrationPlan(frozenset(owners), max_concurrency, soak_seconds)


def _boot_image_migration_id(uid: str, vm_name: str, instance_id: str, release_id: str) -> str:
    return hashlib.sha256(f"{uid}:{vm_name}:{instance_id}:{release_id}".encode()).hexdigest()[:24]


def _boot_image_candidate_name(vm_name: str, migration_id: str) -> str:
    if not _MIGRATION_ID.fullmatch(migration_id):
        raise ValueError("boot-image migration id is invalid")
    suffix = f"-m-{migration_id[:12]}"
    # GCE names are limited to 63 characters and the predecessor identity is
    # also recorded independently in the durable migration journal.
    return f"{vm_name[: 63 - len(suffix)]}{suffix}"


def _disk_attachment(instance: Mapping[str, Any], device_name: str) -> Mapping[str, Any] | None:
    disks = instance.get("disks")
    if not isinstance(disks, list):
        return None
    return next(
        (
            disk
            for disk in disks
            if isinstance(disk, Mapping) and disk.get("deviceName") == device_name and disk.get("boot") is not True
        ),
        None,
    )


def _boot_disk_attachment(instance: Mapping[str, Any]) -> Mapping[str, Any] | None:
    disks = instance.get("disks")
    if not isinstance(disks, list):
        return None
    return next((disk for disk in disks if isinstance(disk, Mapping) and disk.get("boot") is True), None)


def _disk_name(source: Any) -> str:
    if not isinstance(source, str) or not source.strip():
        raise RuntimeError("Agent VM disk source is unavailable")
    name = source.rstrip("/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?", name):
        raise RuntimeError("Agent VM disk source name is invalid")
    return name


def _state_disk_name(migration_id: str) -> str:
    return f"omi-agent-state-{migration_id[:16]}"


def _source_clone_disk_name(migration_id: str) -> str:
    return f"omi-agent-source-{migration_id[:16]}"


def _owner_disk_label(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()[:20]


def _disk_source(project: str, zone: str, disk_name: str) -> str:
    return f"projects/{project}/zones/{zone}/disks/{disk_name}"


def _init_firebase() -> None:
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(
            firebase_admin.credentials.Certificate(json.loads(service_account_json)),
            options=firebase_admin_options(),
        )
    else:
        firebase_admin.initialize_app(options=firebase_admin_options())


def _read_gcs_uri(uri: str) -> bytes:
    if not uri.startswith("gs://"):
        raise ValueError("Agent VM active release must use a gs:// URI")
    bucket_name, _, blob_name = uri[5:].partition("/")
    if not bucket_name or not blob_name:
        raise ValueError("Agent VM release URI must contain a bucket and object")
    return storage.Client().bucket(bucket_name).blob(blob_name).download_as_bytes()


def load_active_release() -> tuple[AgentVmRelease, dict[str, Any]]:
    uri = os.getenv("AGENT_VM_ACTIVE_RELEASE_URI")
    if not uri:
        bucket = os.getenv("AGENT_GCS_BUCKET")
        if not bucket:
            raise RuntimeError("AGENT_VM_ACTIVE_RELEASE_URI or AGENT_GCS_BUCKET is required")
        uri = f"gs://{bucket}/agent-vm/releases/active.json"
    raw = json.loads(_read_gcs_uri(uri))
    if not isinstance(raw, dict):
        raise ValueError("active Agent VM release must be a JSON object")
    release = validate_release_manifest(raw)
    _requested_rollout_phase(raw, release.environment)
    return release, raw


def _bounded_limit(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _owner_from_snapshot(snapshot: Any) -> tuple[str, dict[str, Any]] | None:
    data = snapshot.to_dict() or {}
    vm = data.get("agentVm")
    if isinstance(vm, dict) and isinstance(vm.get("vmName"), str) and isinstance(vm.get("authToken"), str):
        return str(snapshot.id), vm
    return None


def _owners() -> list[tuple[str, dict[str, Any]]]:
    """Discover owners through the existing nested user field, with a bounded legacy fallback.

    The targeted query uses Firestore's automatic single-field index and reads
    Agent VM owners rather than every user.  Older fakes/emulators that cannot
    execute it may use the bounded scan; saturation fails the run so owners are
    never silently omitted.
    """
    users = get_firestore_client().collection("users")
    owner_limit = _bounded_limit("AGENT_VM_OWNER_DISCOVERY_LIMIT", OWNER_DISCOVERY_LIMIT)
    try:
        snapshots = list(users.where(filter=FieldFilter("agentVm.vmName", ">=", "")).limit(owner_limit + 1).stream())
    except Exception as exc:
        fallback_limit = _bounded_limit("AGENT_VM_OWNER_FALLBACK_SCAN_LIMIT", OWNER_FALLBACK_SCAN_LIMIT)
        record_fallback(
            component="firestore_read",
            from_mode="agent_vm_owner_query",
            to_mode="bounded_users_scan",
            reason="capability_mismatch",
            outcome="degraded",
            log=logger,
        )
        logger.info("Bounded Agent VM owner compatibility scan limit: %d", fallback_limit)
        snapshots = list(users.limit(fallback_limit + 1).stream())
        if len(snapshots) > fallback_limit:
            raise RuntimeError(
                "bounded Agent VM owner compatibility scan exhausted; targeted Firestore query is required"
            ) from exc
    if len(snapshots) > owner_limit:
        raise RuntimeError(f"Agent VM owner discovery exceeded configured limit {owner_limit}")
    return [owner for snapshot in snapshots if (owner := _owner_from_snapshot(snapshot)) is not None]


def _requested_rollout_phase(raw: Mapping[str, Any], environment: str) -> str:
    rollout = raw.get("rollout")
    if rollout is not None and not isinstance(rollout, Mapping):
        raise ValueError("rollout must be an object")
    rollout_map = rollout if isinstance(rollout, Mapping) else {}
    requested = rollout_map.get("phase") or ("sentinel" if environment == "production" else "remainder")
    if not isinstance(requested, str) or requested not in ROLLOUT_PHASES:
        raise ValueError(f"unsupported Agent VM rollout phase: {requested!r}")
    return requested


def _rollout_spec(raw: Mapping[str, Any], phase: str) -> tuple[int, int]:
    if phase not in ROLLOUT_PHASES:
        raise ValueError(f"unsupported Agent VM rollout phase: {phase!r}")
    rollout = raw.get("rollout")
    rollout_map = rollout if isinstance(rollout, Mapping) else {}
    phase_target, phase_concurrency, _ = ROLLOUT_PHASES[phase]
    target = os.getenv(
        "AGENT_VM_ROLLOUT_TARGET_PERCENT",
        rollout_map.get("targetPercent", phase_target),
    )
    concurrency = os.getenv(
        "AGENT_VM_RECONCILER_MAX_CONCURRENCY",
        rollout_map.get("maxConcurrency", phase_concurrency),
    )
    try:
        target_percent = max(0, min(100, int(target)))
        max_concurrency = max(1, min(50, int(concurrency)))
    except (TypeError, ValueError) as exc:
        raise ValueError("rollout targetPercent and maxConcurrency must be integers") from exc
    return target_percent, max_concurrency


def _rollout_phase(environment: str, release_id: str, raw: Mapping[str, Any], *, persist: bool = True) -> str:
    client = get_firestore_client()
    ref = client.collection("agent_vm_rollouts").document(environment)
    snapshot = ref.get()
    current = snapshot.to_dict() if snapshot.exists else {}
    current_map = current if isinstance(current, dict) else {}
    if current_map.get("releaseId") == release_id:
        current_phase = current_map.get("phase")
        if current_phase not in ROLLOUT_PHASES:
            raise ValueError(f"stored Agent VM rollout phase is invalid: {current_phase!r}")
        return str(current_phase)
    phase = _requested_rollout_phase(raw, environment)
    if persist:
        ref.set(
            {"releaseId": release_id, "phase": phase, "successfulRuns": 0, "updatedAt": time.time()},
            merge=True,
        )
    return phase


def _advance_rollout(
    environment: str,
    release_id: str,
    phase: str,
    results: Sequence[ReconcileResult],
    selected_count: int,
) -> None:
    client = get_firestore_client()
    ref = client.collection("agent_vm_rollouts").document(environment)
    snapshot = ref.get()
    current = snapshot.to_dict() if snapshot.exists else {}
    current_map = current if isinstance(current, dict) else {}
    if current_map.get("releaseId") != release_id or current_map.get("phase") != phase:
        return
    successful = bool(results) and selected_count == len(results) and all(result.state == "ready" for result in results)
    runs = int(current_map.get("successfulRuns", 0) or 0) + 1 if successful else 0
    next_phase = ROLLOUT_PHASES[phase][2]
    if next_phase and runs >= ROLLOUT_STABLE_RUNS:
        phase = next_phase
        runs = 0
    ref.set(
        {
            "releaseId": release_id,
            "phase": phase,
            "successfulRuns": runs,
            "lastRunAt": time.time(),
            "lastRunStates": {
                state: sum(result.state == state for result in results)
                for state in {result.state for result in results}
            },
        },
        merge=True,
    )


def _select_rollout_owners(
    owners: Sequence[tuple[str, dict[str, Any]]], release_id: str, target_percent: int
) -> list[tuple[str, dict[str, Any]]]:
    selected = [(uid, vm) for uid, vm in owners if rollout_selected(uid, release_id, target_percent)]
    if owners and target_percent > 0 and not selected:
        # A percentage cohort can round to zero in a small fleet.  Select one
        # deterministic sentinel so advancement always has observed VM evidence.
        selected = [min(owners, key=lambda owner: hashlib.sha256(f"{release_id}:{owner[0]}".encode()).digest())]
    return selected


def _select_reconcile_owners(
    owners: Sequence[tuple[str, dict[str, Any]]], release_id: str, target_percent: int
) -> list[tuple[str, dict[str, Any]]]:
    """Add demanded or terminal-cleanup work to the rollout cohort without duplicates."""
    selected = _select_rollout_owners(owners, release_id, target_percent)
    selected_uids = {uid for uid, _ in selected}
    selected.extend(
        (uid, vm)
        for uid, vm in owners
        if uid not in selected_uids and (_start_requested(vm) or _missing_cleanup_candidate(vm))
    )
    return selected


def _start_requested(vm: Mapping[str, Any]) -> bool:
    reconcile = vm.get("reconcile")
    return isinstance(reconcile, Mapping) and bool(reconcile.get("startRequested"))


def _missing_cleanup_candidate(vm: Mapping[str, Any]) -> bool:
    reconcile = vm.get("reconcile")
    return isinstance(reconcile, Mapping) and reconcile.get("state") == "missing"


def _missing_cleanup_grace_seconds() -> int:
    raw = os.getenv("AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_MISSING_CLEANUP_GRACE_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS must be an integer") from exc
    if value < MIN_MISSING_CLEANUP_GRACE_SECONDS:
        raise ValueError(f"AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS must be at least {MIN_MISSING_CLEANUP_GRACE_SECONDS}")
    return value


def _canonical_image_ref(value: str) -> str:
    marker = "/compute/v1/"
    return value.split(marker, 1)[1] if marker in value else value.lstrip("/")


async def _boot_image_drift(
    api: GceAgentVmClient, instance: Mapping[str, Any], release: AgentVmRelease
) -> tuple[str, str] | None:
    desired = _canonical_image_ref(release.boot_image)
    if not _IMMUTABLE_BOOT_IMAGE.fullmatch(desired):
        return "boot_image_manifest_not_immutable", "unknown"
    disks = instance.get("disks")
    boot_disk = (
        next(
            (disk for disk in disks if isinstance(disk, Mapping) and disk.get("boot") is True),
            None,
        )
        if isinstance(disks, list)
        else None
    )
    source = boot_disk.get("source") if isinstance(boot_disk, Mapping) else None
    if not isinstance(source, str) or not source:
        return "boot_image_source_unverifiable", "unknown"
    if not source.startswith("http"):
        source = f"https://compute.googleapis.com/compute/v1/{source.lstrip('/')}"
    response = await api.request("GET", source)
    response.raise_for_status()
    payload = response.json()
    actual_raw = payload.get("sourceImage") if isinstance(payload, Mapping) else None
    if not isinstance(actual_raw, str) or not actual_raw:
        return "boot_image_source_unverifiable", "unknown"
    actual = _canonical_image_ref(actual_raw)
    if actual != desired:
        return "boot_image_recreate_required", actual
    return None


async def _active_state_disk_info(
    api: GceAgentVmClient,
    uid: str,
    vm: Mapping[str, Any],
    instance: Mapping[str, Any],
) -> dict[str, str] | None:
    """Validate the active owner state disk and repair its auto-delete policy."""
    attachment = _disk_attachment(instance, STATE_DISK_DEVICE_NAME)
    expected = vm.get("stateDisk")
    if attachment is None:
        if isinstance(expected, Mapping):
            raise RuntimeError("active Agent VM lost its journaled state disk attachment")
        return None
    disk_name = _disk_name(attachment.get("source"))
    disk = await api.get_disk(disk_name)
    if disk is None:
        raise RuntimeError("active Agent VM state disk is unavailable")
    disk_id = str(disk.get("id") or "")
    labels = disk.get("labels")
    expected_name = expected.get("diskName") if isinstance(expected, Mapping) else None
    expected_id = expected.get("diskId") if isinstance(expected, Mapping) else None
    users = disk.get("users")
    expected_user = api.instance_url(str(vm["vmName"])).split("https://compute.googleapis.com/compute/v1/")[-1]
    normalized_users = [str(user).split("/compute/v1/")[-1] for user in users] if isinstance(users, list) else []
    if (
        not disk_id
        or (expected_name and expected_name != disk_name)
        or (expected_id and str(expected_id) != disk_id)
        or not isinstance(labels, Mapping)
        or labels.get("omi-agent-role") != "state"
        or labels.get("omi-agent-owner") != _owner_disk_label(uid)
        or normalized_users != [expected_user]
    ):
        raise RuntimeError("active Agent VM state disk identity is ambiguous")
    if attachment.get("autoDelete") is not True:
        await api.set_disk_auto_delete(str(vm["vmName"]), STATE_DISK_DEVICE_NAME, True)
    return {"deviceName": STATE_DISK_DEVICE_NAME, "diskName": disk_name, "diskId": disk_id}


async def _rollback_failed_boot_image_candidate(
    api: GceAgentVmClient,
    uid: str,
    predecessor_name: str,
    context: Mapping[str, str],
) -> bool:
    """Restore the predecessor ownership boundary after any pre-cutover failure.

    The context is populated before the first detach. Every provider mutation
    remains fenced by numeric IDs plus migration/owner labels, so a partial
    retry cannot attach or delete a same-named foreign resource.
    """
    migration_id = context.get("migrationId", "")
    candidate_name = context.get("vmName", "")
    candidate_id = context.get("instanceId", "")
    old_instance_id = context.get("oldInstanceId", "")
    state_disk_name = context.get("stateDiskName", "")
    state_disk_id = context.get("stateDiskId", "")
    owner_label = context.get("ownerLabel", "")
    reused = context.get("stateDiskReused") == "true"
    if not all((migration_id, candidate_name, old_instance_id, state_disk_name, state_disk_id, owner_label)):
        return False

    candidate = await api.get_instance(candidate_name)
    if candidate is not None:
        labels = candidate.get("labels")
        observed_id = str(candidate.get("id") or "")
        if (
            not observed_id
            or (candidate_id and candidate_id != observed_id)
            or not isinstance(labels, Mapping)
            or labels.get("omi-agent-migration") != migration_id
            or labels.get("omi-agent-predecessor") != old_instance_id
        ):
            return False
        candidate_id = observed_id
        if not await api.delete_replacement(candidate_name, candidate_id, migration_id):
            return False

    state_disk = await api.get_disk(state_disk_name)
    if state_disk is None:
        return not reused
    labels = state_disk.get("labels")
    if (
        str(state_disk.get("id") or "") != state_disk_id
        or not isinstance(labels, Mapping)
        or labels.get("omi-agent-migration") != migration_id
        or labels.get("omi-agent-role") != "state"
        or labels.get("omi-agent-owner") != owner_label
    ):
        return False
    users = state_disk.get("users")
    if isinstance(users, list) and users:
        return False

    if reused:
        predecessor = await api.get_instance(predecessor_name)
        predecessor_labels = predecessor.get("labels") if isinstance(predecessor, Mapping) else None
        if (
            not isinstance(predecessor, Mapping)
            or str(predecessor.get("id") or "") != old_instance_id
            or not isinstance(predecessor_labels, Mapping)
            or predecessor_labels.get("omi-agent-migration") != migration_id
        ):
            return False
        attachment = _disk_attachment(predecessor, STATE_DISK_DEVICE_NAME)
        if attachment is None:
            await api.attach_disk(
                predecessor_name,
                _disk_source(api.project, api.zone, state_disk_name),
                auto_delete=True,
            )
        elif _disk_name(attachment.get("source")) != state_disk_name:
            return False
        elif attachment.get("autoDelete") is not True:
            await api.set_disk_auto_delete(predecessor_name, STATE_DISK_DEVICE_NAME, True)
    elif not await api.delete_disk(state_disk_name, state_disk_id, migration_id, "state", owner_label):
        return False

    source_clone_name = context.get("sourceCloneDiskName", "")
    source_clone_id = context.get("sourceCloneDiskId", "")
    if (
        source_clone_name
        and source_clone_id
        and not await api.delete_disk(
            source_clone_name,
            source_clone_id,
            migration_id,
            "source",
            owner_label,
        )
    ):
        return False
    return True


async def _replace_stopped_boot_image_drift(
    uid: str,
    vm: Mapping[str, Any],
    instance: Mapping[str, Any],
    release: AgentVmRelease,
    plan: BootImageMigrationPlan,
    *,
    owner: str,
    api: GceAgentVmClient,
    cleanup_context: dict[str, str] | None = None,
) -> ReconcileResult:
    """Create and cut over a stopped, explicitly allowlisted predecessor.

    Old instances are tagged before candidate creation and deliberately remain
    stopped after cutover.  A later reconciliation may retire that immutable,
    ID-fenced predecessor after its soak period; a failed candidate never
    changes the active owner pointer.
    """
    vm_name = str(vm["vmName"])
    zone = str(vm.get("zone") or DEFAULT_ZONE)
    auth_token = str(vm["authToken"])
    if uid not in plan.allowed_uids:
        return ReconcileResult(uid, "recreate_required", "boot-image migration is not allowlisted for this owner")
    if str(instance.get("status") or "") not in {"TERMINATED", "STOPPED"} or vm.get("status") != "stopped":
        return ReconcileResult(uid, "recreate_required", "boot-image migration requires an already stopped VM")
    active = await asyncio.to_thread(active_session_count, uid, vm_name)
    if active:
        return ReconcileResult(uid, "recreate_required", f"{active} active session(s) block boot-image migration")
    old_instance_id = str(instance.get("id") or "")
    if not old_instance_id:
        return ReconcileResult(uid, "recreate_required", "predecessor instance identity is unavailable")
    migration_id = _boot_image_migration_id(uid, vm_name, old_instance_id, release.release_id)
    candidate_name = _boot_image_candidate_name(vm_name, migration_id)
    existing_state_attachment = _disk_attachment(instance, STATE_DISK_DEVICE_NAME)
    state_disk_name = (
        _disk_name(existing_state_attachment.get("source"))
        if isinstance(existing_state_attachment, Mapping)
        else _state_disk_name(migration_id)
    )
    state_disk_reused = existing_state_attachment is not None
    source_clone_name = "" if state_disk_reused else _source_clone_disk_name(migration_id)
    candidate_token = secrets.token_urlsafe(32)
    migration = {
        "migrationId": migration_id,
        "oldVmName": vm_name,
        "oldZone": zone,
        "oldAuthToken": auth_token,
        "oldInstanceId": old_instance_id,
        "candidateVmName": candidate_name,
        "candidateAuthToken": candidate_token,
        "targetRelease": release.release_id,
        "targetBootImage": release.boot_image,
        "soakSeconds": plan.soak_seconds,
        "stateDiskName": state_disk_name,
        "stateDiskReused": state_disk_reused,
        "sourceCloneDiskName": source_clone_name,
    }
    journal = await asyncio.to_thread(
        begin_boot_image_migration, uid, vm_name, zone, auth_token, owner, migration_id, migration
    )
    if journal is None:
        return ReconcileResult(uid, "stale", "boot-image migration claim fence changed")
    candidate_token = journal.get("candidateAuthToken") if isinstance(journal.get("candidateAuthToken"), str) else ""
    if not candidate_token:
        raise RuntimeError("boot-image migration journal has no candidate token")
    state_disk_name = str(journal.get("stateDiskName") or "")
    state_disk_reused = journal.get("stateDiskReused") is True
    source_clone_name = str(journal.get("sourceCloneDiskName") or "")
    if not state_disk_name or (not state_disk_reused and not source_clone_name):
        raise RuntimeError("boot-image migration journal has no durable state disk plan")
    if cleanup_context is not None and journal.get("stateDiskId"):
        cleanup_context.update(
            {
                "vmName": candidate_name,
                "instanceId": str(journal.get("candidateInstanceId") or ""),
                "oldInstanceId": old_instance_id,
                "migrationId": migration_id,
                "stateDiskName": state_disk_name,
                "stateDiskId": str(journal["stateDiskId"]),
                "stateDiskReused": "true" if state_disk_reused else "false",
                "ownerLabel": _owner_disk_label(uid),
                "sourceCloneDiskName": source_clone_name,
                "sourceCloneDiskId": str(journal.get("sourceCloneDiskId") or ""),
            }
        )
    await api.set_migration_labels(vm_name, instance, migration_id)
    candidate = await api.get_instance(candidate_name)
    if candidate is None:
        if not await asyncio.to_thread(
            recover_missing_boot_image_candidate, uid, vm_name, zone, auth_token, owner, migration_id
        ):
            return ReconcileResult(uid, "stale", "missing candidate recovery fence changed")
        owner_label = _owner_disk_label(uid)
        state_disk = await api.get_disk(state_disk_name)
        if state_disk_reused:
            if state_disk is None:
                raise RuntimeError("journaled Agent VM state disk is missing")
            labels = state_disk.get("labels")
            expected_state = vm.get("stateDisk")
            expected_state_id = expected_state.get("diskId") if isinstance(expected_state, Mapping) else None
            users = state_disk.get("users")
            expected_user = api.instance_url(vm_name).split("https://compute.googleapis.com/compute/v1/")[-1]
            normalized_users = (
                [str(user).split("/compute/v1/")[-1] for user in users] if isinstance(users, list) else []
            )
            if (
                str(state_disk.get("id") or "") == ""
                or (expected_state_id and str(state_disk.get("id")) != str(expected_state_id))
                or not isinstance(labels, Mapping)
                or labels.get("omi-agent-role") != "state"
                or labels.get("omi-agent-owner") != owner_label
                or any(user != expected_user for user in normalized_users)
            ):
                raise RuntimeError("journaled Agent VM state disk identity is ambiguous")
            if cleanup_context is not None:
                cleanup_context.update(
                    {
                        "vmName": candidate_name,
                        "instanceId": "",
                        "oldInstanceId": old_instance_id,
                        "migrationId": migration_id,
                        "stateDiskName": state_disk_name,
                        "stateDiskId": str(state_disk["id"]),
                        "stateDiskReused": "true",
                        "ownerLabel": owner_label,
                        "sourceCloneDiskName": "",
                        "sourceCloneDiskId": "",
                    }
                )
            if existing_state_attachment is not None:
                await api.set_disk_auto_delete(vm_name, STATE_DISK_DEVICE_NAME, False)
                await api.detach_disk(vm_name, STATE_DISK_DEVICE_NAME)
        else:
            state_disk = await api.create_disk(
                state_disk_name,
                migration_id=migration_id,
                role="state",
                owner_hash=owner_label,
            )
        if state_disk is None:
            raise RuntimeError("Agent VM state disk is unavailable")
        if cleanup_context is not None and not state_disk_reused:
            cleanup_context.update(
                {
                    "vmName": candidate_name,
                    "instanceId": "",
                    "oldInstanceId": old_instance_id,
                    "migrationId": migration_id,
                    "stateDiskName": state_disk_name,
                    "stateDiskId": str(state_disk["id"]),
                    "stateDiskReused": "false",
                    "ownerLabel": owner_label,
                    "sourceCloneDiskName": source_clone_name,
                    "sourceCloneDiskId": "",
                }
            )
        source_clone: Mapping[str, Any] | None = None
        if not state_disk_reused:
            boot_attachment = _boot_disk_attachment(instance)
            if not isinstance(boot_attachment, Mapping):
                raise RuntimeError("predecessor boot disk is unavailable for state migration")
            boot_source = boot_attachment.get("source")
            if not isinstance(boot_source, str) or not boot_source:
                raise RuntimeError("predecessor boot disk source is unavailable")
            source_clone = await api.create_disk(
                source_clone_name,
                migration_id=migration_id,
                role="source",
                owner_hash=owner_label,
                source_disk=boot_source,
            )
            if cleanup_context is not None:
                cleanup_context["sourceCloneDiskId"] = str(source_clone["id"])
        prepared_state = {
            "stateDiskName": state_disk_name,
            "stateDiskId": str(state_disk.get("id") or ""),
            "stateDiskReused": state_disk_reused,
            "sourceCloneDiskName": source_clone_name,
            **({"sourceCloneDiskId": str(source_clone.get("id") or "")} if isinstance(source_clone, Mapping) else {}),
        }
        if not await asyncio.to_thread(
            record_boot_image_state_disks,
            uid,
            vm_name,
            zone,
            auth_token,
            owner,
            migration_id,
            prepared_state,
        ):
            raise RuntimeError("boot-image state disk journal fence changed")
        await api.create_replacement(
            candidate_name,
            instance,
            release,
            candidate_token,
            migration_id,
            _disk_source(api.project, zone, state_disk_name),
            _disk_source(api.project, zone, source_clone_name) if source_clone_name else None,
        )
        candidate = await api.get_instance(candidate_name)
    if candidate is None or str(candidate.get("id") or "") == "":
        raise RuntimeError("replacement candidate is unavailable")
    labels = candidate.get("labels")
    service_accounts = candidate.get("serviceAccounts")
    first_service_account = service_accounts[0] if isinstance(service_accounts, list) and service_accounts else None
    candidate_service_account = (
        first_service_account.get("email") if isinstance(first_service_account, Mapping) else None
    )
    if (
        not isinstance(labels, Mapping)
        or labels.get("omi-agent-migration") != migration_id
        or labels.get("omi-agent-predecessor") != old_instance_id
        or candidate_service_account != release.service_account
    ):
        raise RuntimeError("replacement candidate identity is ambiguous")
    state_attachment = _disk_attachment(candidate, STATE_DISK_DEVICE_NAME)
    if not isinstance(state_attachment, Mapping) or _disk_name(state_attachment.get("source")) != state_disk_name:
        raise RuntimeError("replacement candidate state disk identity is ambiguous")
    state_disk = await api.get_disk(state_disk_name)
    if state_disk is None or str(state_disk.get("id") or "") == "":
        raise RuntimeError("replacement candidate state disk is unavailable")
    expected_state_id = str(journal.get("stateDiskId") or "")
    if expected_state_id and str(state_disk.get("id")) != expected_state_id:
        raise RuntimeError("replacement candidate state disk ID changed")
    source_clone = _disk_attachment(candidate, STATE_SOURCE_DEVICE_NAME)
    if source_clone_name and (
        not isinstance(source_clone, Mapping) or _disk_name(source_clone.get("source")) != source_clone_name
    ):
        raise RuntimeError("replacement candidate source clone identity is ambiguous")
    source_clone_disk_id = ""
    if source_clone_name:
        source_clone_disk = await api.get_disk(source_clone_name)
        source_clone_disk_id = str(source_clone_disk.get("id") or "") if isinstance(source_clone_disk, Mapping) else ""
        if not source_clone_disk_id:
            raise RuntimeError("replacement candidate source clone is unavailable")
    candidate_boot_drift = await _boot_image_drift(api, candidate, release)
    if candidate_boot_drift:
        raise RuntimeError("replacement candidate boot image does not match the pinned release")
    candidate_id = str(candidate["id"])
    if cleanup_context is not None:
        cleanup_context.update(
            {
                "vmName": candidate_name,
                "instanceId": candidate_id,
                "migrationId": migration_id,
                "oldInstanceId": old_instance_id,
                "stateDiskName": state_disk_name,
                "stateDiskId": str(state_disk["id"]),
                "stateDiskReused": "true" if state_disk_reused else "false",
                "ownerLabel": _owner_disk_label(uid),
                "sourceCloneDiskName": source_clone_name,
                "sourceCloneDiskId": source_clone_disk_id,
            }
        )
    if not await asyncio.to_thread(
        record_boot_image_candidate, uid, vm_name, zone, auth_token, owner, migration_id, candidate_id
    ):
        return ReconcileResult(uid, "stale", "boot-image candidate journal fence changed")
    private_ip = api.private_instance_ip(candidate)
    if not private_ip:
        raise RuntimeError("replacement candidate has no usable private IP")
    await api.wait_for_runtime(
        private_ip,
        candidate_token,
        release,
        expected_state_migration_id=migration_id,
    )
    # The lifecycle lease blocks new proxy admission.  Recheck pre-existing
    # sessions immediately before the irreversible pointer swap.
    if await asyncio.to_thread(active_session_count, uid, vm_name):
        return ReconcileResult(uid, "deferred", "session appeared before boot-image cutover")
    candidate_vm = {
        "vmName": candidate_name,
        "zone": zone,
        "status": "ready",
        "authToken": candidate_token,
        "instanceId": candidate_id,
        "privateIp": private_ip,
        "stateDisk": {
            "deviceName": STATE_DISK_DEVICE_NAME,
            "diskName": state_disk_name,
            "diskId": str(state_disk["id"]),
        },
        **({"ip": api.instance_ip(candidate)} if api.instance_ip(candidate) else {}),
        "reconcile": {
            # Block proxy admission until the journaled soak completes. No
            # owner work can land on the candidate during the rollback window.
            "state": "migration_soaking",
            "releaseId": release.release_id,
            "observedRelease": release.release_id,
            "observedImageDigest": release.image_digest,
            "observedStartupSha256": release.startup_sha256,
            "migration": {
                **migration,
                "stateDiskName": state_disk_name,
                "stateDiskId": str(state_disk["id"]),
                "stateDiskReused": state_disk_reused,
                "sourceCloneDiskName": source_clone_name,
                "sourceCloneDiskId": source_clone_disk_id,
                "candidateInstanceId": candidate_id,
                "cutoverAt": time.time(),
                "cutoverPending": True,
            },
        },
    }
    if not await asyncio.to_thread(
        cutover_boot_image_migration, uid, vm_name, zone, auth_token, owner, migration_id, candidate_vm
    ):
        return ReconcileResult(uid, "stale", "boot-image cutover fence changed; predecessor remains active")
    if source_clone_name:
        try:
            await api.detach_disk(candidate_name, STATE_SOURCE_DEVICE_NAME)
            if not await api.delete_disk(
                source_clone_name,
                source_clone_disk_id,
                migration_id,
                "source",
                _owner_disk_label(uid),
            ):
                logger.warning("Agent VM source clone cleanup fence changed for uid=%s", uid)
        except Exception:
            logger.exception("Agent VM source clone cleanup deferred for uid=%s", uid)
    if cleanup_context is not None:
        cleanup_context.clear()
    try:
        await api.set_disk_auto_delete(candidate_name, STATE_DISK_DEVICE_NAME, True)
    except Exception:
        # The active owner pointer already references this exact disk. Leaving
        # auto-delete disabled preserves data; the next reconciliation repairs
        # the privacy cleanup invariant before reporting the VM ready.
        logger.exception("Agent VM state disk auto-delete repair deferred for uid=%s", uid)
    return ReconcileResult(uid, "migrated", f"cut over to {candidate_name}; predecessor retained for soak")


async def _retire_soaked_boot_image_predecessor(
    uid: str,
    vm: Mapping[str, Any],
    *,
    owner: str,
    api: GceAgentVmClient,
    release: AgentVmRelease,
) -> ReconcileResult | None:
    """Retire a migrated predecessor only after its durable soak deadline.

    This is deliberately a separate recovery-safe phase: once the candidate
    is active, deletion is guarded by both the predecessor GCE numeric ID and
    migration label.  If a worker crashes after deletion, the next run sees a
    404 as success and can complete the Firestore journal.
    """
    reconcile = vm.get("reconcile")
    migration = reconcile.get("migration") if isinstance(reconcile, Mapping) else None
    if not isinstance(migration, Mapping):
        return None
    migration_id = migration.get("migrationId")
    old_vm_name = migration.get("oldVmName")
    old_instance_id = migration.get("oldInstanceId")
    candidate_id = migration.get("candidateInstanceId")
    if not (
        isinstance(migration_id, str)
        and _MIGRATION_ID.fullmatch(migration_id)
        and isinstance(old_vm_name, str)
        and old_vm_name
        and isinstance(old_instance_id, str)
        and old_instance_id
        and isinstance(candidate_id, str)
        and candidate_id == str(vm.get("instanceId") or "")
    ):
        return ReconcileResult(uid, "retry", "migration retirement record is incomplete")
    candidate = await api.get_instance(str(vm["vmName"]))
    if candidate is None or str(candidate.get("id") or "") != candidate_id:
        return ReconcileResult(uid, "soaking", "replacement candidate identity is unavailable during soak")
    private_ip = api.private_instance_ip(candidate)
    if (
        str(candidate.get("status") or "") != "RUNNING"
        or not private_ip
        or not await api.runtime_is_current(
            private_ip,
            str(vm["authToken"]),
            release,
            expected_state_migration_id=migration_id,
        )
    ):
        return ReconcileResult(uid, "soaking", "replacement candidate is not healthy during soak")
    source_clone_name = migration.get("sourceCloneDiskName")
    source_clone_id = migration.get("sourceCloneDiskId")
    if isinstance(source_clone_name, str) and source_clone_name:
        source_disk = await api.get_disk(source_clone_name)
        if source_disk is not None:
            if not isinstance(source_clone_id, str) or str(source_disk.get("id") or "") != source_clone_id:
                return ReconcileResult(uid, "stale", "migration source clone identity changed before cleanup")
            attachment = _disk_attachment(candidate or {}, STATE_SOURCE_DEVICE_NAME)
            if attachment is not None:
                await api.detach_disk(str(vm["vmName"]), STATE_SOURCE_DEVICE_NAME)
            if not await api.delete_disk(
                source_clone_name,
                source_clone_id,
                migration_id,
                "source",
                _owner_disk_label(uid),
            ):
                return ReconcileResult(uid, "stale", "migration source clone cleanup fence changed")
    # A lease for the predecessor must have expired before deleting it. New
    # sessions can only bind to the candidate after the pointer cutover.
    if await asyncio.to_thread(active_session_count, uid, old_vm_name):
        return ReconcileResult(uid, "soaking", "predecessor still has an active session lease")
    vm_name = str(vm["vmName"])
    zone = str(vm.get("zone") or DEFAULT_ZONE)
    auth_token = str(vm["authToken"])
    retirement = await asyncio.to_thread(
        claim_boot_image_migration_retirement,
        uid,
        vm_name,
        zone,
        auth_token,
        owner,
        migration_id,
        candidate_id,
    )
    if retirement is None:
        return ReconcileResult(uid, "stale", "migration retirement fence changed")
    if retirement.get("state") == "soaking":
        return ReconcileResult(uid, "soaking", "replacement candidate is within its journaled soak")
    claimed_old_vm_name = retirement.get("oldVmName")
    claimed_old_instance_id = retirement.get("oldInstanceId")
    if not isinstance(claimed_old_vm_name, str) or not isinstance(claimed_old_instance_id, str):
        return ReconcileResult(uid, "stale", "migration retirement predecessor identity is incomplete")
    if not await api.delete_replacement(claimed_old_vm_name, claimed_old_instance_id, migration_id):
        return ReconcileResult(uid, "stale", "predecessor identity fence changed before retirement")
    completed = await asyncio.to_thread(
        complete_boot_image_migration,
        uid,
        vm_name,
        zone,
        auth_token,
        owner,
        migration_id,
        candidate_id,
    )
    if not completed:
        return ReconcileResult(uid, "stale", "predecessor retired; migration completion fence changed")
    return ReconcileResult(uid, "retired", f"retired soaked predecessor {old_vm_name}")


async def _update_reconcile(
    uid: str,
    vm_name: str,
    auth_token: str,
    owner: str,
    fields: Mapping[str, Any],
    *,
    vm_fields: Mapping[str, Any] | None = None,
    consume_start_request_at: float | None = None,
    force_consume_start_request: bool = False,
) -> bool:
    return await asyncio.to_thread(
        update_vm_reconcile,
        uid,
        vm_name,
        auth_token,
        owner,
        fields,
        vm_fields=vm_fields,
        consume_start_request_at=consume_start_request_at,
        force_consume_start_request=force_consume_start_request,
    )


async def reconcile_one(
    uid: str,
    vm: Mapping[str, Any],
    release: AgentVmRelease,
    *,
    owner: str,
    project: str,
    dry_run: bool = False,
    missing_cleanup_grace_seconds: int | None = None,
    boot_image_migration: BootImageMigrationPlan | None = None,
) -> ReconcileResult:
    vm_name = str(vm["vmName"])
    auth_token = str(vm["authToken"])
    zone = str(vm.get("zone") or DEFAULT_ZONE)
    api = GceAgentVmClient(project, zone)
    if dry_run:
        instance = await api.get_instance(vm_name)
        if instance is None:
            return ReconcileResult(uid, "missing", "GCE instance not found")
        reasons = drift_reasons(instance, release)
        boot_drift = await _boot_image_drift(api, instance, release)
        if boot_drift:
            reasons.append("boot_image")
        if str(instance.get("status")) == "RUNNING":
            private_ip = api.private_instance_ip(instance)
            if not private_ip or not await api.runtime_is_current(private_ip, auth_token, release):
                reasons.append("runtime")
        return ReconcileResult(uid, "drift" if reasons else "ready", ",".join(sorted(set(reasons))))
    reconcile_raw = vm.get("reconcile")
    reconcile_state = reconcile_raw if isinstance(reconcile_raw, Mapping) else {}
    active_migration = reconcile_state.get("migration")
    post_cutover_migration = isinstance(active_migration, Mapping) and str(
        active_migration.get("candidateInstanceId") or ""
    ) == str(vm.get("instanceId") or "")
    missing_since_raw = reconcile_state.get("missingSince")
    missing_since = float(missing_since_raw) if isinstance(missing_since_raw, (int, float)) else None
    start_requested = bool(reconcile_state.get("startRequested"))
    start_requested_at = reconcile_state.get("startRequestedAt") if start_requested else None
    observed_start_request_at = float(start_requested_at) if isinstance(start_requested_at, (int, float)) else None
    if reconcile_state.get("state") == "quarantined" and reconcile_state.get("releaseId") == release.release_id:
        return ReconcileResult(uid, "quarantined", str(reconcile_state.get("lastError") or "operator action required"))
    if not await asyncio.to_thread(claim_vm_lease, uid, vm_name, auth_token, owner, release.release_id):
        return ReconcileResult(uid, "busy")

    now = time.time()
    missing_cleanup_grace_seconds = (
        _missing_cleanup_grace_seconds() if missing_cleanup_grace_seconds is None else missing_cleanup_grace_seconds
    )
    failed_candidate: dict[str, str] = {}
    try:
        instance = await api.get_instance(vm_name)
        if instance is None:
            terminal_cleanup_due = (
                not start_requested
                and missing_since is not None
                and missing_since <= now - missing_cleanup_grace_seconds
            )
            cleanup_blocked_detail: str | None = None
            if terminal_cleanup_due:
                if vm.get("status") not in {"ready", "stopped"}:
                    cleanup_blocked_detail = (
                        "GCE instance not found; original provisioning outcome is not safe to clean"
                    )
                else:
                    active = await asyncio.to_thread(active_session_count, uid, vm_name)
                    if active:
                        cleanup_blocked_detail = f"GCE instance not found; {active} active session(s) block cleanup"
            if terminal_cleanup_due and cleanup_blocked_detail is None:
                assert missing_since is not None
                deleted = await asyncio.to_thread(
                    clear_missing_vm_if_current,
                    uid,
                    vm_name,
                    zone,
                    auth_token,
                    owner,
                    missing_since,
                )
                if deleted:
                    return ReconcileResult(uid, "cleaned", "removed abandoned missing VM record")
                return ReconcileResult(uid, "stale", "owner lease or terminal-cleanup fence changed")
            recorded_missing_since = missing_since if missing_since is not None else now
            missing_fields: dict[str, Any] = {
                "state": "missing",
                "lastError": "GCE instance not found",
                "missingSince": recorded_missing_since,
                "lease": DELETE_FIELD,
                "drainRequested": DELETE_FIELD,
                "drainRequestedAt": DELETE_FIELD,
            }
            # A provider-confirmed 404 makes the observed demand impossible to
            # fulfill. Consume only that exact request, while the transaction
            # preserves any newer demand that arrives during this check.
            missing_fields.update({"startRequested": DELETE_FIELD, "startRequestedAt": DELETE_FIELD})
            if not await _update_reconcile(
                uid,
                vm_name,
                auth_token,
                owner,
                missing_fields,
                consume_start_request_at=observed_start_request_at,
            ):
                return ReconcileResult(uid, "stale", "owner lease lost while recording missing VM")
            if cleanup_blocked_detail:
                return ReconcileResult(uid, "missing", cleanup_blocked_detail)
            return ReconcileResult(uid, "cleanup_pending", "GCE instance not found; waiting for terminal cleanup grace")
        boot_drift = await _boot_image_drift(api, instance, release)
        if boot_drift:
            reason, actual = boot_drift
            # A mutable, malformed, or unreadable source is a fail-closed
            # observation, never permission to replace an instance.
            if boot_image_migration is not None and reason == "boot_image_recreate_required":
                migration = await _replace_stopped_boot_image_drift(
                    uid,
                    vm,
                    instance,
                    release,
                    boot_image_migration,
                    owner=owner,
                    api=api,
                    cleanup_context=failed_candidate,
                )
                if migration.state != "recreate_required":
                    return migration
            if not await _update_reconcile(
                uid,
                vm_name,
                auth_token,
                owner,
                {
                    "state": "recreate_required",
                    "lastError": reason,
                    "driftReasons": [reason],
                    "requiredBootImage": release.boot_image,
                    "observedBootImage": actual,
                    "missingSince": DELETE_FIELD,
                    **clear_vm_reconcile_lease_fields(),
                },
                consume_start_request_at=observed_start_request_at,
            ):
                return ReconcileResult(uid, "stale", "owner lease lost while recording boot-image drift")
            return ReconcileResult(
                uid,
                "recreate_required",
                f"{reason}; operator must recreate VM from exact immutable image {release.boot_image}",
            )
        state_disk_info = await _active_state_disk_info(api, uid, vm, instance)
        retirement = await _retire_soaked_boot_image_predecessor(uid, vm, owner=owner, api=api, release=release)
        if retirement is not None:
            return retirement
        reasons = drift_reasons(instance, release)
        if str(instance.get("status")) == "RUNNING":
            private_ip = api.private_instance_ip(instance)
            if not private_ip or not await api.runtime_is_current(private_ip, auth_token, release):
                reasons.append("runtime")
        if reasons:
            if not await asyncio.to_thread(renew_vm_lease, uid, vm_name, auth_token, owner):
                return ReconcileResult(uid, "stale", "owner lease lost before drain")
            if not await _update_reconcile(
                uid,
                vm_name,
                auth_token,
                owner,
                {"state": "draining", "drainRequested": True, "drainRequestedAt": now, "driftReasons": reasons},
            ):
                return ReconcileResult(uid, "stale", "owner lease lost while requesting drain")
            active = await asyncio.to_thread(active_session_count, uid, vm_name)
            if active:
                if not await _update_reconcile(
                    uid,
                    vm_name,
                    auth_token,
                    owner,
                    {
                        "state": "deferred",
                        "retryAt": now + 120,
                        "activeSessionCount": active,
                    },
                ):
                    return ReconcileResult(uid, "stale", "owner lease lost while deferring drain")
                return ReconcileResult(uid, "deferred", f"{active} active session(s)")

        status = str(instance.get("status") or "UNKNOWN")
        if not reasons and status in {"TERMINATED", "STOPPED"} and not start_requested:
            if not await _update_reconcile(
                uid,
                vm_name,
                auth_token,
                owner,
                {
                    "state": "ready",
                    "observedRelease": release.release_id,
                    "observedImageDigest": release.image_digest,
                    "observedStartupSha256": release.startup_sha256,
                    "lastSuccessAt": time.time(),
                    "retryCount": 0,
                    "lastError": None,
                    "retryAt": None,
                    "missingSince": DELETE_FIELD,
                    **clear_vm_reconcile_lease_fields(),
                },
                vm_fields={
                    "status": "stopped",
                    **({"stateDisk": state_disk_info} if state_disk_info else {}),
                },
                consume_start_request_at=observed_start_request_at,
            ):
                return ReconcileResult(uid, "stale", "owner lease lost while recording stopped VM")
            return ReconcileResult(uid, "ready", "stopped; idle self-stop preserved")
        if status == "RUNNING" and reasons:
            if not await asyncio.to_thread(renew_vm_lease, uid, vm_name, auth_token, owner):
                return ReconcileResult(uid, "stale", "owner lease lost before stop")
            await api.stop(vm_name)
            status = "TERMINATED"
        if status not in {"TERMINATED", "STOPPED"} and reasons:
            raise RuntimeError(f"provider status {status}")

        if reasons:
            latest = await api.get_instance(vm_name)
            if latest is None:
                raise RuntimeError("instance disappeared during reconciliation")
            if not await asyncio.to_thread(renew_vm_lease, uid, vm_name, auth_token, owner):
                return ReconcileResult(uid, "stale", "owner lease lost before metadata update")
            await api.set_service_account(vm_name, release.service_account)
            await api.set_metadata(vm_name, latest, release, auth_token)
            status = str((await api.get_instance(vm_name) or {}).get("status") or status)

        if status in {"TERMINATED", "STOPPED"}:
            if not await asyncio.to_thread(renew_vm_lease, uid, vm_name, auth_token, owner):
                return ReconcileResult(uid, "stale", "owner lease lost before start")
            await api.start(vm_name)
        elif status != "RUNNING":
            raise RuntimeError(f"provider status {status}")

        latest = await api.get_instance(vm_name)
        if latest is None:
            raise RuntimeError("instance disappeared before readiness verification")
        private_ip = api.private_instance_ip(latest)
        if not private_ip:
            raise RuntimeError("instance has no usable private IP")
        await api.wait_for_runtime(private_ip, auth_token, release)
        public_ip = api.instance_ip(latest)
        finished_at = time.time()
        if not await _update_reconcile(
            uid,
            vm_name,
            auth_token,
            owner,
            {
                "state": "ready",
                "observedRelease": release.release_id,
                "observedImageDigest": release.image_digest,
                "observedStartupSha256": release.startup_sha256,
                "lastSuccessAt": finished_at,
                "retryCount": 0,
                "lastError": None,
                "retryAt": None,
                "missingSince": DELETE_FIELD,
                **clear_vm_reconcile_lease_fields(),
            },
            vm_fields={
                "status": "ready",
                "privateIp": private_ip,
                **({"stateDisk": state_disk_info} if state_disk_info else {}),
                **({"ip": public_ip} if public_ip else {}),
            },
            consume_start_request_at=observed_start_request_at,
        ):
            return ReconcileResult(uid, "stale", "owner lease lost before final CAS")
        return ReconcileResult(uid, "ready", release.release_id)
    except Exception as exc:
        logger.warning("Agent VM reconciliation failed for one owner (%s): %s", uid, type(exc).__name__)
        reconcile_raw = vm.get("reconcile")
        reconcile: dict[str, Any] = reconcile_raw if isinstance(reconcile_raw, dict) else {}
        prior_release = str(reconcile.get("releaseId") or "")
        retry_count = (
            1
            if release.release_id and prior_release != release.release_id
            else int(reconcile.get("retryCount", 0) or 0) + 1
        )
        retry_at = time.time() + retry_delay_seconds(retry_count)
        retry_state = "quarantined" if retry_count >= 3 else "retry"
        cleanup_succeeded = not post_cutover_migration
        if failed_candidate:
            try:
                cleanup_succeeded = await _rollback_failed_boot_image_candidate(
                    api,
                    uid,
                    vm_name,
                    failed_candidate,
                )
                if not cleanup_succeeded:
                    logger.error("Agent VM migration rollback fence changed for uid=%s", uid)
                elif failed_candidate.get("instanceId"):
                    if not await asyncio.to_thread(
                        mark_boot_image_migration_candidate_deleted,
                        uid,
                        vm_name,
                        zone,
                        auth_token,
                        owner,
                        failed_candidate["migrationId"],
                        failed_candidate["instanceId"],
                    ):
                        logger.warning(
                            "Agent VM migration candidate journal fence changed after cleanup for uid=%s", uid
                        )
            except Exception:
                cleanup_succeeded = False
                logger.exception("Agent VM migration candidate cleanup failed for uid=%s", uid)
        if not cleanup_succeeded:
            # Never reopen proxy admission while ownership of the durable disk
            # is ambiguous. Operator repair or a later successful retry must
            # restore the predecessor boundary first.
            retry_state = "quarantined"
        if not await _update_reconcile(
            uid,
            vm_name,
            auth_token,
            owner,
            {
                "state": retry_state,
                "retryCount": retry_count,
                "lastError": type(exc).__name__,
                "retryAt": retry_at,
                # A demand start is the retry's eligibility signal. Retain it
                # until terminal quarantine so the scheduled reconciler can
                # honor retryAt without requiring another client request.
                "lease": DELETE_FIELD,
                "drainRequested": True if not cleanup_succeeded else DELETE_FIELD,
                "drainRequestedAt": time.time() if not cleanup_succeeded else DELETE_FIELD,
            },
            consume_start_request_at=observed_start_request_at if retry_state == "quarantined" else None,
            force_consume_start_request=retry_state == "quarantined",
        ):
            return ReconcileResult(uid, "stale", "owner lease lost while recording failure")
        return ReconcileResult(uid, retry_state, type(exc).__name__)


async def run_reconciler(*, dry_run: bool = False) -> list[ReconcileResult]:
    _init_firebase()
    release, raw_manifest = load_active_release()
    environment = os.getenv("AGENT_VM_ENVIRONMENT", release.environment)
    project = os.getenv("GCE_PROJECT_ID")
    if not project:
        raise RuntimeError("GCE_PROJECT_ID is required for Agent VM reconciliation")
    # Validate before owner discovery so an accidentally promoted migration
    # section cannot look harmless just because this run has no matching VMs.
    migration_plan = _boot_image_migration_plan(raw_manifest, release)
    missing_cleanup_grace_seconds = _missing_cleanup_grace_seconds()
    owner = f"{os.getenv('K_REVISION', 'local')}:{uuid.uuid4().hex}"
    if not dry_run and not await asyncio.to_thread(claim_reconciler_run_lease, environment, owner):
        logger.info("Agent VM reconciler skipped: another run owns the %s lease", environment)
        return []
    try:
        lease_lost = asyncio.Event()
        heartbeat_stop = asyncio.Event()
        heartbeat_task: asyncio.Task[None] | None = None

        async def heartbeat() -> None:
            while not heartbeat_stop.is_set():
                await asyncio.sleep(LEASE_HEARTBEAT_SECONDS)
                try:
                    if not await asyncio.to_thread(renew_reconciler_run_lease, environment, owner):
                        lease_lost.set()
                        return
                except Exception:
                    logger.exception("Agent VM reconciler lease heartbeat failed")
                    lease_lost.set()
                    return

        try:
            if not dry_run:
                heartbeat_task = asyncio.create_task(heartbeat(), name="agent-vm-reconciler-lease-heartbeat")
            phase = await asyncio.to_thread(
                _rollout_phase, environment, release.release_id, raw_manifest, persist=not dry_run
            )
            target_percent, max_concurrency = _rollout_spec(raw_manifest, phase)
            owners = await asyncio.to_thread(_owners)
            rollout_selected = _select_rollout_owners(owners, release.release_id, target_percent)
            selected = sorted(
                _select_reconcile_owners(owners, release.release_id, target_percent), key=lambda item: item[0]
            )
            # An explicit boot-image migration allowlist is independent of the
            # ordinary release rollout cohort.  A stopped allowlisted VM that is
            # not in the current cohort must still be selected so its drift can
            # be replaced.  Rollout advancement only consumes rollout_selected
            # results, so these extra owners never advance the rollout phase.
            if migration_plan is not None:
                selected_uids = {uid for uid, _ in selected}
                migration_candidates = [
                    (uid, vm)
                    for uid, vm in owners
                    if uid not in selected_uids
                    and uid in migration_plan.allowed_uids
                    and str(vm.get("status") or "") == "stopped"
                ]
                selected.extend(migration_candidates)
            # A migration plan has its own explicit maxConcurrency contract and
            # never inherits the normal release rollout's wider semaphore.
            # Every selected allowlisted owner gets a chance; the dedicated
            # lock serializes potentially long candidate readiness checks.
            migration_lock = asyncio.Semaphore(migration_plan.max_concurrency) if migration_plan is not None else None
            semaphore = asyncio.Semaphore(max_concurrency)

            async def one(uid: str, vm: dict[str, Any]) -> ReconcileResult:
                migration_for_owner = (
                    migration_plan if migration_plan is not None and uid in migration_plan.allowed_uids else None
                )

                async def reconcile() -> ReconcileResult:
                    async with semaphore:
                        return await reconcile_one(
                            uid,
                            vm,
                            release,
                            owner=owner,
                            project=project,
                            dry_run=dry_run,
                            missing_cleanup_grace_seconds=missing_cleanup_grace_seconds,
                            boot_image_migration=migration_for_owner,
                        )

                # Do not claim an owner VM lease until this migration has the
                # one permitted slot. A health wait can last minutes; claiming
                # first would make queued owner leases expire before mutation.
                if migration_for_owner is not None and migration_lock is not None:
                    async with migration_lock:
                        return await reconcile()
                return await reconcile()

            results = await asyncio.gather(*(one(uid, vm) for uid, vm in selected))
            if lease_lost.is_set() and not dry_run:
                raise AgentVmLeaseLost("reconciler run lease lost")
        finally:
            heartbeat_stop.set()
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
        counts: dict[str, int] = {}
        for result in results:
            counts[result.state] = counts.get(result.state, 0) + 1
        if not dry_run:
            rollout_uids = {uid for uid, _ in rollout_selected}
            rollout_results = [result for result in results if result.uid in rollout_uids]
            await asyncio.to_thread(
                _advance_rollout, environment, release.release_id, phase, rollout_results, len(rollout_selected)
            )
        logger.info("Agent VM reconciliation complete: %s", counts)
        return results
    finally:
        if not dry_run:
            await asyncio.to_thread(release_reconciler_run_lease, environment, owner)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    results = asyncio.run(run_reconciler(dry_run=bool(args.dry_run)))
    return 1 if any(result.state in FAILED_JOB_STATES for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
