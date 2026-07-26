import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from google.cloud.firestore import DELETE_FIELD
from pydantic import BaseModel, ConfigDict, Field

from database._client import get_firestore_client
from utils.executors import db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid

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


def _delete_vm(uid: str) -> None:
    get_firestore_client().collection("users").document(uid).update({"agentVm": DELETE_FIELD})


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


def _ip(instance: dict[str, Any]) -> str:
    try:
        return str(instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"])
    except (KeyError, IndexError, TypeError):
        return "unknown"


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
    return _ip(instance)


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
    return _ip(instance)


async def _provision_background(
    uid: str, project: str, source_image: str, bucket: str, vm_name: str, auth_token: str
) -> None:
    try:
        ip = await _create_vm(project, source_image, bucket, vm_name, auth_token)
        await run_blocking(db_executor, _set_vm, uid, vm_name, "ready", auth_token, _now(), ip)
    except Exception as exc:
        logger.error("Agent VM provisioning failed for uid=%s: %s", uid, exc)
        await run_blocking(db_executor, _set_vm, uid, vm_name, "error", auth_token, _now())


async def _restart_background(uid: str, project: str, vm: dict[str, Any]) -> None:
    vm_name = str(vm["vmName"])
    zone = str(vm.get("zone") or _ZONE)
    auth_token = str(vm.get("authToken") or "")
    try:
        ip = await _start_vm(project, vm_name, zone)
        await run_blocking(db_executor, _set_vm, uid, vm_name, "ready", auth_token, _now(), ip, zone)
    except Exception as exc:
        logger.error("Agent VM restart failed for uid=%s: %s", uid, exc)
        await run_blocking(db_executor, _set_vm, uid, vm_name, "error", auth_token, _now(), None, zone)


async def _recover_background(uid: str, vm: dict[str, Any], ip: str) -> None:
    await run_blocking(
        db_executor,
        _set_vm,
        uid,
        str(vm["vmName"]),
        "ready",
        str(vm.get("authToken") or ""),
        _now(),
        ip,
        str(vm.get("zone") or _ZONE),
    )


def _response(vm: dict[str, Any]) -> AgentVmResponse:
    return AgentVmResponse(
        vm_name=str(vm["vmName"]),
        zone=str(vm.get("zone") or _ZONE),
        ip=vm.get("ip"),
        status=str(vm.get("status") or "provisioning"),
        auth_token=str(vm.get("authToken") or ""),
        created_at=str(vm.get("createdAt") or ""),
        last_query_at=vm.get("lastQueryAt"),
    )


@router.post("/v2/agent/provision", response_model=ProvisionAgentResponse)
async def provision_agent_vm(
    background_tasks: BackgroundTasks, uid: str = Depends(get_current_user_uid)
) -> ProvisionAgentResponse:
    if _agent_disabled():
        raise HTTPException(status_code=503, detail="Agent VM provisioning is disabled")
    vm = await run_blocking(db_executor, _get_vm, uid)
    if vm:
        return ProvisionAgentResponse(
            status="exists",
            vm_name=str(vm["vmName"]),
            ip=vm.get("ip"),
            auth_token=str(vm.get("authToken") or ""),
            agent_status=str(vm.get("status") or "provisioning"),
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
        status="provisioning", vm_name=vm_name, auth_token=auth_token, agent_status="provisioning"
    )


@router.get("/v2/agent/status", response_model=AgentVmResponse | None)
async def get_agent_status(
    background_tasks: BackgroundTasks, uid: str = Depends(get_current_user_uid)
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
        await run_blocking(db_executor, _delete_vm, uid)
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
    if gce_status == "RUNNING" and status in {"error", "stopped"} and instance is not None:
        pending = {**vm, "status": "provisioning", "ip": None}
        background_tasks.add_task(_recover_background, uid, vm, _ip(instance))
        return _response(pending)
    return _response(vm)
