"""Static map preview proxy — ``GET /v1/static-map``.

The app funnels every map preview through this route so the only Maps key stays
server-side and rendered images are shared across users via Redis
(see ``utils/static_map.py``). Auth keeps the route from becoming an open
image proxy on the project's key.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.static_map import MalformedPinsError, fetch_static_map, parse_pins

logger = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_static_map_error(exc: Exception, fallback: str) -> str:
    """Sanitize static map exception details while preserving debug logging."""
    logger.warning("Static map operation failed: %s: %s", type(exc).__name__, exc)
    return fallback


@router.get('/v1/static-map')
async def get_static_map(
    pins: str = Query(..., description="Pipe-separated 'lat,lng' pairs (max 50 after de-duplication)"),
    width: int = Query(..., ge=64, le=1280, description='Requested image width in px'),
    height: int = Query(..., ge=64, le=1280, description='Requested image height in px'),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'static_map:get')),
):
    try:
        parsed = parse_pins(pins)
    except MalformedPinsError as error:
        detail = _sanitize_static_map_error(error, "Invalid static map pin coordinates")
        raise HTTPException(status_code=400, detail=detail) from error
    except ValueError as error:
        detail = _sanitize_static_map_error(error, "Invalid static map parameters")
        raise HTTPException(status_code=400, detail=detail) from error

    try:
        image = await fetch_static_map(parsed, width, height)
    except Exception as error:
        logger.warning("Static map provider fetch failed: %s: %s", type(error).__name__, error)
        record_fallback(
            component='static_map',
            from_mode='provider_static_map',
            to_mode='client_pin_canvas',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        raise HTTPException(status_code=502, detail='Static map is temporarily unavailable') from error

    if image is None:
        # The app renders its offline pin-dot canvas for any failure here —
        # count the degrade through the shared fallback telemetry.
        record_fallback(
            component='static_map',
            from_mode='provider_static_map',
            to_mode='client_pin_canvas',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        raise HTTPException(status_code=502, detail='Static map is temporarily unavailable')

    return Response(content=image, media_type='image/png', headers={'Cache-Control': 'private, max-age=86400'})


__all__ = [
    "_sanitize_static_map_error",
    "get_static_map",
    "router",
]
