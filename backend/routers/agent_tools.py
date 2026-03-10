"""
Agent tools router — exposes Python backend tools to the VM agent.

Endpoints:
- GET  /v1/agent/tools         — returns tool definitions (name, description, parameters)
- POST /v1/agent/execute-tool  — executes a named tool and returns the result
- GET  /v1/agent/vm-status     — returns VM status from Firestore (with restart if stopped)
- POST /v1/agent/vm-ensure     — ensures user has a VM: creates if missing, restarts if stopped
- POST /v1/agent/keepalive     — pings the VM to reset its idle auto-stop timer
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from database._client import db as firestore_db
from database.users import get_agent_vm
from utils.other.endpoints import get_current_user_uid
from utils.retrieval.agentic import agent_config_context, CORE_TOOLS
from utils.retrieval.tools.app_tools import load_app_tools
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

router = APIRouter()

GCE_PROJECT = os.environ.get("GCE_PROJECT_ID", os.environ.get("GOOGLE_CLOUD_PROJECT", "based-hardware"))
GCE_ZONE = "us-central1-a"
GCE_SOURCE_IMAGE = os.environ.get("GCE_SOURCE_IMAGE", f"projects/{GCE_PROJECT}/global/images/family/omi-agent")
AGENT_GCS_BUCKET = os.environ.get("AGENT_GCS_BUCKET", "based-hardware-agent")


# --------------- GCE helpers ---------------


def _get_gce_access_token() -> str:
    """Get a GCE access token via Application Default Credentials."""
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


async def _check_gce_status(vm_name: str, zone: str) -> str:
    """Check the actual GCE instance status (RUNNING, TERMINATED, STOPPED, etc.)."""
    token = _get_gce_access_token()
    url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            logger.error(f"[gce] Failed to get instance status: {resp.status_code} {sanitize(resp.text)}")
            return "UNKNOWN"
        return resp.json().get("status", "UNKNOWN")


async def _start_vm_and_wait(vm_name: str, zone: str) -> str:
    """Start a stopped/terminated GCE VM and wait for it to get an IP. Returns the new IP."""
    import time

    t0 = time.monotonic()
    token = _get_gce_access_token()
    start_url = (
        f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}/start"
    )

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(start_url, headers={"Authorization": f"Bearer {token}"}, content=b"")
        if resp.status_code not in (200, 204):
            raise Exception(f"GCE start failed: {resp.status_code} {sanitize(resp.text)}")
        t_start = time.monotonic() - t0
        logger.info(f"[vm-start] {vm_name} start API call: {t_start:.1f}s")

        op_name = resp.json().get("name")
        if not op_name:
            raise Exception("Missing operation name in GCE start response")

        op_url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/operations/{op_name}"
        for i in range(24):
            await asyncio.sleep(5)
            token = _get_gce_access_token()
            status_resp = await client.get(op_url, headers={"Authorization": f"Bearer {token}"})
            status = status_resp.json()
            if status.get("status") == "DONE":
                if "error" in status:
                    raise Exception(f"GCE start operation failed: {status['error']}")
                t_op = time.monotonic() - t0
                logger.info(f"[vm-start] {vm_name} operation done after {i + 1} polls: {t_op:.1f}s")
                break

        # Poll for a valid external IP (may take a few seconds after operation completes)
        instance_url = (
            f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
        )
        ip = None
        for attempt in range(6):
            token = _get_gce_access_token()
            inst_resp = await client.get(instance_url, headers={"Authorization": f"Bearer {token}"})
            instance = inst_resp.json()
            try:
                candidate = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
                if candidate and candidate != "unknown":
                    ip = candidate
                    t_ip = time.monotonic() - t0
                    logger.info(f"[vm-start] {vm_name} got IP {ip} on attempt {attempt + 1}: {t_ip:.1f}s total")
                    break
            except (KeyError, IndexError):
                pass
            if attempt < 5:
                logger.info(f"[vm-start] {vm_name} no IP yet, retrying ({attempt + 1}/6)...")
                await asyncio.sleep(3)

        if not ip:
            t_fail = time.monotonic() - t0
            logger.error(f"[vm-start] {vm_name} failed to get IP after 6 attempts: {t_fail:.1f}s")
            ip = "unknown"

        return ip


def _update_firestore_vm(uid: str, ip: str | None, status: str):
    """Update the user's agentVm fields in Firestore."""
    update = {"agentVm.status": status}
    if ip:
        update["agentVm.ip"] = ip
    firestore_db.collection('users').document(uid).update(update)


def _set_firestore_vm(uid: str, vm_name: str, zone: str, ip: str | None, status: str, auth_token: str):
    """Write the full agentVm document to Firestore (for initial provisioning)."""
    now = datetime.now(timezone.utc).isoformat()
    vm_data = {
        "vmName": vm_name,
        "zone": zone,
        "status": status,
        "authToken": auth_token,
        "createdAt": now,
    }
    if ip:
        vm_data["ip"] = ip
    firestore_db.collection('users').document(uid).set({"agentVm": vm_data}, merge=True)


async def _create_gce_vm(vm_name: str, auth_token: str) -> str:
    """Create a GCE VM from the omi-agent image family. Returns the external IP."""
    zone = GCE_ZONE
    startup_script = (
        f"#!/bin/bash\ncurl -sf https://storage.googleapis.com/{AGENT_GCS_BUCKET}/startup.sh"
        f" -o /tmp/omi-startup.sh && bash /tmp/omi-startup.sh\n"
    )

    url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances"
    body = {
        "name": vm_name,
        "machineType": f"zones/{zone}/machineTypes/e2-small",
        "disks": [
            {
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": GCE_SOURCE_IMAGE,
                    "diskSizeGb": "50",
                    "diskType": f"zones/{zone}/diskTypes/pd-ssd",
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
            "items": [
                {"key": "startup-script", "value": startup_script},
                {"key": "auth-token", "value": auth_token},
            ]
        },
    }

    token = _get_gce_access_token()
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
        if resp.status_code not in (200, 204):
            raise Exception(f"GCE insert failed: {resp.status_code} {sanitize(resp.text)}")

        op_name = resp.json().get("name")
        if not op_name:
            raise Exception("Missing operation name in GCE insert response")

        # Poll operation until done (max ~2 minutes)
        op_url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/operations/{op_name}"
        op_done = False
        for i in range(24):
            await asyncio.sleep(5)
            token = _get_gce_access_token()
            status_resp = await client.get(op_url, headers={"Authorization": f"Bearer {token}"})
            op_status = status_resp.json()
            if op_status.get("status") == "DONE":
                if "error" in op_status:
                    raise Exception(f"GCE insert operation failed: {op_status['error']}")
                logger.info(f"[vm-create] {vm_name} operation done after {i + 1} polls")
                op_done = True
                break
        if not op_done:
            raise Exception(f"GCE insert timed out after 120s for {vm_name}")

        # Get external IP
        instance_url = (
            f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}"
        )
        for attempt in range(6):
            token = _get_gce_access_token()
            inst_resp = await client.get(instance_url, headers={"Authorization": f"Bearer {token}"})
            instance = inst_resp.json()
            try:
                candidate = instance["networkInterfaces"][0]["accessConfigs"][0]["natIP"]
                if candidate:
                    logger.info(f"[vm-create] {vm_name} got IP {candidate} on attempt {attempt + 1}")
                    return candidate
            except (KeyError, IndexError):
                pass
            if attempt < 5:
                await asyncio.sleep(3)

        raise Exception(f"Failed to get external IP for {vm_name} after 6 attempts")


async def _provision_vm_background(uid: str, vm_name: str, auth_token: str):
    """Background task: create a new GCE VM, update Firestore when ready."""
    try:
        ip = await _create_gce_vm(vm_name, auth_token)
        _set_firestore_vm(uid, vm_name, GCE_ZONE, ip, "ready", auth_token)
        logger.info(f"[vm-ensure] VM {vm_name} created, ip={ip}")
    except Exception as e:
        logger.error(f"[vm-ensure] Failed to create VM {vm_name}: {e}")
        _update_firestore_vm(uid, None, "error")


async def _restart_vm_background(uid: str, vm_name: str, zone: str):
    """Background task: start stopped VM, update Firestore with new IP when ready."""
    try:
        ip = await _start_vm_and_wait(vm_name, zone)
        _update_firestore_vm(uid, ip, "ready")
        logger.info(f"[vm-ensure] VM {vm_name} restarted, ip={ip}")
    except Exception as e:
        logger.error(f"[vm-ensure] Failed to restart VM {vm_name}: {e}")
        _update_firestore_vm(uid, None, "error")


# --------------- endpoints ---------------


def _vm_response(vm: dict, status_override: str | None = None) -> dict:
    """Build a standard VM response dict with all fields the desktop expects."""
    return {
        "has_vm": True,
        "status": status_override or vm.get("status"),
        "vm_name": vm.get("vmName"),
        "ip": vm.get("ip"),
        "auth_token": vm.get("authToken"),
        "zone": vm.get("zone", GCE_ZONE),
        "created_at": vm.get("createdAt"),
        "last_query_at": vm.get("lastQueryAt"),
    }


@router.get("/v1/agent/vm-status")
async def get_vm_status(background_tasks: BackgroundTasks, uid: str = Depends(get_current_user_uid)):
    """Return the user's agent VM info from Firestore. Restarts stopped VMs."""
    vm = get_agent_vm(uid)
    if not vm:
        return {"has_vm": False}

    fs_status = vm.get("status", "")
    vm_name = vm.get("vmName")
    zone = vm.get("zone", GCE_ZONE)

    # For ready/error/stopped VMs, verify actual GCE status and restart if needed
    if fs_status in ("ready", "error", "stopped") and vm_name:
        try:
            gce_status = await _check_gce_status(vm_name, zone)
        except Exception as e:
            logger.warning(f"[vm-status] GCE status check failed for {vm_name}: {e}")
            return _vm_response(vm)

        if gce_status in ("TERMINATED", "STOPPED"):
            logger.info(f"[vm-status] VM {vm_name} is {gce_status}, restarting...")
            _update_firestore_vm(uid, None, "provisioning")
            background_tasks.add_task(_restart_vm_background, uid, vm_name, zone)
            return _vm_response(vm, status_override="provisioning")

        if gce_status == "RUNNING" and fs_status != "ready":
            _update_firestore_vm(uid, vm.get("ip"), "ready")
            return _vm_response(vm, status_override="ready")

    return _vm_response(vm)


@router.post("/v1/agent/vm-ensure")
async def ensure_vm(background_tasks: BackgroundTasks, uid: str = Depends(get_current_user_uid)):
    """Ensure user has a VM: create if missing, restart if stopped."""
    vm = get_agent_vm(uid)

    # No VM exists — provision a new one
    if not vm:
        uid_prefix = uid[:12].lower() if len(uid) > 12 else uid.lower()
        vm_name = f"omi-agent-{uid_prefix}"
        auth_token = f"omi-{uuid.uuid4()}"

        # Claim the slot in Firestore before spawning background creation
        _set_firestore_vm(uid, vm_name, GCE_ZONE, None, "provisioning", auth_token)
        background_tasks.add_task(_provision_vm_background, uid, vm_name, auth_token)
        logger.info(f"[vm-ensure] Provisioning new VM {vm_name} for uid={uid[:8]}...")

        return {
            "has_vm": True,
            "status": "provisioning",
            "vm_name": vm_name,
            "ip": None,
            "auth_token": auth_token,
            "zone": GCE_ZONE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_query_at": None,
        }

    vm_name = vm.get("vmName")
    zone = vm.get("zone", GCE_ZONE)
    fs_status = vm.get("status", "")

    # If Firestore already says provisioning, don't double-start
    if fs_status == "provisioning":
        return _vm_response(vm)

    # Check actual GCE status for ready/error/stopped VMs
    if fs_status in ("ready", "error", "stopped") and vm_name:
        try:
            gce_status = await _check_gce_status(vm_name, zone)
        except Exception as e:
            logger.error(f"[vm-ensure] GCE status check failed: {e}")
            return _vm_response(vm)

        if gce_status in ("TERMINATED", "STOPPED"):
            logger.info(f"[vm-ensure] VM {vm_name} is {gce_status}, restarting...")
            _update_firestore_vm(uid, None, "provisioning")
            background_tasks.add_task(_restart_vm_background, uid, vm_name, zone)
            return _vm_response(vm, status_override="provisioning")

        if gce_status == "RUNNING" and fs_status != "ready":
            _update_firestore_vm(uid, vm.get("ip"), "ready")
            return _vm_response(vm, status_override="ready")

    return _vm_response(vm)


@router.post("/v1/agent/keepalive")
async def keepalive(uid: str = Depends(get_current_user_uid)):
    """Ping the VM's /ping endpoint to reset its idle auto-stop timer."""
    vm = get_agent_vm(uid)
    if not vm or vm.get("status") != "ready":
        return {"ok": False, "reason": "no_vm"}

    vm_ip = vm.get("ip")
    auth_token = vm.get("authToken")
    if not vm_ip or not auth_token:
        return {"ok": False, "reason": "missing_vm_info"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"http://{vm_ip}:8080/ping?token={auth_token}")
            if resp.status_code == 200:
                return {"ok": True}
            logger.warning(f"[keepalive] VM ping returned {resp.status_code}")
            return {"ok": False, "reason": "ping_failed"}
    except Exception as e:
        logger.warning(f"[keepalive] VM ping failed: {e}")
        return {"ok": False, "reason": "unreachable"}


def _tool_schema(t) -> dict:
    """Extract a clean JSON schema from a LangChain tool."""
    schema = t.args_schema.model_json_schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = list(schema.get("required", []))

    # Strip the 'config' parameter — it's internal LangChain plumbing
    props.pop("config", None)
    if "config" in required:
        required.remove("config")

    return {
        "name": t.name,
        "description": t.description or "",
        "parameters": {
            "type": "object",
            "properties": props,
            "required": required,
        },
    }


@router.get("/v1/agent/tools")
def list_tools(uid: str = Depends(get_current_user_uid)):
    """Return all available tool definitions for a user."""
    tools = []

    for t in CORE_TOOLS:
        tools.append(_tool_schema(t))

    try:
        app_tools = load_app_tools(uid)
        for t in app_tools:
            tools.append(_tool_schema(t))
    except Exception as e:
        logger.error(f"⚠️ Error loading app tools for agent_tools: {e}")

    return {"tools": tools}


class ExecuteToolRequest(BaseModel):
    tool_name: str
    params: dict = {}


@router.post("/v1/agent/execute-tool")
async def execute_tool(
    body: ExecuteToolRequest,
    uid: str = Depends(get_current_user_uid),
):
    """Execute a named tool and return its result."""
    # Set up agent_config_context so tools can resolve the UID
    config = {
        "configurable": {
            "user_id": uid,
        },
    }
    agent_config_context.set(config)

    # Find the tool
    all_tools = list(CORE_TOOLS)
    try:
        app_tools = load_app_tools(uid)
        all_tools.extend(app_tools)
    except Exception as e:
        logger.error(f"⚠️ Error loading app tools: {e}")

    target = None
    for t in all_tools:
        if t.name == body.tool_name:
            target = t
            break

    if target is None:
        raise HTTPException(status_code=404, detail=f"Tool '{body.tool_name}' not found")

    # Strip config param if caller accidentally included it
    params = {k: v for k, v in body.params.items() if k != "config"}

    try:
        # Prefer async coroutine if available (app tools), else sync invoke
        if hasattr(target, "coroutine") and target.coroutine is not None:
            result = await target.coroutine(**params)
        else:
            # Pass config as second arg (LangChain RunnableConfig), not as tool input
            result = target.invoke(params, config=config)
        return {"result": str(result)}
    except Exception as e:
        logger.error(f"❌ Error executing tool {body.tool_name}: {e}")
        return {"error": str(e)}
