"""Minimal 410 boundaries for retired app-client operations.

These routes have no feature implementation or storage side effects. Keeping
their request shapes accepted lets released clients receive a terminal
retirement response instead of a route/validation error.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from utils.other.endpoints import get_current_user_uid

router = APIRouter()

_RETIRED_JSON_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": {"type": "object", "additionalProperties": True}}},
    }
}


def _retired_response() -> JSONResponse:
    return JSONResponse(
        status_code=410,
        headers={"Cache-Control": "no-store"},
        content={"detail": {"error": "feature_retired"}},
    )


@router.get("/v1/jit/knowledge-ledger/prompt-snapshot", status_code=410, deprecated=True)
def retired_ledger_prompt_snapshot(
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.get("/v1/jit/knowledge-ledger/mirror-snapshot", status_code=410, deprecated=True)
def retired_ledger_mirror_snapshot(
    request: Request,
    cursor: str | None = None,
    page_size: int = Query(50),
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.get("/v1/jit/rollout-decision", status_code=410, deprecated=True)
def retired_jit_rollout_decision(
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.get("/v1/jit/trigger-snapshot", status_code=410, deprecated=True)
def retired_jit_trigger_snapshot(
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.post(
    "/v1/jit/trigger-feedback",
    status_code=410,
    deprecated=True,
    openapi_extra=_RETIRED_JSON_BODY,
)
def retired_jit_trigger_feedback(
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.post(
    "/v1/jit/proactivity/reservations",
    status_code=410,
    deprecated=True,
    openapi_extra=_RETIRED_JSON_BODY,
)
def retired_jit_proactivity_reservation(
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.post(
    "/v3/memories/{memory_id}/use",
    status_code=410,
    deprecated=True,
    openapi_extra=_RETIRED_JSON_BODY,
)
def retired_memory_use(
    memory_id: str,
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


@router.get("/v1/frame-requests/temporary/{request_id}/image", status_code=410, deprecated=True)
def retired_temporary_frame_image(
    request_id: str,
    request: Request,
    account_generation: int | None = None,
    uid: str = Depends(get_current_user_uid),
) -> JSONResponse:
    return _retired_response()


__all__ = ["router"]
