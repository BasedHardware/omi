"""
Agent tools router — exposes Python backend tools to the VM agent.

Endpoints:
- GET  /v1/agent/tools         — returns tool definitions (name, description, parameters)
- POST /v1/agent/execute-tool  — executes a named tool and returns the result
- GET  /v1/agent/vm-status     — returns basic VM status from Firestore
- POST /v1/agent/vm-ensure     — requests reconciliation for an unavailable VM, returns current state
- POST /v1/agent/keepalive     — pings the VM to reset its idle auto-stop timer
"""

import logging
from typing import Any

from utils.executors import db_executor, run_blocking

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from database.users import get_agent_vm
from services.agent_vm_lifecycle import reconcile_requested, request_vm_start
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.retrieval.agentic import agent_config_context, CORE_TOOLS
from utils.retrieval.tool_result_boundaries import preserve_chat_memory_tool_result_boundary
from utils.retrieval.tools.app_tools import load_app_tools
from utils.log_sanitizer import sanitize

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

router = APIRouter()

# Legacy placeholder that earlier builds persisted as agentVm.ip when the GCE
# IP poll timed out. Never written any more; still read so already-poisoned
# records are re-provisioned instead of being reported ready.
UNRESOLVED_VM_IP = "unknown"


class AgentVmInfo(BaseModel):
    has_vm: bool
    status: str | None = None


class AgentKeepaliveResponse(BaseModel):
    ok: bool
    reason: str | None = None


class AgentToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class AgentToolsResponse(BaseModel):
    tools: list[AgentToolSchema]


def _is_usable_vm_ip(ip) -> bool:
    """True when `ip` is an address a caller can actually dial.

    `UNRESOLVED_VM_IP` is truthy, so a stored placeholder satisfies every
    `if ip:` reader while resolving to nothing.
    """
    return isinstance(ip, str) and bool(ip) and ip != UNRESOLVED_VM_IP


# --------------- endpoints ---------------


@router.get("/v1/agent/vm-status", response_model=AgentVmInfo)
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


@router.post("/v1/agent/vm-ensure", response_model=AgentVmInfo)
async def ensure_vm(background_tasks: BackgroundTasks, uid: str = Depends(get_current_user_uid)):
    """Queue a fenced reconciliation when the persisted VM is unavailable."""
    del background_tasks
    vm = await run_blocking(db_executor, get_agent_vm, uid)
    if not vm:
        return {"has_vm": False}

    if reconcile_requested(vm):
        return {"has_vm": True, "status": "updating"}
    # Firestore's IP/status is a cache, not provider availability evidence.
    # Every client ensure records demand; only the reconciler observes GCE and
    # decides whether a healthy VM needs work.
    requested = await run_blocking(
        db_executor,
        request_vm_start,
        uid,
        str(vm.get("vmName") or ""),
        str(vm.get("authToken") or ""),
    )
    return {"has_vm": True, "status": "updating" if requested else str(vm.get("status") or "unknown")}


@router.post("/v1/agent/keepalive", response_model=AgentKeepaliveResponse)
async def keepalive(uid: str = Depends(get_current_user_uid)):
    """Ping the VM's /ping endpoint to reset its idle auto-stop timer."""
    vm = await run_blocking(db_executor, get_agent_vm, uid)
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


@router.get("/v1/agent/tools", response_model=AgentToolsResponse)
def list_tools(uid: str = Depends(get_current_user_uid)):
    """Return all available tool definitions for a user."""
    tools = []

    for t in CORE_TOOLS:
        tools.append(_tool_schema(t))

    degraded = False
    try:
        app_tools = load_app_tools(uid)
    except Exception:
        # Whole app-tool lane unavailable — core tools still serve.
        logger.error("⚠️ Error loading app tools for agent_tools", exc_info=True)
        app_tools = []
        degraded = True
    for t in app_tools:
        try:
            tools.append(_tool_schema(t))
        except Exception:
            # One malformed schema must not drop the remaining app tools.
            logger.error(f"⚠️ Skipping app tool with malformed schema: {getattr(t, 'name', '?')}", exc_info=True)
            degraded = True
    if degraded:
        record_fallback(
            component='agent_tools',
            from_mode='full_toolset',
            to_mode='partial_toolset',
            reason='malformed_doc',
            outcome='degraded',
        )

    return {"tools": tools}


class ExecuteToolRequest(BaseModel):
    tool_name: str
    params: dict = {}


class ExecuteToolResponse(BaseModel):
    result: str | None = None
    error: str | None = None


@router.post("/v1/agent/execute-tool", response_model=ExecuteToolResponse)
async def execute_tool(
    body: ExecuteToolRequest,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "agent:execute_tool")),
):
    """Execute a named tool and return its result."""
    # Set up agent_config_context so tools can resolve the UID
    config = {
        "configurable": {
            "user_id": uid,
        },
    }
    agent_config_context.set(config)

    # Find the tool. `load_app_tools` reads Redis plus one Firestore document
    # per enabled app, so it must not run on the event loop — see the canonical
    # path in utils/retrieval/agentic.py.
    all_tools = list(CORE_TOOLS)
    try:
        app_tools = await run_blocking(db_executor, load_app_tools, uid)
        all_tools.extend(app_tools)
    except Exception as error:
        logger.error("⚠️ Error loading app tools error_type=%s", type(error).__name__)
        record_fallback(
            component='agent_tools',
            from_mode='full_toolset',
            to_mode='partial_toolset',
            reason='other',
            outcome='degraded',
        )

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
            # Every CORE_TOOLS entry is a sync @tool that fans out to Firestore
            # and Pinecone, so invoking it here would park the whole event loop
            # for the duration. `run_blocking` copies the current context, so
            # `agent_config_context` still resolves inside the worker thread.
            # Pass config as second arg (LangChain RunnableConfig), not as tool input
            result = await run_blocking(db_executor, target.invoke, params, config=config)
        result = preserve_chat_memory_tool_result_boundary(body.tool_name, str(result))
        return {"result": result}
    except Exception as error:
        # Exception text can embed caller params (pydantic renders
        # `input_value=...`), so keep it off both the log and response planes.
        logger.error("❌ Error executing tool %s error_type=%s", body.tool_name, type(error).__name__)
        return {"error": "Tool execution failed"}
