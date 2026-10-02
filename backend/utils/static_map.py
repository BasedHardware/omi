"""Static map preview images — the single provider seam for app map previews.

Every in-app map preview is rendered through ``GET /v1/static-map``
(``routers/static_map.py``): the server holds the only Maps key, builds the
provider URL here, and caches rendered bytes in Redis keyed by the quantized
pin set, size and theme, so repeat renders of the same place (the home recap carousel
re-renders often) cost one upstream call per distinct pin set. Swapping the
provider means changing this module only.

Coordinates are never logged — only counts and outcomes (see
``utils/conversations/location.py`` for the same rule).
"""

import asyncio
import hashlib
import io
import json
import logging
import math
import os
import time
from functools import lru_cache
from typing import List, Literal, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from database.redis_db import r
from utils.executors import db_executor, run_blocking, storage_executor
from utils.http_client import get_maps_client, get_maps_semaphore

logger = logging.getLogger(__name__)

# Google Static Maps accepts at most 640px per axis (1280 with scale=2).
_MAX_AXIS_PX = 640
# Quantize pins to ~11m so users recording at the same place share one cached
# image; the offset is invisible at the zooms these previews render at.
_PIN_PRECISION = 4
_MAX_PINS = 50
# Rendered images are immutable for a given URL shape; version the cache key so
# a style bump — or a one-off invalidation — drops old entries without a flush.
# Bumped 1->2 to evict provider "degraded render" watermarks (served as HTTP 200
# image/png under launch-load authorization degradation) that were cached and
# shared to every user for the full TTL before the reject below existed.
# Bumped 2->3 for the black-and-white light/dark restyle (theme is now part of the key).
# Bumped 3->4: the pin is drawn here (a dot), not by the provider.
_CACHE_VERSION = 4
_CACHE_TTL_SECONDS = 604800  # 7 days
# Stampede dedup: per-key render lock TTL (bounds how long a crashed holder can
# wedge waiters), how often waiters poll the cache, and how long they wait
# before rendering unlocked.
_RENDER_LOCK_TTL_SECONDS = 30
_RENDER_POLL_INTERVAL_SECONDS = 0.25
_RENDER_WAIT_TIMEOUT_SECONDS = 15.0

MapTheme = Literal['light', 'dark']

# Black and white in both themes, like Uber's map: grey land, white (or dark grey)
# streets with a slightly darker edge, grey water and parks, street and area
# names kept, POIs, icons and transit off, so the pin carries the image. Old app
# builds send no theme and get dark, the only look they ever rendered.
_DARK_STYLES = [
    'style=element:geometry%7Ccolor:0x161616',
    'style=element:labels.icon%7Cvisibility:off',
    'style=element:labels.text.fill%7Ccolor:0x7c7c7c',
    'style=element:labels.text.stroke%7Ccolor:0x161616',
    'style=feature:administrative%7Celement:geometry%7Cvisibility:off',
    'style=feature:administrative.land_parcel%7Cvisibility:off',
    'style=feature:administrative.neighborhood%7Celement:labels.text.fill%7Ccolor:0x8c8c8c',
    'style=feature:landscape.man_made%7Celement:geometry%7Ccolor:0x1b1b1b',
    'style=feature:poi%7Cvisibility:off',
    'style=feature:poi.park%7Cvisibility:on',
    'style=feature:poi.park%7Celement:geometry%7Ccolor:0x1d1d1d',
    'style=feature:poi.park%7Celement:labels%7Cvisibility:off',
    'style=feature:road%7Celement:geometry.fill%7Ccolor:0x2a2a2a',
    'style=feature:road%7Celement:geometry.stroke%7Ccolor:0x1f1f1f',
    'style=feature:road.highway%7Celement:geometry.fill%7Ccolor:0x3b3b3b',
    'style=feature:road.highway%7Celement:geometry.stroke%7Ccolor:0x2c2c2c',
    'style=feature:road.local%7Celement:labels%7Cvisibility:off',
    'style=feature:transit%7Cvisibility:off',
    'style=feature:water%7Celement:geometry%7Ccolor:0x0a0a0a',
    'style=feature:water%7Celement:labels%7Cvisibility:off',
]

_LIGHT_STYLES = [
    'style=element:geometry%7Ccolor:0xeaeaea',
    'style=element:labels.icon%7Cvisibility:off',
    'style=element:labels.text.fill%7Ccolor:0x767676',
    'style=element:labels.text.stroke%7Ccolor:0xffffff',
    'style=feature:administrative%7Celement:geometry%7Cvisibility:off',
    'style=feature:administrative.land_parcel%7Cvisibility:off',
    'style=feature:administrative.neighborhood%7Celement:labels.text.fill%7Ccolor:0x6e6e6e',
    'style=feature:landscape.man_made%7Celement:geometry%7Ccolor:0xe4e4e4',
    'style=feature:poi%7Cvisibility:off',
    'style=feature:poi.park%7Cvisibility:on',
    'style=feature:poi.park%7Celement:geometry%7Ccolor:0xe0e0e0',
    'style=feature:poi.park%7Celement:labels%7Cvisibility:off',
    'style=feature:road%7Celement:geometry.fill%7Ccolor:0xffffff',
    'style=feature:road%7Celement:geometry.stroke%7Ccolor:0xdcdcdc',
    # Highways keep the white road fill, as on Uber's light map; their darker edge sets them apart.
    'style=feature:road.highway%7Celement:geometry.stroke%7Ccolor:0xc9c9c9',
    'style=feature:road.local%7Celement:labels%7Cvisibility:off',
    'style=feature:transit%7Cvisibility:off',
    'style=feature:water%7Celement:geometry%7Ccolor:0xcfcfcf',
    'style=feature:water%7Celement:labels%7Cvisibility:off',
]

_STYLES = {'dark': _DARK_STYLES, 'light': _LIGHT_STYLES}

# The provider draws no marker. Each pin is the app's dot, drawn onto the render
# where it lands: a disc in the theme's ink (white on dark, black on light, never
# purple, the brand rule) ringed in the opposite colour, a small centre dot, and a
# soft shadow. Every app build gets the same pin. Sizes are logical pixels.
_SCALE = 2
_TILE_PX = 256
_STREET_ZOOM = 15
# Room kept between the outermost pins and the frame, so their dots stay whole.
_FIT_MARGIN_PX = 24
_PIN_RADIUS = 9.0
_PIN_RING = 3.4  # centred on the disc's edge
_PIN_CENTER = 2.7
_PIN_INK = {'dark': ((255, 255, 255), (0, 0, 0)), 'light': ((0, 0, 0), (255, 255, 255))}
# Web Mercator ends at about ±85.0511° (sin = tanh(pi)), where the provider's tiles stop.
_MAX_SIN_LATITUDE = math.tanh(math.pi)


class MalformedPinsError(ValueError):
    """Client sent a pins parameter that cannot be parsed into bounded coordinates."""


class PinsDoNotFitError(ValueError):
    """The pins spread wider than the render holds, even at the provider's widest zoom."""


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
            raw_lat = float(parts[0].strip())
            raw_lng = float(parts[1].strip())
        except (ValueError, TypeError):
            raise MalformedPinsError('each pin must be numeric lat,lng')
        if not -90 <= raw_lat <= 90 or not -180 <= raw_lng <= 180:
            raise MalformedPinsError('pin coordinates out of bounds')
        latitude = round(raw_lat, _PIN_PRECISION)
        longitude = round(raw_lng, _PIN_PRECISION)
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


def _world(latitude: float, longitude: float) -> Tuple[float, float]:
    """Web Mercator position as a fraction of the world, 0..1 on each axis. A latitude past
    the projection's edge lands on it, as on the provider's tiles."""
    sin_lat = min(max(math.sin(math.radians(latitude)), -_MAX_SIN_LATITUDE), _MAX_SIN_LATITUDE)
    return (longitude + 180) / 360, 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)


def _wrapped(dx: float) -> float:
    """A world-x offset taken the short way round the antimeridian, in [-0.5, 0.5)."""
    return (dx + 0.5) % 1 - 0.5


def _from_world(x: float, y: float) -> Tuple[float, float]:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y)))), x * 360 - 180


def frame_pins(pins: List[Tuple[float, float]], width: int, height: int) -> Tuple[Tuple[float, float], int]:
    """The render's centre and zoom: one pin centred at street zoom; several, the
    closest zoom (at most street zoom) that keeps every pin a margin inside the
    frame. Framed here rather than by the provider so the pins can be drawn where
    they land. Raises ``PinsDoNotFitError`` when they don't fit even at zoom 0."""
    if len(pins) == 1:
        return pins[0], _STREET_ZOOM
    xs, ys = zip(*(_world(*pin) for pin in pins))
    # The pins cover the world minus its widest empty stretch of longitude, so pins either side
    # of the antimeridian frame as neighbours. On a tie the stretch across it wins: the usual frame.
    order = sorted(xs)
    gaps = [east - west for west, east in zip(order, order[1:])] + [order[0] + 1 - order[-1]]
    widest = max(range(len(gaps)), key=lambda i: (gaps[i], i == len(gaps) - 1))
    span_x, span_y = 1 - gaps[widest], max(ys) - min(ys)
    center_x = (order[(widest + 1) % len(order)] + span_x / 2) % 1
    room_x, room_y = max(width - 2 * _FIT_MARGIN_PX, 1), max(height - 2 * _FIT_MARGIN_PX, 1)

    def fits(zoom: int) -> bool:
        return span_x * _TILE_PX * 2**zoom <= room_x and span_y * _TILE_PX * 2**zoom <= room_y

    zoom = _STREET_ZOOM
    while zoom > 0 and not fits(zoom):
        zoom -= 1
    if not fits(zoom):
        raise PinsDoNotFitError(f'{len(pins)} pins do not fit a {width}x{height} render')
    return _from_world(center_x, (min(ys) + max(ys)) / 2), zoom


def pin_pixels(
    pins: List[Tuple[float, float]], center: Tuple[float, float], zoom: int, width: int, height: int
) -> List[Tuple[float, float]]:
    """Where each pin lands in the render, in its ``scale=2`` pixels."""
    center_x, center_y = _world(*center)
    world_px = _TILE_PX * 2**zoom * _SCALE
    points: List[Tuple[float, float]] = []
    for pin in pins:
        x, y = _world(*pin)
        points.append(
            (width * _SCALE / 2 + _wrapped(x - center_x) * world_px, height * _SCALE / 2 + (y - center_y) * world_px)
        )
    return points


@lru_cache(maxsize=2)
def _pin_sprite(theme: MapTheme) -> Image.Image:
    """One pin with its shadow, drawn at 4x and box-averaged down: smooth edges, no halo."""
    supersample = 4
    k = _SCALE * supersample
    outer = (_PIN_RADIUS + _PIN_RING / 2) * k
    half = supersample * math.ceil((outer + 6 * k) / supersample)  # room for the shadow's drop and blur
    ink, ring = _PIN_INK[theme]

    def disc(radius: float, drop: float = 0) -> List[float]:
        return [half - radius, half - radius + drop, half + radius, half + radius + drop]

    sprite = Image.new('RGBA', (2 * half, 2 * half), (0, 0, 0, 0))
    ImageDraw.Draw(sprite).ellipse(disc(outer, 1.5 * k), fill=(0, 0, 0, 71))
    sprite = sprite.filter(ImageFilter.GaussianBlur(1.6 * k))
    draw = ImageDraw.Draw(sprite)
    draw.ellipse(disc(outer), fill=ring)
    draw.ellipse(disc((_PIN_RADIUS - _PIN_RING / 2) * k), fill=ink)
    draw.ellipse(disc(_PIN_CENTER * k), fill=ring)
    return sprite.resize((2 * half // supersample, 2 * half // supersample), Image.Resampling.BOX)


def draw_pins(image: bytes, pins: List[Tuple[float, float]], width: int, height: int, theme: MapTheme) -> bytes:
    """Draw each pin's dot onto a provider render (PNG in, PNG out)."""
    with Image.open(io.BytesIO(image)) as render:
        canvas = render.convert('RGB')
    expected = (width * _SCALE, height * _SCALE)
    if canvas.size != expected:
        # Pins are placed in the frame's scale=2 pixels; on any other size they would land in the wrong place.
        raise ValueError(f'render is {canvas.width}x{canvas.height}, expected {expected[0]}x{expected[1]}')
    sprite = _pin_sprite(theme)
    offset = sprite.width // 2
    center, zoom = frame_pins(pins, width, height)
    for x, y in pin_pixels(pins, center, zoom, width, height):
        canvas.paste(sprite, (round(x) - offset, round(y) - offset), sprite)
    out = io.BytesIO()
    # The provider sends an 8-bit palette PNG and the pins add only a few greys, so the result
    # usually still fits 256 colours. Keep it 8-bit then: lossless, and about 40% smaller.
    if canvas.getcolors(256) is not None:
        canvas.quantize(256).save(out, format='PNG')
    else:
        canvas.save(out, format='PNG')
    return out.getvalue()


def build_static_map_url(
    pins: List[Tuple[float, float]], width: int, height: int, api_key: str, theme: MapTheme = 'dark'
) -> str:
    """Build the provider URL for the quantized pin set, size and theme.

    The frame comes from ``frame_pins`` (one pin centred at street zoom; several
    fitted inside the frame), and the provider draws no marker: ``draw_pins``
    adds the dots after the render.

    Callers pass already-normalized dimensions (see ``_effective_dimensions``);
    the provider serves at most 640px per axis (1280 with ``scale=2``).

    Provider URL budget: the Maps Static API restricts URLs to 16,384
    characters (https://developers.google.com/maps/documentation/maps-static/
    start). The old 2,048 figure is the legacy v2 limit and now belongs to the
    separate Maps URLs service — do not guard against it. Measured worst case
    with either theme's style list is about 1.2KB whatever the pin count, since the
    pins no longer appear in the URL; re-measure if the style list or provider
    changes.
    """
    (latitude, longitude), zoom = frame_pins(pins, width, height)
    styles = '&'.join(_STYLES[theme])
    return (
        f'https://maps.googleapis.com/maps/api/staticmap?center={latitude:.6f},{longitude:.6f}&zoom={zoom}'
        f'&size={width}x{height}&scale={_SCALE}&format=png&{styles}&key={api_key}'
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


def _cache_key(pins: List[Tuple[float, float]], width: int, height: int, theme: MapTheme = 'dark') -> str:
    # Sorting makes the key order-insensitive even if a caller passes unsorted pins.
    payload = json.dumps(
        {'v': _CACHE_VERSION, 'pins': sorted(pins), 'w': width, 'h': height, 'theme': theme}, sort_keys=True
    )
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


async def _render_from_provider(
    pins: List[Tuple[float, float]], width: int, height: int, theme: MapTheme
) -> Optional[bytes]:
    """Fetch a fresh render from the provider. Failures return ``None`` and are never cached."""
    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not api_key:
        logger.error('static map render unavailable: GOOGLE_MAPS_API_KEY is not set')
        return None

    try:
        url = build_static_map_url(pins, width, height, api_key, theme)
    except PinsDoNotFitError:
        # Too spread out for this size even at the widest zoom; the app's canvas shows every pin instead.
        logger.warning('static map pins do not fit pin_count=%d size=%dx%d', len(pins), width, height)
        return None
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
    # Google serves degraded/error renders (e.g. the authorization "key
    # required" / "for development purposes only" watermark that surfaced under
    # launch-load) as a normal HTTP 200 image/png, flagged only by this header.
    # A valid styled render never sets it, so treat its presence as a failure
    # and never cache it — otherwise one poisoned render is served to every user
    # for the whole cache TTL (the incident this reject fixes).
    warning = response.headers.get('X-Staticmap-API-Warning')
    if warning:
        logger.error(
            'static map render degraded (provider warning); not caching pin_count=%d warning=%s',
            len(pins),
            warning[:120],
        )
        return None
    try:
        # Off the event loop on storage_executor, next to the provider bytes it works on. No pool is
        # dedicated to image work, and this is short: about 10 ms for a card and 50 ms at the largest
        # size, once per distinct pin set (the render lock and the cache absorb repeats).
        return await run_blocking(storage_executor, draw_pins, response.content, pins, width, height, theme)
    except Exception as error:
        # A render without its pins would mislead; fail like any other bad render.
        logger.error('static map pin drawing failed error_type=%s pin_count=%d', type(error).__name__, len(pins))
        return None


async def fetch_static_map(
    pins: List[Tuple[float, float]], width: int, height: int, theme: MapTheme = 'dark'
) -> Optional[bytes]:
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
    key = _cache_key(pins, width, height, theme)

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
            image = await _render_from_provider(pins, width, height, theme)
            if image is not None:
                await _write_cache(key, image)
            return image

        if lock_state != 'held':
            # Lock unavailable (Redis broken): render immediately, no wait —
            # the cache write is best-effort like every other Redis touch.
            image = await _render_from_provider(pins, width, height, theme)
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
        image = await _render_from_provider(pins, width, height, theme)
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
