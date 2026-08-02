import asyncio
import ipaddress
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from google.cloud.firestore import DELETE_FIELD, transactional
from pydantic import BaseModel, ConfigDict, Field

from database._client import get_firestore_client
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid
from utils.subscription import is_trial_paywalled

logger = logging.getLogger(__name__)
router = APIRouter()
_ZONE = "us-central1-a"


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
    project = os.getenv("GCE_PROJECT_ID") or os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GCP_PROJECT_ID")
    if not project:
        raise RuntimeError("GCE project is not configured")
    return project


def _source_image(project: str) -> str:
    return os.getenv("GCE_SOURCE_IMAGE") or f"projects/{project}/global/images/family/omi-agent"


def _gcs_bucket() -> str:
    bucket = os.getenv("AGENT_GCS_BUCKET")
    if not bucket:
        raise RuntimeError("AGENT_GCS_BUCKET is not configured")
    return bucket


def _get_vm(uid: str) -> dict[str, Any] | None:
    snapshot = get_firestore_client().collection("users").document(uid).get()
    if not snapshot.exists:
        return None
    vm = snapshot.to_dict().get("agentVm")
    return vm if isinstance(vm, dict) and vm.get("vmName") else None


def _set_vm(
    uid: str,
    vm_name: str,
    status: str,
    auth_token: str,
    created_at: str,
    ip: str | None = None,
    zone: str = _ZONE,
) -> None:
    if status == "ready" and not _is_usable_vm_ip(ip):
        raise ValueError("refusing to persist ready agentVm without a usable IP address")
    vm: dict[str, Any] = {
        "vmName": vm_name,
        "zone": zone,
        "status": status,
        "authToken": auth_token,
        "createdAt": created_at,
    }
    if ip:
        vm["ip"] = ip
    get_firestore_client().collection("users").document(uid).set({"agentVm": vm}, merge=True)


@transactional
def _set_vm_if_current_txn(
    transaction,
    user_ref,
    expected_vm_name: str,
    expected_auth_token: str,
    status: str,
    ip: str | None,
    zone: str,
) -> bool:
    snapshot = user_ref.get(transaction=transaction)
    current = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(current, dict):
        return False
    if current.get("vmName") != expected_vm_name or current.get("authToken") != expected_auth_token:
        return False
    if status == "ready" and not _is_usable_vm_ip(ip):
        raise ValueError("refusing to persist ready agentVm without a usable IP address")
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
        client.collection("users").document(uid),
        expected_vm_name,
        expected_auth_token,
        status,
        ip,
        zone,
    )


@transactional
def _delete_vm_if_current_txn(transaction, user_ref, expected_vm_name: str, expected_auth_token: str) -> bool:
    snapshot = user_ref.get(transaction=transaction)
    current = (snapshot.to_dict() or {}).get("agentVm") if snapshot.exists else None
    if not isinstance(current, dict):
        return False
    if current.get("vmName") != expected_vm_name or current.get("authToken") != expected_auth_token:
        return False
    transaction.update(user_ref, {"agentVm": DELETE_FIELD})
    return True


def _delete_vm_if_current(uid: str, expected_vm_name: str, expected_auth_token: str) -> bool:
    client = get_firestore_client()
    return _delete_vm_if_current_txn(
        client.transaction(),
        client.collection("users").document(uid),
        expected_vm_name,
        expected_auth_token,
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


async def _create_vm(project: str, source_image: str, bucket: str, vm_name: str, auth_token: str) -> str:
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{_ZONE}/instances"
    startup = f"#!/bin/bash\ncurl -sf https://storage.googleapis.com/{bucket}/startup.sh -o /tmp/omi-startup.sh && bash /tmp/omi-startup.sh\n"
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
        "networkInterfaces": [
            {
                "network": "global/networks/default",
                "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
            }
        ],
        "tags": {"items": ["omi-agent-vm"]},
        "metadata": {
            "items": [{"key": "startup-script", "value": startup}, {"key": "auth-token", "value": auth_token}]
        },
    }
    token = await run_blocking(db_executor, _get_access_token)
    response = await _gce_request("POST", url, token, body)
    response.raise_for_status()
    operation = response.json().get("name")
    if not operation:
        raise RuntimeError("GCE create response omitted operation name")
    await _operation(project, _ZONE, operation)
    _, instance = await _instance(project, _ZONE, vm_name)
    if instance is None:
        raise RuntimeError("GCE created VM is unavailable")
    ip = _ip(instance)
    if ip is None:
        raise RuntimeError("GCE created VM has no usable IP address")
    return ip


async def _start_vm(project: str, vm_name: str, zone: str) -> str:
    token = await run_blocking(db_executor, _get_access_token)
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{vm_name}/start"
    response = await _gce_request("POST", url, token)
    response.raise_for_status()
    operation = response.json().get("name")
    if not operation:
        raise RuntimeError("GCE start response omitted operation name")
    await _operation(project, zone, operation)
    _, instance = await _instance(project, zone, vm_name)
    if instance is None:
        raise RuntimeError("GCE restarted VM is unavailable")
    ip = _ip(instance)
    if ip is None:
        raise RuntimeError("GCE restarted VM has no usable IP address")
    return ip


async def _provision_background(
    uid: str, project: str, source_image: str, bucket: str, vm_name: str, auth_token: str
) -> None:
    try:
        ip = await _create_vm(project, source_image, bucket, vm_name, auth_token)
        await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "ready", ip)
    except Exception as exc:
        logger.error("Agent VM provisioning failed for uid=%s: %s", uid, exc)
        await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "error")


async def _restart_background(uid: str, project: str, vm: dict[str, Any]) -> None:
    vm_name = str(vm["vmName"])
    zone = str(vm.get("zone") or _ZONE)
    auth_token = str(vm.get("authToken") or "")
    try:
        ip = await _start_vm(project, vm_name, zone)
        await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "ready", ip, zone)
    except Exception as exc:
        logger.error("Agent VM restart failed for uid=%s: %s", uid, exc)
        await run_blocking(db_executor, _set_vm_if_current, uid, vm_name, auth_token, "error", None, zone)


async def _recover_background(uid: str, vm: dict[str, Any], ip: str) -> None:
    await run_blocking(
        db_executor,
        _set_vm_if_current,
        uid,
        str(vm["vmName"]),
        str(vm.get("authToken") or ""),
        "ready",
        ip,
        str(vm.get("zone") or _ZONE),
    )


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
    vm = await run_blocking(db_executor, _get_vm, uid)
    if vm:
        return ProvisionAgentResponse(
            status="exists",
            vmName=str(vm["vmName"]),
            ip=vm.get("ip"),
            authToken=str(vm.get("authToken") or ""),
            agentStatus=str(vm.get("status") or "provisioning"),
        )
    try:
        project = _project()
        source_image = _source_image(project)
        bucket = _gcs_bucket()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    vm_name = f"omi-agent-{uid[:12].lower()}"
    auth_token = f"omi-{uuid.uuid4()}"
    created_at = _now()
    await run_blocking(db_executor, _set_vm, uid, vm_name, "provisioning", auth_token, created_at)
    background_tasks.add_task(_provision_background, uid, project, source_image, bucket, vm_name, auth_token)
    return ProvisionAgentResponse(
        status="provisioning", vmName=vm_name, authToken=auth_token, agentStatus="provisioning"
    )


@router.get("/v2/agent/status", response_model=AgentVmResponse | None)
async def get_agent_status(
    background_tasks: BackgroundTasks, uid: str = Depends(_authorized_desktop_user)
) -> AgentVmResponse | None:
    if _agent_disabled():
        return None
    vm = await run_blocking(db_executor, _get_vm, uid)
    if not vm:
        return None
    status = str(vm.get("status") or "provisioning")
    if status not in {"ready", "error", "stopped"}:
        return _response(vm)
    try:
        project = _project()
        gce_status, instance = await _instance(project, str(vm.get("zone") or _ZONE), str(vm["vmName"]))
    except Exception as exc:
        logger.warning("Agent VM status check failed for uid=%s: %s", uid, exc)
        return _response(vm)
    if gce_status == "NOT_FOUND":
        await run_blocking(
            db_executor,
            _delete_vm_if_current,
            uid,
            str(vm["vmName"]),
            str(vm.get("authToken") or ""),
        )
        return None
    if gce_status in {"TERMINATED", "STOPPED"}:
        pending = {**vm, "status": "provisioning", "ip": None}
        await run_blocking(
            db_executor,
            _set_vm,
            uid,
            str(vm["vmName"]),
            "provisioning",
            str(vm.get("authToken") or ""),
            _now(),
            None,
            str(vm.get("zone") or _ZONE),
        )
        background_tasks.add_task(_restart_background, uid, project, vm)
        return _response(pending)
    if (
        gce_status == "RUNNING"
        and instance is not None
        and (status in {"error", "stopped"} or not _is_usable_vm_ip(vm.get("ip")))
    ):
        pending = {**vm, "status": "provisioning", "ip": None}
        instance_ip = _ip(instance)
        if instance_ip is None:
            return _response(pending)
        background_tasks.add_task(_recover_background, uid, vm, instance_ip)
        return _response(pending)
    return _response(vm)
