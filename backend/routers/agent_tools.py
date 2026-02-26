"""
Agent tools router — exposes Python backend tools to the VM agent.

Endpoints:
- GET  /v1/agent/tools         — returns tool definitions (name, description, parameters)
- POST /v1/agent/execute-tool  — executes a named tool and returns the result
- GET  /v1/agent/vm-status     — returns basic VM status from Firestore
- POST /v1/agent/vm-ensure     — checks VM status, restarts if stopped, returns current state
- POST /v1/agent/keepalive     — pings the VM to reset its idle auto-stop timer
"""

import asyncio
import logging
from datetime import datetime, timezone

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from database.users import get_agent_vm
from utils.other.endpoints import get_current_user_uid
from utils.retrieval.agentic import agent_config_context, CORE_TOOLS
from utils.retrieval.tools.app_tools import load_app_tools
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

router = APIRouter()

GCE_PROJECT = "based-hardware"


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
        # Start the VM
        resp = await client.post(start_url, headers={"Authorization": f"Bearer {token}"}, content=b"")
        if resp.status_code not in (200, 204):
            raise Exception(f"GCE start failed: {resp.status_code} {sanitize(resp.text)}")
        t_start = time.monotonic() - t0
        logger.info(f"[vm-start] {vm_name} start API call: {t_start:.1f}s")

        op_name = resp.json().get("name")
        if not op_name:
            raise Exception("Missing operation name in GCE start response")

        # Poll operation until done (max ~2 minutes)
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
    from database.users import db as firestore_db

    update = {"agentVm.status": status}
    if ip:
        update["agentVm.ip"] = ip
    firestore_db.collection('users').document(uid).update(update)


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


@router.get("/v1/agent/vm-status")
def get_vm_status(uid: str = Depends(get_current_user_uid)):
    """Return the user's agent VM info from Firestore."""
    vm = get_agent_vm(uid)
    logger.info(f"[vm-status] uid={uid} vm={sanitize(vm)}")
    if not vm or vm.get("status") != "ready":
        return {"has_vm": False}
    return {
        "has_vm": True,
        "status": vm.get("status"),
    }


@router.post("/v1/agent/vm-ensure")
async def ensure_vm(background_tasks: BackgroundTasks, uid: str = Depends(get_current_user_uid)):
    """Check VM status; if stopped/terminated, restart it in the background."""
    vm = get_agent_vm(uid)
    if not vm:
        return {"has_vm": False}

    vm_name = vm.get("vmName")
    zone = vm.get("zone", "us-central1-a")
    fs_status = vm.get("status", "")

    # If Firestore already says provisioning, don't double-start
    if fs_status == "provisioning":
        return {"has_vm": True, "status": "provisioning"}

    # Check actual GCE status for ready/error/stopped VMs
    if fs_status in ("ready", "error", "stopped"):
        try:
            gce_status = await _check_gce_status(vm_name, zone)
        except Exception as e:
            logger.error(f"[vm-ensure] GCE status check failed: {e}")
            return {"has_vm": True, "status": fs_status}

        if gce_status in ("TERMINATED", "STOPPED"):
            logger.info(f"[vm-ensure] VM {vm_name} is {gce_status}, restarting...")
            _update_firestore_vm(uid, None, "provisioning")
            background_tasks.add_task(_restart_vm_background, uid, vm_name, zone)
            return {"has_vm": True, "status": "provisioning"}

        if gce_status == "RUNNING" and fs_status != "ready":
            _update_firestore_vm(uid, vm.get("ip"), "ready")
            return {"has_vm": True, "status": "ready"}

    return {"has_vm": True, "status": fs_status}


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
