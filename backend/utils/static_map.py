"""Static map preview images — the single provider seam for app map previews.

Every in-app map preview is rendered through ``GET /v1/static-map``
(``routers/static_map.py``): the server holds the only Maps key, builds the
provider URL here, and caches rendered bytes in Redis keyed by the quantized
pin set and size, so repeat renders of the same place (the home recap carousel
re-renders often) cost one upstream call per distinct pin set. Swapping the
provider means changing this module only.

Coordinates are never logged — only counts and outcomes (see
``utils/conversations/location.py`` for the same rule).
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import List, Optional, Tuple

from database.redis_db import r
from utils.executors import db_executor, run_blocking
from utils.http_client import get_maps_client, get_maps_semaphore

logger = logging.getLogger(__name__)

# Google Static Maps accepts at most 640px per axis (1280 with scale=2).
_MAX_AXIS_PX = 640
# Quantize pins to ~11m so users recording at the same place share one cached
# image; the offset is invisible at the zooms these previews render at.
_PIN_PRECISION = 4
_MAX_PINS = 50
# Rendered images are immutable for a given URL shape; version the cache key so
# a style bump invalidates old entries without a flush.
_CACHE_VERSION = 1
_CACHE_TTL_SECONDS = 604800  # 7 days
# Stampede dedup: per-key render lock TTL (bounds how long a crashed holder can
# wedge waiters), how often waiters poll the cache, and how long they wait
# before rendering unlocked.
_RENDER_LOCK_TTL_SECONDS = 30
_RENDER_POLL_INTERVAL_SECONDS = 0.25
_RENDER_WAIT_TIMEOUT_SECONDS = 15.0

# Dark styling shared by every preview. Mirrors the look the app shipped with
# client-side Google Static Maps (conversation detail geolocation card).
_DARK_STYLES = [
    'style=element:geometry%7Ccolor:0x1a1a1a',
    'style=element:labels.icon%7Cvisibility:off',
    'style=element:labels.text.fill%7Ccolor:0x4a4a4a',
    'style=element:labels.text.stroke%7Ccolor:0x1a1a1a',
    'style=feature:administrative%7Celement:geometry%7Cvisibility:off',
    'style=feature:administrative%7Celement:labels%7Cvisibility:off',
    'style=feature:administrative.locality%7Celement:labels.text.fill%7Ccolor:0x8a8a8a',
    'style=feature:administrative.neighborhood%7Cvisibility:off',
    'style=feature:administrative.land_parcel%7Cvisibility:off',
    'style=feature:poi%7Celement:labels%7Cvisibility:off',
    'style=feature:poi.business%7Cvisibility:off',
    'style=feature:poi.government%7Cvisibility:off',
    'style=feature:poi.medical%7Cvisibility:off',
    'style=feature:poi.place_of_worship%7Cvisibility:off',
    'style=feature:poi.school%7Cvisibility:off',
    'style=feature:poi.sports_complex%7Cvisibility:off',
    'style=feature:poi.park%7Celement:geometry%7Ccolor:0x263c3f',
    'style=feature:poi.park%7Celement:labels.text%7Cvisibility:simplified',
    'style=feature:poi.park%7Celement:labels.text.fill%7Ccolor:0x5a7a5f',
    'style=feature:road%7Celement:geometry%7Ccolor:0x2c2c2c',
    'style=feature:road%7Celement:labels%7Cvisibility:simplified',
    'style=feature:road%7Celement:labels.text.fill%7Ccolor:0x6a6a6a',
    'style=feature:road.arterial%7Celement:geometry%7Ccolor:0x373737',
    'style=feature:road.arterial%7Celement:labels%7Cvisibility:off',
    'style=feature:road.highway%7Celement:geometry%7Ccolor:0x444444',
    'style=feature:road.highway%7Celement:labels.text.fill%7Ccolor:0x8a8a8a',
    'style=feature:road.highway.controlled_access%7Celement:geometry%7Ccolor:0x555555',
    'style=feature:road.local%7Celement:labels%7Cvisibility:off',
    'style=feature:transit%7Celement:labels%7Cvisibility:off',
    'style=feature:water%7Celement:geometry%7Ccolor:0x0e1626',
    'style=feature:water%7Celement:labels.text.fill%7Ccolor:0x3d5a5d',
    'style=feature:water%7Celement:labels%7Cvisibility:simplified',
]


class MalformedPinsError(ValueError):
    """Client sent a pins parameter that cannot be parsed into bounded coordinates."""


def parse_pins(pins: str) -> List[Tuple[float, float]]:
    """Parse ``lat,lng|lat,lng|...`` into bounded, de-duplicated, sorted pins.

    De-duplication and sorting happen on the quantized values so the same place
    always maps to the same cache entry regardless of pin order or repeats.
    """
    if not pins:
        raise MalformedPinsError('pins must be a non-empty pipe-separated list of lat,lng pairs')
    parsed: List[Tuple[float, float]] = []
    seen: set[Tuple[float, float]] = set()
    for chunk in pins.split('|'):
        parts = chunk.split(',')
        if len(parts) != 2:
            raise MalformedPinsError('each pin must be lat,lng')
        try:
            latitude = round(float(parts[0].strip()), _PIN_PRECISION)
            longitude = round(float(parts[1].strip()), _PIN_PRECISION)
        except (ValueError, TypeError):
            raise MalformedPinsError('each pin must be numeric lat,lng')
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise MalformedPinsError('pin coordinates out of bounds')
        if (latitude, longitude) in seen:
            continue
        seen.add((latitude, longitude))
        parsed.append((latitude, longitude))
        if len(parsed) >= _MAX_PINS:
            break
    if not parsed:
        raise MalformedPinsError('pins must contain at least one coordinate pair')
    parsed.sort()
    return parsed


def build_static_map_url(pins: List[Tuple[float, float]], width: int, height: int, api_key: str) -> str:
    """Build the provider URL for the quantized pin set and size.

    One pin renders centered at street zoom; several pins use the provider's
    ``visible=`` auto-fit so every stop lands inside the frame.

    Callers pass already-normalized dimensions (see ``_effective_dimensions``);
    the provider serves at most 640px per axis (1280 with ``scale=2``).

    Provider URL budget: the Maps Static API restricts URLs to 16,384
    characters (https://developers.google.com/maps/documentation/maps-static/
    start). The old 2,048 figure is the legacy v2 limit and now belongs to the
    separate Maps URLs service — do not guard against it. Measured worst case
    with the full style list is ~4KB at the 50-pin cap (the pin list appears
    twice, in ``markers`` and ``visible``), comfortably inside the limit;
    re-measure if the style list, pin cap, or provider changes.
    """
    size = f'size={width}x{height}'
    scale = 'scale=2'
    locations = '%7C'.join(f'{latitude:.4f},{longitude:.4f}' for latitude, longitude in pins)
    # White markers match the app's pin styling (and the brand's no-purple rule).
    markers = f'markers=color:0xFFFFFF%7C{locations}'
    framing = f'center={locations}&zoom=15' if len(pins) == 1 else f'visible={locations}'
    styles = '&'.join(_DARK_STYLES)
    return (
        f'https://maps.googleapis.com/maps/api/staticmap?{framing}&{size}&{scale}'
        f'&format=png&{markers}&{styles}&key={api_key}'
    )


def _effective_dimensions(width: int, height: int) -> Tuple[int, int]:
    """Normalize oversized requests with one proportional scale factor.

    Scaling both axes by ``min(1, 640/width, 640/height)`` (instead of
    independent per-axis clamps) preserves the aspect ratio AND makes every
    request that differs only by scale share one cache entry — the provider
    serves at most 640px per axis (1280 with ``scale=2``).
    """
    factor = min(1.0, _MAX_AXIS_PX / width, _MAX_AXIS_PX / height)
    return int(width * factor), int(height * factor)


def _cache_key(pins: List[Tuple[float, float]], width: int, height: int) -> str:
    # Sorting makes the key order-insensitive even if a caller passes unsorted pins.
    payload = json.dumps({'v': _CACHE_VERSION, 'pins': sorted(pins), 'w': width, 'h': height}, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f'staticmap:{digest}'


async def _read_cache(key: str) -> Optional[bytes]:
    try:
        cached = await run_blocking(db_executor, r.get, key)
        if cached:
            return cached if isinstance(cached, bytes) else bytes(cached)
    except Exception as error:
        logger.warning('static map cache read failed error_type=%s', type(error).__name__)
    return None


async def _write_cache(key: str, image: bytes) -> None:
    try:
        await run_blocking(db_executor, r.set, key, image, ex=_CACHE_TTL_SECONDS)
    except Exception as error:
        logger.warning('static map cache write failed error_type=%s', type(error).__name__)


async def _render_from_provider(pins: List[Tuple[float, float]], width: int, height: int) -> Optional[bytes]:
    """Fetch a fresh render from the provider. Failures return ``None`` and are never cached."""
    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not api_key:
        logger.error('static map render unavailable: GOOGLE_MAPS_API_KEY is not set')
        return None

    url = build_static_map_url(pins, width, height, api_key)
    try:
        async with get_maps_semaphore():
            response = await get_maps_client().get(url)
    except Exception as error:
        logger.error('static map render failed error_type=%s pin_count=%d', type(error).__name__, len(pins))
        return None
    content_type = response.headers.get('content-type', '')
    if response.status_code != 200 or not content_type.startswith('image/'):
        logger.error(
            'static map render rejected status=%d content_type=%s pin_count=%d',
            response.status_code,
            content_type.split(';')[0],
            len(pins),
        )
        return None
    return response.content


async def fetch_static_map(pins: List[Tuple[float, float]], width: int, height: int) -> Optional[bytes]:
    """Return cached rendered bytes, fetching from the provider on a miss.

    Returns ``None`` on any upstream failure — callers surface an error and the
    app falls back to its offline canvas; a failure is never cached.

    Stampede dedup: a cache miss takes a short-lived per-key render lock
    (``r.set(nx=True)``). The lock holder renders once; concurrent misses poll
    the cache for the holder's result and, if the wait budget expires, render
    without the lock — a lost lock must never turn into a 502, so every lock
    error path fails open to a plain fetch.
    """
    width, height = _effective_dimensions(width, height)
    key = _cache_key(pins, width, height)

    cached = await _read_cache(key)
    if cached:
        return cached

    lock_key = f'{key}:render-lock'
    lock_acquired = False
    # 'acquired' -> we render; 'held' -> wait for the holder; 'unavailable' ->
    # the lock infrastructure itself is broken, so fail open immediately:
    # polling a broken cache for 15s would only add latency to every request.
    lock_state = 'unavailable'
    try:
        try:
            acquired = await run_blocking(db_executor, r.set, lock_key, '1', ex=_RENDER_LOCK_TTL_SECONDS, nx=True)
            lock_state = 'acquired' if acquired else 'held'
        except Exception as error:
            # Fail open: lock errors degrade to unprotected rendering.
            logger.warning('static map render-lock acquire failed error_type=%s', type(error).__name__)

        if lock_state == 'acquired':
            lock_acquired = True
            # Recheck: the previous holder may have finished between our miss
            # and acquiring the lock.
            cached = await _read_cache(key)
            if cached:
                return cached
            image = await _render_from_provider(pins, width, height)
            if image is not None:
                await _write_cache(key, image)
            return image

        if lock_state != 'held':
            # Lock unavailable (Redis broken): render immediately, no wait —
            # the cache write is best-effort like every other Redis touch.
            image = await _render_from_provider(pins, width, height)
            if image is not None:
                await _write_cache(key, image)
            return image

        # Someone else holds the render lock: wait for their result instead of
        # stacking a duplicate provider call.
        deadline = time.monotonic() + _RENDER_WAIT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(_RENDER_POLL_INTERVAL_SECONDS)
            cached = await _read_cache(key)
            if cached:
                return cached
        # Wait budget exhausted (holder crashed or is wedged): fail open and
        # render without holding the lock.
        logger.warning('static map render-lock wait timed out; rendering unlocked')
        image = await _render_from_provider(pins, width, height)
        if image is not None:
            await _write_cache(key, image)
        return image
    finally:
        if lock_acquired:
            try:
                await run_blocking(db_executor, r.delete, lock_key)
            except Exception as error:
                # The lock has a TTL; failing to release only risks one
                # duplicate render after this holder is done.
                logger.warning('static map render-lock release failed error_type=%s', type(error).__name__)
