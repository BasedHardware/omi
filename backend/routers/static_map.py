"""Static map preview proxy — ``GET /v1/static-map``.

The app funnels every map preview through this route so the only Maps key stays
server-side and rendered images are shared across users via Redis
(see ``utils/static_map.py``). Auth keeps the route from becoming an open
image proxy on the project's key.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.static_map import MalformedPinsError, fetch_static_map, parse_pins

logger = logging.getLogger(__name__)

router = APIRouter()


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
        raise HTTPException(status_code=400, detail=str(error))

    image = await fetch_static_map(parsed, width, height)
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
