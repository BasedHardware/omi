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
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import firebase_admin
from google.cloud import storage
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import get_firestore_client
from services.agent_vm_lifecycle import (
    DEFAULT_ZONE,
    LEASE_HEARTBEAT_SECONDS,
    AgentVmLeaseLost,
    AgentVmRelease,
    GceAgentVmClient,
    active_session_count,
    claim_reconciler_run_lease,
    claim_vm_lease,
    clear_vm_reconcile_lease_fields,
    drift_reasons,
    release_reconciler_run_lease,
    renew_reconciler_run_lease,
    renew_vm_lease,
    retry_delay_seconds,
    rollout_selected,
    update_vm_reconcile,
    validate_release_manifest,
)
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
_IMMUTABLE_BOOT_IMAGE = re.compile(r"^projects/[^/]+/global/images/[^/]+$")


@dataclass(frozen=True)
class ReconcileResult:
    uid: str
    state: str
    detail: str = ""


def _init_firebase() -> None:
    try:
        firebase_admin.get_app()
        return
    except ValueError:
        pass
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(firebase_admin.credentials.Certificate(json.loads(service_account_json)))
    else:
        firebase_admin.initialize_app()


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


async def _update_reconcile(
    uid: str,
    vm_name: str,
    auth_token: str,
    owner: str,
    fields: Mapping[str, Any],
    *,
    vm_fields: Mapping[str, Any] | None = None,
) -> bool:
    return await asyncio.to_thread(
        update_vm_reconcile,
        uid,
        vm_name,
        auth_token,
        owner,
        fields,
        vm_fields=vm_fields,
    )


async def reconcile_one(
    uid: str,
    vm: Mapping[str, Any],
    release: AgentVmRelease,
    *,
    owner: str,
    project: str,
    dry_run: bool = False,
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
    if reconcile_state.get("state") == "quarantined" and reconcile_state.get("releaseId") == release.release_id:
        return ReconcileResult(uid, "quarantined", str(reconcile_state.get("lastError") or "operator action required"))
    if not await asyncio.to_thread(claim_vm_lease, uid, vm_name, auth_token, owner, release.release_id):
        return ReconcileResult(uid, "busy")

    now = time.time()
    try:
        instance = await api.get_instance(vm_name)
        if instance is None:
            if not await _update_reconcile(
                uid,
                vm_name,
                auth_token,
                owner,
                {"state": "missing", "lastError": "GCE instance not found", **clear_vm_reconcile_lease_fields()},
            ):
                return ReconcileResult(uid, "stale", "owner lease lost while recording missing VM")
            return ReconcileResult(uid, "missing", "GCE instance not found")
        boot_drift = await _boot_image_drift(api, instance, release)
        if boot_drift:
            reason, actual = boot_drift
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
                    **clear_vm_reconcile_lease_fields(),
                },
            ):
                return ReconcileResult(uid, "stale", "owner lease lost while recording boot-image drift")
            return ReconcileResult(
                uid,
                "recreate_required",
                f"{reason}; operator must recreate VM from exact immutable image {release.boot_image}",
            )
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
        if not reasons and status in {"TERMINATED", "STOPPED"}:
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
                    **clear_vm_reconcile_lease_fields(),
                },
                vm_fields={"status": "stopped"},
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
                **clear_vm_reconcile_lease_fields(),
            },
            vm_fields={
                "status": "ready",
                "privateIp": private_ip,
                **({"ip": public_ip} if public_ip else {}),
            },
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
                **clear_vm_reconcile_lease_fields(),
            },
        ):
            return ReconcileResult(uid, "stale", "owner lease lost while recording failure")
        return ReconcileResult(uid, retry_state, type(exc).__name__)


async def run_reconciler(*, dry_run: bool = False) -> list[ReconcileResult]:
    _init_firebase()
    release, raw_manifest = load_active_release()
    environment = os.getenv("AGENT_VM_ENVIRONMENT", release.environment)
    project = os.getenv("GCE_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
    if not project:
        raise RuntimeError("GCE_PROJECT_ID, FIREBASE_PROJECT_ID, or GCP_PROJECT_ID is required")
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
                if not await asyncio.to_thread(renew_reconciler_run_lease, environment, owner):
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
            selected = _select_rollout_owners(owners, release.release_id, target_percent)
            semaphore = asyncio.Semaphore(max_concurrency)

            async def one(uid: str, vm: dict[str, Any]) -> ReconcileResult:
                async with semaphore:
                    return await reconcile_one(uid, vm, release, owner=owner, project=project, dry_run=dry_run)

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
            await asyncio.to_thread(_advance_rollout, environment, release.release_id, phase, results, len(selected))
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
