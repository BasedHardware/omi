"""Retired Agent VM broker endpoints.

The cloud Agent VM — one GCE instance per registered desktop user running a
Claude coding agent — was retired (2,773 lifetime sessions across 106 users,
zero successful sessions since 2026-08-13, ~0.1% utilization at the July
peak). The provisioning/status broker and the whole control plane behind it
are deleted. These routes remain as permanent tombstones for desktop clients
released before the retirement, whose launch flow still calls them.

Contract (pinned by tests/unit/test_desktop_agent_vm.py):

- ``POST /v2/agent/provision`` -> ``410``. Never ``401``: the desktop
  ``APIClient`` treats any 401 on this path as session invalidation and
  force-signs the user out (``signOutOn401``). A retirement must not sign
  anybody out.
- ``GET /v2/agent/status`` -> ``200`` with a ``null`` body. Never a ``200``
  body reporting ``status: "provisioning"`` without an IP: released clients
  decode that as progress and poll 75 x 5s (~6.25 minutes) before giving up.
- ``POST /v2/agent/vm/stop-self`` -> ``410``. Only the (now deleted) guest
  image ever called it; operator-driven export sessions stop their instance
  with gcloud instead.

All three routes are deliberately unauthenticated: the tombstones expose no
data, and authentication failures are exactly the 401 class this retirement
must never emit.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_AGENT_VM_RETIRED = "The cloud Agent VM has been retired and can no longer be provisioned."


@router.post("/v2/agent/provision")
def provision_agent_vm() -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": _AGENT_VM_RETIRED})


@router.post("/v2/agent/vm/stop-self")
def stop_self() -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": _AGENT_VM_RETIRED})


@router.get("/v2/agent/status")
def get_agent_status() -> JSONResponse:
    # `content=None` serializes to a literal `null` body, which released
    # desktop clients decode as an absent optional and skip silently.
    return JSONResponse(status_code=200, content=None)
