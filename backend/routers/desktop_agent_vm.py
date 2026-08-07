import asyncio
import hashlib
import ipaddress
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import google.auth
import google.auth.transport.requests
import google.oauth2.id_token
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from google.cloud.firestore import transactional
from google.cloud.firestore_v1.base_query import FieldFilter
from pydantic import BaseModel, ConfigDict, Field

from database import users as users_db
from database._client import get_firestore_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from services.agent_vm_lifecycle import (
    claim_vm_lease,
    clear_vm_reconcile_lease_fields,
    request_vm_start,
    startup_wrapper,
    update_vm_reconcile,
)
from services.agent_vm_read import (
    apply_agent_vm_read_decision,
    classify_provider_observation,
    decide_agent_vm_read,
    demoted_updating_vm,
    reconcile_in_progress,
)
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid
from utils.subscription import is_trial_paywalled

logger = logging.getLogger(__name__)
router = APIRouter()
_ZONE = "us-central1-a"
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_READY_TIMEOUT_SECONDS = 300
_READY_POLL_SECONDS = 5
_STOP_BROKER_RATE_LIMIT = 30
_STOP_BROKER_RATE_WINDOW_SECONDS = 60
_stop_broker_attempts: dict[str, list[float]] = {}
_stop_broker_attempts_lock = threading.Lock()


class AccountDeletionAccessBlocked(RuntimeError):
    pass


class AgentVmCreateOutcomeUnknown(RuntimeError):
    """The provider may have accepted a create request before the failure."""


class AgentVmResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vm_name: str = Field(alias="vmName")
    zone: str
    ip: str | None = None
    status: str
    auth_token: str = Field(alias="authToken")
    created_at: str = Field(alias="createdAt")
    last_query_at: str | None = Field(default=None, alias="lastQueryAt")


class ProvisionAgentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    vm_name: str = Field(alias="vmName")
    ip: str | None = None
    auth_token: str = Field(alias="authToken")
    agent_status: str = Field(alias="agentStatus")


def _agent_disabled() -> bool:
    return os.getenv("ENVIRONMENT") == "local-dev-harness"


async def _authorized_desktop_user(uid: str = Depends(get_current_user_uid)) -> str:
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=402, detail="trial_expired")
    return uid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _project() -> str:
    project = os.getenv("GCE_PROJECT_ID")
    if not project:
        raise RuntimeError("GCE_PROJECT_ID is required for Agent VM control")
    return project


def _source_image(project: str) -> str:
    source_image = os.getenv("AGENT_VM_BOOT_IMAGE", "").strip()
    if not re.fullmatch(rf"projects/{re.escape(project)}/global/images/[^/]+", source_image):
        raise RuntimeError("AGENT_VM_BOOT_IMAGE must name an exact immutable image in the configured GCE project")
    return source_image


def _gcs_bucket() -> str:
    bucket = os.getenv("AGENT_GCS_BUCKET")
    if not bucket:
        raise RuntimeError("AGENT_GCS_BUCKET is not configured")
    return bucket


def _service_account() -> str:
    service_account = os.getenv("GCE_SERVICE_ACCOUNT")
    if not service_account:
        raise RuntimeError("GCE_SERVICE_ACCOUNT is not configured")
    return service_account


def _agent_vm_startup_metadata(bucket: str) -> dict[str, str]:
    del bucket
    startup_uri = os.getenv("AGENT_VM_STARTUP_URI", "").strip()
    startup_sha256 = os.getenv("AGENT_VM_STARTUP_SHA256", "").strip()
    release_id = os.getenv("AGENT_VM_RELEASE_ID", "").strip()
    image_digest = os.getenv("AGENT_VM_IMAGE_DIGEST", "").strip()
    boot_image = os.getenv("AGENT_VM_BOOT_IMAGE", "").strip()
    if (
        not startup_uri.startswith("https://storage.googleapis.com/")
        or not re.fullmatch(r"[0-9a-f]{64}", startup_sha256)
        or not re.fullmatch(r"[0-9a-f]{40}", release_id)
        or not re.fullmatch(r".+@sha256:[0-9a-f]{64}", image_digest)
        or not re.fullmatch(r"projects/[^/]+/global/images/[^/]+", boot_image)
    ):
        raise RuntimeError("Agent VM provisioning requires a complete immutable release contract")
    metadata = {
        "startup-script": startup_wrapper(startup_uri, startup_sha256),
        "omi-agent-reconciler-schema": "1",
        "omi-agent-release": release_id,
        "omi-agent-image-digest": image_digest,
        "omi-agent-startup-sha256": startup_sha256,
        "omi-agent-boot-image": boot_image,
    }
    return metadata


def _get_vm(uid: str) -> dict[str, Any] | None:
    snapshot = get_firestore_client().collection("users").document(uid).get()
    if not snapshot.exists:
        return None
    vm = snapshot.to_dict().get("agentVm")
    return vm if isinstance(vm, dict) and vm.get("vmName") else None


def _reconcile_in_progress(vm: dict[str, Any], now: float | None = None) -> bool:
    return reconcile_in_progress(vm, now)


def _updating_vm(vm: dict[str, Any]) -> dict[str, Any]:
    return demoted_updating_vm(vm)


def _validate_ready_vm_ip(status: str, ip: str | None) -> None:
    if status == "ready" and not _is_usable_vm_ip(ip):
        raise ValueError("refusing to persist ready agentVm without a usable IP address")


@transactional
def _claim_vm_if_allowed_txn(
    transaction, deletion_ref, user_ref, candidate: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    deletion_status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(deletion_status):
        raise AccountDeletionAccessBlocked(deletion_status or "unknown")
    snapshot = user_ref.get(transaction=transaction)
    current = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if isinstance(current, dict) and current.get("vmName"):
        return current, False
    transaction.set(user_ref, {"agentVm": candidate}, merge=True)
    return candidate, True


def _claim_vm_if_allowed(uid: str, candidate: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    client = get_firestore_client()
    return _claim_vm_if_allowed_txn(
        client.transaction(),
        client.collection("account_deletions").document(uid),
        client.collection("users").document(uid),
        candidate,
    )


def _vm_lifecycle_allowed(uid: str, expected_vm_name: str, expected_auth_token: str) -> bool:
    client = get_firestore_client()
    deletion = client.collection("account_deletions").document(uid).get()
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    deletion_status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(deletion_status):
        return False
    user = client.collection("users").document(uid).get()
    current = (user.to_dict() or {}).get("agentVm") if user.exists else None
    return (
        isinstance(current, dict)
        and current.get("vmName") == expected_vm_name
        and current.get("authToken") == expected_auth_token
    )


@transactional
def _set_vm_if_current_txn(
    transaction,
    deletion_ref,
    user_ref,
    expected_vm_name: str,
    expected_auth_token: str,
    status: str,
    ip: str | None,
    zone: str,
) -> bool:
    deletion = deletion_ref.get(transaction=transaction)
    raw_status = (deletion.to_dict() or {}).get("wipe_status") if deletion.exists else None
    deletion_status = normalize_account_deletion_status(marker_exists=deletion.exists, raw_status=raw_status)
    if account_deletion_blocks_access(deletion_status):
        return False
    snapshot = user_ref.get(transaction=transaction)
    current = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(current, dict):
        return False
    if current.get("vmName") != expected_vm_name or current.get("authToken") != expected_auth_token:
        return False
    _validate_ready_vm_ip(status, ip)
    next_vm = {
        **current,
        "vmName": expected_vm_name,
        "zone": zone,
        "status": status,
        "authToken": expected_auth_token,
    }
    if _is_usable_vm_ip(ip):
        next_vm["ip"] = ip
    else:
        next_vm.pop("ip", None)
    transaction.set(user_ref, {"agentVm": next_vm}, merge=True)
    return True


def _set_vm_if_current(
    uid: str,
    expected_vm_name: str,
    expected_auth_token: str,
    status: str,
    ip: str | None = None,
    zone: str = _ZONE,
) -> bool:
    client = get_firestore_client()
    return _set_vm_if_current_txn(
        client.transaction(),
        client.collection("account_deletions").document(uid),
        client.collection("users").document(uid),
        expected_vm_name,
        expected_auth_token,
        status,
        ip,
        zone,
    )


def _get_access_token() -> str:
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


async def _gce_request(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.request(method, url, headers={"Authorization": f"Bearer {token}"}, json=body)
    return response


async def _operation(project: str, zone: str, operation: str) -> None:
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/operations/{operation}"
    for _ in range(24):
        await asyncio.sleep(5)
        token = await run_blocking(db_executor, _get_access_token)
        response = await _gce_request("GET", url, token)
        response.raise_for_status()
        result = response.json()
        if result.get("status") == "DONE":
            if result.get("error"):
                raise RuntimeError(f"GCE operation failed: {result['error']}")
            return
    raise RuntimeError("GCE operation timed out")


async def _instance(project: str, zone: str, vm_name: str) -> tuple[str, dict[str, Any] | None]:
    token = await run_blocking(db_executor, _get_access_token)
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{vm_name}"
    response = await _gce_request("GET", url, token)
    if response.status_code == 404:
        return "NOT_FOUND", None
    response.raise_for_status()
    instance = response.json()
    return str(instance.get("status", "UNKNOWN")), instance


async def _wait_for_vm_ready(ip: str, auth_token: str) -> None:
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    url = f"http://{ip}:8080/health"
    headers = {"Authorization": f"Bearer {auth_token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        while time.monotonic() < deadline:
            try:
                unauthenticated = await client.get(url)
                if unauthenticated.status_code != 401:
                    await asyncio.sleep(_READY_POLL_SECONDS)
                    continue
                response = await client.get(url, headers=headers)
                if response.status_code == 200 and response.json().get("status") == "ok":
                    return
            except (httpx.HTTPError, ValueError):
                pass
            await asyncio.sleep(_READY_POLL_SECONDS)
    raise RuntimeError("Agent VM did not become healthy before the readiness timeout")


def _is_usable_vm_ip(value: Any) -> bool:
    if not isinstance(value, str) or not value or value == "unknown":
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _ip(instance: dict[str, Any]) -> str | None:
    try:
        candidate = str(instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"])
    except (KeyError, IndexError, TypeError):
        return None
    return candidate if _is_usable_vm_ip(candidate) else None


async def _create_vm(
    project: str, source_image: str, bucket: str, vm_name: str, auth_token: str, service_account: str
) -> str:
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{_ZONE}/instances"
    startup_metadata = _agent_vm_startup_metadata(bucket)
    body = {
        "name": vm_name,
        "machineType": f"zones/{_ZONE}/machineTypes/e2-small",
        "disks": [
            {
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": source_image,
                    "diskSizeGb": "50",
                    "diskType": f"zones/{_ZONE}/diskTypes/pd-balanced",
                },
            }
        ],
        "serviceAccounts": [
            {
                # This identity is dedicated to VM bootstrap and is limited to
                # the Agent VM image repository and environment secrets.
                "email": service_account,
                "scopes": [_CLOUD_PLATFORM_SCOPE],
            }
        ],
        "networkInterfaces": [
            {
                "network": "global/networks/default",
                "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
            }
        ],
        "tags": {"items": ["omi-agent-vm"]},
        "metadata": {
            "items": [
                *[{"key": key, "value": value} for key, value in startup_metadata.items()],
                {"key": "auth-token", "value": auth_token},
            ]
        },
    }
    token = await run_blocking(db_executor, _get_access_token)
    try:
        response = await _gce_request("POST", url, token, body)
    except Exception as exc:
        raise AgentVmCreateOutcomeUnknown("GCE create request outcome is unknown") from exc
    response.raise_for_status()
    operation = response.json().get("name")
    if not operation:
        raise AgentVmCreateOutcomeUnknown("GCE create response omitted operation name")
    try:
        await _operation(project, _ZONE, operation)
        _, instance = await _instance(project, _ZONE, vm_name)
    except Exception as exc:
        raise AgentVmCreateOutcomeUnknown("GCE create completion is unknown") from exc
    if instance is None:
        raise AgentVmCreateOutcomeUnknown("GCE created VM is unavailable")
    ip = _ip(instance)
    if ip is None:
        raise AgentVmCreateOutcomeUnknown("GCE created VM has no usable IP address")
    await _wait_for_vm_ready(ip, auth_token)
    return ip


async def _stop_vm(project: str, vm_name: str, zone: str) -> None:
    token = await run_blocking(db_executor, _get_access_token)
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{vm_name}/stop"
    response = await _gce_request("POST", url, token)
    response.raise_for_status()
    operation = response.json().get("name")
    if not operation:
        raise RuntimeError("GCE stop response omitted operation name")
    await _operation(project, zone, operation)


async def _delete_vm(project: str, vm_name: str, zone: str) -> None:
    token = await run_blocking(db_executor, _get_access_token)
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{vm_name}"
    response = await _gce_request("DELETE", url, token)
    if response.status_code == 404:
        return
    response.raise_for_status()
    operation = response.json().get("name")
    if operation:
        await _operation(project, zone, operation)


def _verify_agent_vm_identity(token: str) -> dict[str, Any]:
    audience = os.getenv("AGENT_VM_STOP_AUDIENCE", "").strip()
    if not audience:
        raise RuntimeError("Agent VM stop broker audience is not configured")
    claims = google.oauth2.id_token.verify_token(
        token,
        request=google.auth.transport.requests.Request(),
        audience=audience,
    )
    if not isinstance(claims, dict):
        raise ValueError("Agent VM identity token claims are not an object")
    return claims


def _compute_identity_fields(claims: dict[str, Any]) -> tuple[str, str, str, str, str]:
    google_claims = claims.get("google")
    compute = google_claims.get("compute_engine") if isinstance(google_claims, dict) else None
    if not isinstance(compute, dict):
        raise ValueError("Agent VM identity token is not a full Compute Engine identity token")
    project = str(compute.get("project_id") or "")
    name = str(compute.get("instance_name") or "")
    zone = str(compute.get("zone") or "")
    instance_id = str(compute.get("instance_id") or "")
    email = str(claims.get("email") or "")
    if not project or not name or not zone or not instance_id or not email or claims.get("email_verified") is not True:
        raise ValueError("Agent VM identity token is missing required Compute Engine claims")
    if (
        project != _project()
        or not re.fullmatch(r"[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?", zone)
        or not re.fullmatch(r"omi-agent-[a-z0-9-]+", name)
        or not instance_id.isdigit()
    ):
        raise ValueError("Agent VM identity token is outside the broker scope")
    expected_service_account = os.getenv("GCE_RUNTIME_SERVICE_ACCOUNT") or _service_account()
    if email != expected_service_account:
        raise ValueError("Agent VM identity token is not from the Agent VM runtime identity")
    return project, zone, name, email, instance_id


def _find_vm_owner(vm_name: str) -> tuple[str, dict[str, Any]] | None:
    snapshots = (
        get_firestore_client()
        .collection("users")
        .where(filter=FieldFilter("agentVm.vmName", "==", vm_name))
        .limit(2)
        .stream()
    )
    owner: tuple[str, dict[str, Any]] | None = None
    for snapshot in snapshots:
        data = snapshot.to_dict() or {}
        vm = data.get("agentVm")
        if isinstance(vm, dict) and vm.get("vmName") == vm_name:
            if owner is not None:
                raise ValueError("Agent VM name maps to multiple owners")
            owner = str(snapshot.id), vm
    return owner


def _stop_broker_rate_allowed(request: Request) -> bool:
    subject = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - _STOP_BROKER_RATE_WINDOW_SECONDS
    with _stop_broker_attempts_lock:
        for key, stamps in list(_stop_broker_attempts.items()):
            recent = [stamp for stamp in stamps if stamp >= cutoff]
            if recent:
                _stop_broker_attempts[key] = recent
            else:
                _stop_broker_attempts.pop(key, None)
        attempts = list(_stop_broker_attempts.get(subject, []))
        if len(attempts) >= _STOP_BROKER_RATE_LIMIT:
            _stop_broker_attempts[subject] = attempts
            return False
        attempts.append(now)
        _stop_broker_attempts[subject] = attempts
        return True


@router.post("/v2/agent/vm/stop-self")
async def stop_self(request: Request) -> dict[str, str]:
    """Broker the idle VM stop after verifying the VM's full GCE identity.

    The endpoint intentionally has no Firebase-user dependency: only a VM can
    present the audience-bound Google identity token, and the Firestore owner
    lookup is the second authorization boundary.
    """
    if not _stop_broker_rate_allowed(request):
        raise HTTPException(status_code=429, detail="Agent VM stop broker rate limit exceeded")
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing VM identity")
    try:
        claims = await run_blocking(db_executor, _verify_agent_vm_identity, header[7:].strip())
        project, zone, vm_name, _, instance_id = _compute_identity_fields(claims)
        owner = await run_blocking(db_executor, _find_vm_owner, vm_name)
    except (RuntimeError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=403, detail="Invalid Agent VM identity") from exc
    if owner is None:
        raise HTTPException(status_code=404, detail="Agent VM owner not found")
    uid, vm = owner
    owner_zone = str(vm.get("zone") or "")
    if not owner_zone or owner_zone != zone:
        raise HTTPException(status_code=403, detail="Agent VM identity zone does not match its owner record")
    auth_token = str(vm.get("authToken") or "")
    if not auth_token or not await run_blocking(db_executor, _vm_lifecycle_allowed, uid, vm_name, auth_token):
        raise HTTPException(status_code=409, detail="Agent VM owner is no longer active")
    if _reconcile_in_progress(vm):
        return {"status": "updating", "vmName": vm_name}
    stop_owner = f"idle-stop:{uuid.uuid4().hex}"
    claimed = await run_blocking(db_executor, claim_vm_lease, uid, vm_name, auth_token, stop_owner)
    if not claimed:
        return {"status": "updating", "vmName": vm_name}
    persisted_stopped = False
    try:
        status, instance = await _instance(project, zone, vm_name)
        if instance is None:
            raise HTTPException(status_code=404, detail="Agent VM instance not found")
        if str(instance.get("id") or "") != instance_id or str(instance.get("name") or "") != vm_name:
            raise HTTPException(status_code=403, detail="Agent VM runtime identity does not match the live instance")
        if status == "RUNNING":
            await _stop_vm(project, vm_name, zone)
            persisted_stopped = True
            return {"status": "stopping", "vmName": vm_name}
        if status in {"STOPPED", "TERMINATED"}:
            persisted_stopped = True
        return {"status": "stopped", "vmName": vm_name}
    finally:
        await run_blocking(
            db_executor,
            update_vm_reconcile,
            uid,
            vm_name,
            auth_token,
            stop_owner,
            {"state": "ready", **clear_vm_reconcile_lease_fields()},
            {"status": "stopped"} if persisted_stopped else None,
        )


async def _delete_late_vm_or_record(uid: str, project: str, vm_name: str, zone: str) -> None:
    try:
        await _delete_vm(project, vm_name, zone)
    except Exception:
        await run_blocking(db_executor, users_db.record_late_agent_vm_cleanup, uid, vm_name, zone)
        raise


async def _cleanup_possible_late_vm(uid: str, project: str, vm_name: str, zone: str) -> None:
    """Delete one possibly-created VM, durably recording a provider failure."""
    try:
        await _delete_late_vm_or_record(uid, project, vm_name, zone)
    except Exception as exc:
        logger.error("Late Agent VM cleanup deferred for uid=%s: %s", uid, exc)


async def _provision_background(
    uid: str, project: str, source_image: str, bucket: str, vm_name: str, auth_token: str, service_account: str
) -> None:
    if not await run_blocking(db_executor, _vm_lifecycle_allowed, uid, vm_name, auth_token):
        logger.info("Skipping Agent VM create after deletion/owner transition for uid=%s", uid)
        return
    try:
        ip = await _create_vm(project, source_image, bucket, vm_name, auth_token, service_account)
    except AgentVmCreateOutcomeUnknown as exc:
        logger.error("Agent VM provisioning failed for uid=%s: %s", uid, exc)
        if not await run_blocking(db_executor, _vm_lifecycle_allowed, uid, vm_name, auth_token):
            await _cleanup_possible_late_vm(uid, project, vm_name, _ZONE)
            return
        await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "error")
        return
    except Exception as exc:
        logger.error("Agent VM provisioning failed before provider acceptance for uid=%s: %s", uid, exc)
        if await run_blocking(db_executor, _vm_lifecycle_allowed, uid, vm_name, auth_token):
            await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "error")
        return

    if not await run_blocking(db_executor, _vm_lifecycle_allowed, uid, vm_name, auth_token):
        logger.warning("Deleting late-created Agent VM after deletion/owner transition for uid=%s", uid)
        await _cleanup_possible_late_vm(uid, project, vm_name, _ZONE)
        return
    updated = await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "ready", ip)
    if not updated:
        await _cleanup_possible_late_vm(uid, project, vm_name, _ZONE)


def _response(vm: dict[str, Any]) -> AgentVmResponse:
    return AgentVmResponse(
        vmName=str(vm["vmName"]),
        zone=str(vm.get("zone") or _ZONE),
        ip=vm.get("ip"),
        status=str(vm.get("status") or "provisioning"),
        authToken=str(vm.get("authToken") or ""),
        createdAt=str(vm.get("createdAt") or ""),
        lastQueryAt=vm.get("lastQueryAt"),
    )


@router.post("/v2/agent/provision", response_model=ProvisionAgentResponse)
async def provision_agent_vm(
    background_tasks: BackgroundTasks, uid: str = Depends(_authorized_desktop_user)
) -> ProvisionAgentResponse:
    if _agent_disabled():
        raise HTTPException(status_code=503, detail="Agent VM provisioning is disabled")
    try:
        project = _project()
        source_image = _source_image(project)
        bucket = _gcs_bucket()
        service_account = _service_account()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    generation = uuid.uuid4().hex
    vm_name = f"omi-agent-{hashlib.sha256(uid.encode('utf-8')).hexdigest()[:20]}-{generation[:8]}"
    auth_token = f"omi-{generation}"
    created_at = _now()
    candidate = {
        "vmName": vm_name,
        "zone": _ZONE,
        "status": "provisioning",
        "authToken": auth_token,
        "createdAt": created_at,
    }
    try:
        vm, claimed = await run_blocking(db_executor, _claim_vm_if_allowed, uid, candidate)
    except AccountDeletionAccessBlocked as exc:
        raise HTTPException(status_code=403, detail="account_deletion_in_progress") from exc
    if not claimed:
        if _reconcile_in_progress(vm):
            return ProvisionAgentResponse(
                status="exists",
                vmName=str(vm["vmName"]),
                ip=None,
                authToken=str(vm.get("authToken") or ""),
                agentStatus="updating",
            )
        return ProvisionAgentResponse(
            status="exists",
            vmName=str(vm["vmName"]),
            ip=vm.get("ip"),
            authToken=str(vm.get("authToken") or ""),
            agentStatus=str(vm.get("status") or "provisioning"),
        )
    background_tasks.add_task(
        _provision_background, uid, project, source_image, bucket, vm_name, auth_token, service_account
    )
    return ProvisionAgentResponse(
        status="provisioning", vmName=vm_name, authToken=auth_token, agentStatus="provisioning"
    )


@router.get("/v2/agent/status", response_model=AgentVmResponse | None)
async def get_agent_status(
    background_tasks: BackgroundTasks, uid: str = Depends(_authorized_desktop_user)
) -> AgentVmResponse | None:
    if _agent_disabled():
        return None
    del background_tasks
    vm = await run_blocking(db_executor, _get_vm, uid)
    if not vm:
        return None
    if _reconcile_in_progress(vm):
        return _response(_updating_vm(vm))
    status = str(vm.get("status") or "provisioning")
    if status not in {"ready", "error", "stopped"}:
        return _response(vm)
    try:
        project = _project()
        gce_status, instance = await _instance(project, str(vm.get("zone") or _ZONE), str(vm["vmName"]))
        observation = classify_provider_observation(gce_status=gce_status)
    except Exception as exc:
        logger.warning("Agent VM status check failed for uid=%s: %s", uid, exc)
        # GCE UNKNOWN / API blip — do not wipe Firestore ownership.
        return _response(vm)
    usable_cached_ip: bool | None = None
    if observation.kind == "running":
        usable_cached_ip = _is_usable_vm_ip(vm.get("ip"))
        if instance is not None and not usable_cached_ip and _ip(instance) is None:
            logger.warning(
                "Deferring running Agent VM without an external IP to the reconciler for uid=%s",
                uid,
            )
    decision = decide_agent_vm_read(vm, observation, usable_cached_ip=usable_cached_ip)
    if decision.queue_start:
        # Provider 404 / stopped / repairable running: queue fenced reconciler
        # demand. Do not erase the owner pointer here — the reconciler owns
        # missing/grace/session fences and eventual terminal cleanup.
        requested = await run_blocking(
            db_executor,
            request_vm_start,
            uid,
            str(vm["vmName"]),
            str(vm.get("authToken") or ""),
        )
        if not requested:
            return _response(await run_blocking(db_executor, _get_vm, uid) or vm)
    return _response(apply_agent_vm_read_decision(vm, decision))
