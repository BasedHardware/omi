"""Per-user prefs endpoints for the LLM gateway.

Service-authed. The calling service (``backend`` / ``pusher``) forwards
the Firebase-validated uid via ``X-Omi-User-Uid`` and the gateway
attributes the prefs to that uid. The gateway never trusts the uid
directly — it relies on the service token to prove the caller is
authorized to speak for that uid.

Endpoints:
    GET  /v1/auto-router/prefs   — fetch the caller's prefs (uid from auth)
    PUT  /v1/auto-router/prefs   — replace the caller's prefs
    DELETE /v1/auto-router/prefs — clear the caller's prefs
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.user_prefs import UserPrefs
from llm_gateway.gateway.user_prefs_store import (
    UserPrefsStoreError,
    get_user_prefs_store,
)

router = APIRouter()


def _require_user_uid(caller: ServiceAuthDependency) -> str:
    """Extract the per-user uid from the authenticated service caller.

    The gateway is service-only; without a uid in the auth headers the
    prefs endpoints cannot scope a read or write. Returning 422 (not
    403) because the caller is authenticated but the request is
    missing a required field.
    """
    if caller.user_uid is None:
        raise HTTPException(
            status_code=422,
            detail='prefs endpoints require X-Omi-User-Uid forwarded by the caller',
        )
    return caller.user_uid


def _iso8601_utc(epoch_seconds: float) -> str | None:
    if epoch_seconds <= 0.0:
        return None
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat().replace('+00:00', 'Z')


@router.get('/v1/auto-router/prefs')
async def get_prefs(caller: ServiceAuthDependency = ...) -> dict[str, Any]:
    """Return the caller's per-lane weight overrides.

    Empty prefs (the default) means no overrides; the picker uses lane
    defaults. Response shape::

        {
            "uid": "<uid>",
            "prefs": {"<lane_id>": {"quality": ..., "latency": ..., "cost": ...}, ...},
            "updated_at": "2026-07-01T12:00:00Z"   // ISO 8601, null if never set
        }
    """
    uid = _require_user_uid(caller)
    try:
        entry = get_user_prefs_store().get(uid)
    except UserPrefsStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail=f'prefs backend unavailable: {type(exc).__name__}',
        ) from exc
    return {
        'uid': uid,
        'prefs': entry.prefs.to_dict(),
        'updated_at': _iso8601_utc(entry.updated_at),
    }


@router.put('/v1/auto-router/prefs')
async def put_prefs(
    body: dict[str, Any],
    caller: ServiceAuthDependency = ...,
) -> dict[str, Any]:
    """Replace the caller's per-lane weight overrides.

    Request body shape::

        {"prefs": {"<lane_id>": {"quality": ..., "latency": ..., "cost": ...}, ...}}

    Empty ``prefs: {}`` clears all overrides (stored prefs become
    empty; the picker uses lane defaults).

    Returns 200 with the updated prefs and ``updated_at``.
    Returns 400 if any lane's weights are invalid.
    Returns 422 if the caller did not forward ``X-Omi-User-Uid``.
    Returns 503 if the prefs backend is unavailable.
    """
    uid = _require_user_uid(caller)

    if 'prefs' not in body:
        raise HTTPException(
            status_code=400,
            detail={'code': 'missing_prefs', 'message': "request body must include 'prefs' key"},
        )

    raw_prefs = body['prefs']
    if raw_prefs is None:
        raw_prefs = {}
    if not isinstance(raw_prefs, dict):
        raise HTTPException(
            status_code=400,
            detail={
                'code': 'invalid_prefs_type',
                'message': f"'prefs' must be a dict, got {type(raw_prefs).__name__}",
            },
        )

    try:
        prefs = UserPrefs.from_dict(raw_prefs)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail={'code': 'invalid_prefs', 'message': str(exc)},
        ) from exc

    try:
        entry = get_user_prefs_store().set(uid, prefs)
    except UserPrefsStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail=f'prefs backend unavailable: {type(exc).__name__}',
        ) from exc
    return {
        'uid': uid,
        'prefs': entry.prefs.to_dict(),
        'updated_at': _iso8601_utc(entry.updated_at) or '',
    }


@router.delete('/v1/auto-router/prefs')
async def delete_prefs(caller: ServiceAuthDependency = ...) -> dict[str, Any]:
    """Clear the caller's prefs. Idempotent — returns 200 even if no prefs exist."""
    uid = _require_user_uid(caller)
    try:
        get_user_prefs_store().clear(uid)
    except UserPrefsStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail=f'prefs backend unavailable: {type(exc).__name__}',
        ) from exc
    return {'uid': uid, 'prefs': {}, 'updated_at': None}


__all__ = ['router']
