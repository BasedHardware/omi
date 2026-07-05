"""User-initiated agent VM lifecycle (stop).

The desktop can start (`/v1/agent/vm-ensure`) and keep-alive (`/v1/agent/keepalive`) the
per-user agent sandbox VM, but there was no way to stop it before the idle auto-stop timer
fires. This exposes a self-scoped stop so a user can end their own GCE compute now.

Hosted in its own light module rather than routers/agent_tools.py: that module imports
utils.retrieval.agentic, which constructs an OpenAI client at import time, so importing it
is not clean. The GCE token helper and status writer are re-inlined here (a few lines) to
keep this module import-pure.
"""

import logging

import google.auth
import google.auth.transport.requests
import httpx
from fastapi import APIRouter, Depends

from database.users import get_agent_vm, db as firestore_db
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize
from utils.other.endpoints import get_current_user_uid

logger = logging.getLogger(__name__)

router = APIRouter()

GCE_PROJECT = "based-hardware"


def _get_gce_access_token() -> str:
    """Get a GCE access token via Application Default Credentials (sync; offload in async)."""
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _set_vm_status(uid: str, status: str) -> None:
    firestore_db.collection('users').document(uid).update({"agentVm.status": status})


@router.post("/v1/agent/vm-stop", tags=['agent'])
async def stop_agent_vm(uid: str = Depends(get_current_user_uid)):
    """Stop the caller's own agent VM to end GCE compute billing.

    Self-scoped: reads only users/{uid}.agentVm, so a user can stop only their own VM.
    Idempotent: an already-stopped (or absent) VM returns without calling GCE again.
    """
    vm = await run_blocking(db_executor, get_agent_vm, uid)
    if not vm:
        return {"ok": False, "reason": "no_vm"}

    vm_name = vm.get("vmName")
    zone = vm.get("zone", "us-central1-a")
    if not vm_name:
        return {"ok": False, "reason": "missing_vm_info"}

    if vm.get("status") == "stopped":
        return {"ok": True, "status": "stopped"}

    token = await run_blocking(db_executor, _get_gce_access_token)
    url = f"https://compute.googleapis.com/compute/v1/projects/{GCE_PROJECT}/zones/{zone}/instances/{vm_name}/stop"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers={"Authorization": f"Bearer {token}"}, content=b"")
    except httpx.HTTPError as e:
        logger.error(f"[vm-stop] GCE stop request failed uid={uid}: {sanitize(str(e))}")
        return {"ok": False, "reason": "unreachable"}

    if resp.status_code not in (200, 204):
        logger.error(f"[vm-stop] GCE stop failed uid={uid}: {resp.status_code} {sanitize(resp.text)}")
        return {"ok": False, "reason": "stop_failed"}

    await run_blocking(db_executor, _set_vm_status, uid, "stopped")
    return {"ok": True, "status": "stopped"}
