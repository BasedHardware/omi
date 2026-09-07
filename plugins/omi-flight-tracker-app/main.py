"""
Omi OpenSky Live Flight Tracker & Aviation Radar Integration App.

Provides real-time ADS-B transponder flight tracking, overhead aircraft identification,
and regional airspace monitoring for Omi AI wearables.
"""

import copy
import ipaddress
import math
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from .models import (
        AirspaceActivityRequest,
        ChatToolResponse,
        FlightsOverheadRequest,
        TrackFlightRequest,
    )
except ImportError:
    from models import (
        AirspaceActivityRequest,
        ChatToolResponse,
        FlightsOverheadRequest,
        TrackFlightRequest,
    )

# --- Configuration & Constants ---
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
REQUEST_TIMEOUT = 12.0
OPENSKY_CACHE_TTL = 15.0  # OpenSky updates every 10-15 seconds for anonymous users
MAX_CACHE_ENTRIES = 500
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60.0

# Pre-indexed coordinates for major global aviation hubs and cities
KNOWN_METRO_COORDINATES: Dict[str, Tuple[float, float]] = {
    "london": (51.5074, -0.1278),
    "new york": (40.7128, -74.0060),
    "nyc": (40.7128, -74.0060),
    "paris": (48.8566, 2.3522),
    "tokyo": (35.6762, 139.6503),
    "frankfurt": (50.1109, 8.6821),
    "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298),
    "san francisco": (37.7749, -122.4194),
    "atlanta": (33.7490, -84.3880),
    "dubai": (25.2048, 55.2708),
    "singapore": (1.3521, 103.8198),
    "sydney": (-33.8688, 151.2093),
    "berlin": (52.5200, 13.4050),
    "amsterdam": (52.3676, 4.9041),
    "toronto": (43.6532, -79.3832),
    "madrid": (40.4168, -3.7038),
    "rome": (41.9028, 12.4964),
    "mumbai": (19.0760, 72.8777),
    "delhi": (28.6139, 77.2090),
    "hong kong": (22.3193, 114.1694),
    "seoul": (37.5665, 126.9780),
    "dallas": (32.7767, -96.7970),
    "miami": (25.7617, -80.1918),
    "seattle": (47.6062, -122.3321),
    "boston": (42.3601, -71.0589),
    "zurich": (47.3769, 8.5417),
    "vienna": (48.2082, 16.3738),
}

# --- Bounded LRU Cache with Shallow Container Protection ---
class LRUCache:
    def __init__(self, capacity: int = MAX_CACHE_ENTRIES):
        self.capacity = capacity
        self.cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        if key not in self.cache:
            return None
        expires_at, val = self.cache[key]
        if now > expires_at:
            del self.cache[key]
            return None
        self.cache.move_to_end(key)
        # Return shallow copy of containers to prevent caller mutation without allocating deep copies
        if isinstance(val, tuple):
            return tuple(list(item) if isinstance(item, (list, tuple)) else item for item in val)
        elif isinstance(val, list):
            return list(val)
        elif isinstance(val, dict):
            return dict(val)
        return val

    def set(self, key: str, val: Any, ttl: float = OPENSKY_CACHE_TTL) -> None:
        now = time.monotonic()
        if key in self.cache:
            self.cache.move_to_end(key)
        # Store immutable or protected snapshot
        if isinstance(val, tuple):
            stored_val = tuple(tuple(item) if isinstance(item, list) else item for item in val)
        elif isinstance(val, list):
            stored_val = tuple(val)
        elif isinstance(val, dict):
            stored_val = copy.deepcopy(val)
        else:
            stored_val = val
        self.cache[key] = (now + ttl, stored_val)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def clear(self) -> None:
        self.cache.clear()


cache = LRUCache()

# --- Rate Limiter with Trusted Proxy Isolation & Bounded History ---
class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, window_seconds: float = RATE_LIMIT_WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.history: Dict[str, List[float]] = {}
        self.max_tracked_ips = 500
        self.trusted_proxies: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = self._load_trusted_proxies()

    def _load_trusted_proxies(self) -> List[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        proxies: List[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
            ipaddress.ip_network("127.0.0.1/32"),
            ipaddress.ip_network("::1/128"),
        ]
        env_val = os.getenv("TRUSTED_PROXIES", "")
        for item in env_val.split(","):
            item = item.strip()
            if item:
                try:
                    proxies.append(ipaddress.ip_network(item, strict=False))
                except ValueError:
                    pass
        return proxies

    def is_peer_trusted(self, peer_ip_str: str) -> bool:
        try:
            peer_ip = ipaddress.ip_address(peer_ip_str)
            return any(peer_ip in net for net in self.trusted_proxies)
        except ValueError:
            return False

    def get_client_ip(self, request: Request) -> str:
        peer_ip = request.client.host if request.client else "127.0.0.1"
        if self.is_peer_trusted(peer_ip):
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                first_hop = forwarded.split(",")[0].strip()
                try:
                    ipaddress.ip_address(first_hop)
                    return first_hop
                except ValueError:
                    pass
        return peer_ip

    def _evict_idle_entries(self, now: float) -> None:
        valid_from = now - self.window_seconds
        idle_ips = [
            ip for ip, timestamps in self.history.items()
            if not timestamps or timestamps[-1] <= valid_from
        ]
        for ip in idle_ips:
            del self.history[ip]
        # If still over limit, drop oldest
        if len(self.history) > self.max_tracked_ips:
            excess = len(self.history) - self.max_tracked_ips
            for ip in list(self.history.keys())[:excess]:
                del self.history[ip]

    def is_rate_limited(self, client_ip: str) -> bool:
        now = time.monotonic()
        valid_from = now - self.window_seconds

        if len(self.history) > self.max_tracked_ips:
            self._evict_idle_entries(now)

        timestamps = self.history.get(client_ip, [])
        timestamps = [ts for ts in timestamps if ts > valid_from]
        if len(timestamps) >= self.max_requests:
            self.history[client_ip] = timestamps
            return True
        timestamps.append(now)
        self.history[client_ip] = timestamps
        return False


rate_limiter = SlidingWindowRateLimiter()

# --- Geographic & Aviation Math Helpers ---
def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two GPS coordinates in kilometers (antimeridian safe)."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    # Normalize dlambda to [-pi, pi] across antimeridian
    dlambda = (dlambda + math.pi) % (2.0 * math.pi) - math.pi

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def calculate_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates initial compass bearing from observer to aircraft in degrees (antimeridian safe)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    # Normalize dlambda to [-pi, pi] across antimeridian
    dlambda = (dlambda + math.pi) % (2.0 * math.pi) - math.pi

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    initial_bearing = math.atan2(y, x)
    return (math.degrees(initial_bearing) + 360.0) % 360.0


def bearing_to_compass(bearing: float) -> str:
    """Converts degrees (0-360) to a 16-wind compass point string."""
    compass_points = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    idx = int((bearing + 11.25) / 22.5) % 16
    return compass_points[idx]


def compute_bounding_boxes(lat: float, lon: float, radius_km: float) -> List[Tuple[float, float, float, float]]:
    """
    Computes list of (lamin, lomin, lamax, lomax) bounding boxes.
    If the search radius crosses the antimeridian (±180°), splits into two separate bounding boxes.
    """
    delta_lat = radius_km / 111.0
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    delta_lon = radius_km / (111.0 * cos_lat)

    lamin = max(-90.0, lat - delta_lat)
    lamax = min(90.0, lat + delta_lat)
    raw_lomin = lon - delta_lon
    raw_lomax = lon + delta_lon

    if raw_lomin < -180.0:
        # Crosses antimeridian to the west: split into [lomin+360, 180] and [-180, lomax]
        return [
            (lamin, raw_lomin + 360.0, lamax, 180.0),
            (lamin, -180.0, lamax, min(180.0, raw_lomax)),
        ]
    elif raw_lomax > 180.0:
        # Crosses antimeridian to the east: split into [lomin, 180] and [-180, lomax-360]
        return [
            (lamin, max(-180.0, raw_lomin), lamax, 180.0),
            (lamin, -180.0, lamax, raw_lomax - 360.0),
        ]
    else:
        return [(lamin, max(-180.0, raw_lomin), lamax, min(180.0, raw_lomax))]


def resolve_coordinates(
    lat: Optional[float],
    lon: Optional[float],
    location: Optional[str]
) -> Tuple[float, float, str]:
    """Resolves coordinates from either direct floats or known metro/airport names."""
    if lat is not None and lon is not None:
        label = f"coordinates ({lat:.4f}, {lon:.4f})"
        return lat, lon, label

    if location:
        norm = location.strip().lower()
        if norm in KNOWN_METRO_COORDINATES:
            c_lat, c_lon = KNOWN_METRO_COORDINATES[norm]
            return c_lat, c_lon, location.strip().title()
        # Fallback partial match
        for k, coords in KNOWN_METRO_COORDINATES.items():
            if k in norm or norm in k:
                return coords[0], coords[1], k.title()

        raise ValueError(
            f"Location '{location}' is not in the built-in city registry. "
            f"Please supply explicit 'latitude' and 'longitude' coordinates (e.g. lat=40.71, lon=-74.00)."
        )

    raise ValueError("Either 'latitude' and 'longitude' or a supported 'location' name must be provided.")


def format_flight_entry(
    state: List[Any],
    observer_lat: Optional[float] = None,
    observer_lon: Optional[float] = None
) -> Dict[str, Any]:
    """
    Parses OpenSky state vector:
    [0: icao24, 1: callsign, 2: origin_country, 3: time_pos, 4: last_contact,
     5: lon, 6: lat, 7: baro_altitude, 8: on_ground, 9: velocity,
     10: true_track, 11: vertical_rate, 12: sensors, 13: geo_altitude,
     14: squawk, 15: spi, 16: position_source]
    """
    icao24 = state[0]
    callsign = (state[1] or "").strip() or f"ICAO-{icao24.upper()}"
    country = state[2] or "Unknown Origin"
    lon = state[5]
    lat = state[6]
    baro_alt_m = state[7]
    on_ground = bool(state[8])
    velocity_mps = state[9]
    heading_deg = state[10]
    vert_rate_mps = state[11]

    # Altitude formatting
    if on_ground:
        alt_str = "On Ground"
        alt_ft = 0
    elif baro_alt_m is not None:
        alt_ft = int(baro_alt_m * 3.28084)
        alt_str = f"{alt_ft:,} ft ({int(baro_alt_m):,} m)"
    else:
        alt_str = "Unknown Altitude"
        alt_ft = 0

    # Speed formatting
    if velocity_mps is not None:
        speed_kts = int(velocity_mps * 1.94384)
        speed_mph = int(velocity_mps * 2.23694)
        speed_str = f"{speed_kts} kts ({speed_mph} mph)"
    else:
        speed_str = "Unknown Speed"
        speed_kts = 0

    # Vertical status
    if on_ground:
        vert_status = "Stationary / Taxiing"
    elif vert_rate_mps is not None:
        rate_fpm = int(vert_rate_mps * 196.85)
        if rate_fpm > 100:
            vert_status = f"Climbing (+{rate_fpm:,} ft/min)"
        elif rate_fpm < -100:
            vert_status = f"Descending ({rate_fpm:,} ft/min)"
        else:
            vert_status = "Level Flight (Cruising)"
    else:
        vert_status = "Cruising"

    # Heading
    heading_str = f"{int(heading_deg)}° ({bearing_to_compass(heading_deg)})" if heading_deg is not None else "N/A"

    # Distance & Direction from observer
    dist_km = None
    dist_miles = None
    bearing_str = None
    if observer_lat is not None and observer_lon is not None and lat is not None and lon is not None:
        dist_km = haversine_distance_km(observer_lat, observer_lon, lat, lon)
        dist_miles = dist_km * 0.621371
        bearing = calculate_bearing_deg(observer_lat, observer_lon, lat, lon)
        bearing_str = bearing_to_compass(bearing)

    return {
        "icao24": icao24,
        "callsign": callsign,
        "country": country,
        "latitude": lat,
        "longitude": lon,
        "altitude": alt_str,
        "altitude_ft": alt_ft,
        "speed": speed_str,
        "speed_kts": speed_kts,
        "heading": heading_str,
        "vertical_status": vert_status,
        "on_ground": on_ground,
        "distance_km": dist_km,
        "distance_miles": dist_miles,
        "compass_direction": bearing_str,
    }


# --- OpenSky Network Client ---
async def fetch_single_opensky_bbox(
    bbox: Optional[Tuple[float, float, float, float]]
) -> Tuple[int, List[List[Any]]]:
    """Fetches real-time ADS-B states for a single bounding box with caching."""
    cache_key = f"opensky_states_{bbox}" if bbox else "opensky_states_global"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    params: Dict[str, Any] = {}
    if bbox:
        lamin, lomin, lamax, lomax = bbox
        params["lamin"] = f"{lamin:.4f}"
        params["lomin"] = f"{lomin:.4f}"
        params["lamax"] = f"{lamax:.4f}"
        params["lomax"] = f"{lomax:.4f}"

    headers = {"User-Agent": "OmiAviationRadar/1.0 (Wearable Intelligence)"}

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(OPENSKY_STATES_URL, params=params, headers=headers)
            if resp.status_code == 429:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="OpenSky flight radar is temporarily rate-limited due to high traffic. Please retry in 15 seconds."
                )
            if resp.status_code >= 500:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="OpenSky upstream service is temporarily unavailable."
                )
            resp.raise_for_status()
            data = resp.json()
            timestamp = data.get("time", int(time.time()))
            raw_states = data.get("states") or []
            result = (timestamp, raw_states)
            cache.set(cache_key, result, ttl=OPENSKY_CACHE_TTL)
            return result
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="OpenSky flight radar is temporarily rate-limited due to high traffic. Please retry in 15 seconds."
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenSky upstream API returned error {status_code}."
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Network error communicating with OpenSky Network: {str(exc)}"
        )


async def fetch_opensky_states(
    bbox: Optional[Tuple[float, float, float, float]] = None
) -> Tuple[int, List[List[Any]]]:
    """Fetches real-time ADS-B states from OpenSky."""
    return await fetch_single_opensky_bbox(bbox)


async def fetch_opensky_states_for_boxes(
    boxes: List[Tuple[float, float, float, float]]
) -> Tuple[int, List[List[Any]]]:
    """Fetches states across one or multiple bounding boxes (handling antimeridian splits)."""
    if not boxes:
        return await fetch_single_opensky_bbox(None)
    if len(boxes) == 1:
        return await fetch_single_opensky_bbox(boxes[0])

    # Multiple bounding boxes (antimeridian wrap)
    combined_states: List[List[Any]] = []
    seen_icaos = set()
    latest_time = 0

    for box in boxes:
        ts, states = await fetch_single_opensky_bbox(box)
        latest_time = max(latest_time, ts)
        for s in states:
            icao = s[0]
            if icao not in seen_icaos:
                seen_icaos.add(icao)
                combined_states.append(s)

    return latest_time, combined_states


# --- FastAPI Application ---
app = FastAPI(
    title="Omi OpenSky Flight Tracker & Live Aviation Radar",
    description="Real-time ADS-B flight tracking, overhead aircraft identification, and airspace activity intelligence for Omi AI wearables.",
    version="1.0.0",
)


# Rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path.startswith("/tools/"):
        client_ip = rate_limiter.get_client_ip(request)
        if rate_limiter.is_rate_limited(client_ip):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"result": None, "error": "Rate limit exceeded (60 requests/minute). Please slow down."}
            )
    response = await call_next(request)
    return response


# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def root():
    """Interactive dashboard for the OpenSky Flight Tracker app."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Omi Live Aviation Radar</title>
        <style>
            :root {
                --bg: #0b0f19;
                --card-bg: #161f30;
                --accent: #38bdf8;
                --text: #f8fafc;
                --text-muted: #94a3b8;
                --border: #334155;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                margin: 0;
                padding: 2rem;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .container {
                max-width: 850px;
                width: 100%;
            }
            header {
                text-align: center;
                margin-bottom: 2rem;
            }
            h1 {
                font-size: 2.2rem;
                color: var(--accent);
                margin-bottom: 0.5rem;
            }
            p.lead {
                color: var(--text-muted);
                font-size: 1.1rem;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }
            .card {
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 1.5rem;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            }
            .card h3 {
                margin-top: 0;
                color: var(--accent);
            }
            .card p {
                color: var(--text-muted);
                font-size: 0.95rem;
                line-height: 1.5;
            }
            .badge {
                display: inline-block;
                background: #0284c7;
                color: white;
                padding: 0.25rem 0.6rem;
                border-radius: 6px;
                font-size: 0.75rem;
                font-weight: 600;
                margin-bottom: 0.8rem;
            }
            pre {
                background: #0f172a;
                padding: 1rem;
                border-radius: 8px;
                overflow-x: auto;
                font-size: 0.85rem;
                border: 1px solid var(--border);
            }
            footer {
                text-align: center;
                color: var(--text-muted);
                font-size: 0.85rem;
                margin-top: 2rem;
            }
            a {
                color: var(--accent);
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <div class="badge">OMI WEARABLE INTEGRATION</div>
                <h1>✈️ Live Aviation Radar & Flight Tracker</h1>
                <p class="lead">Real-time ADS-B transponder tracking powered by the OpenSky Network for Omi AI wearables.</p>
            </header>

            <div class="grid">
                <div class="card">
                    <h3>🔭 Overhead Flight Radar</h3>
                    <p>Detects aircraft flying directly overhead using GPS coordinates or city names with compass bearings, altitude, and ground speed.</p>
                    <pre>POST /tools/get_flights_overhead</pre>
                </div>
                <div class="card">
                    <h3>🎯 Flight Tracker</h3>
                    <p>Tracks commercial and private aircraft by callsign (e.g. UAL123, DLH400) reporting flight path, climb rate, and location.</p>
                    <pre>POST /tools/track_flight_by_callsign</pre>
                </div>
                <div class="card">
                    <h3>🌐 Regional Airspace</h3>
                    <p>Summarizes active air traffic volume and cruising aircraft across major countries, metro hubs, and airspace sectors.</p>
                    <pre>POST /tools/get_airspace_activity</pre>
                </div>
            </div>

            <div class="card">
                <h3>Omi Integration Contract</h3>
                <p>Check the registered tools manifest at <a href="/.well-known/omi-tools.json">/.well-known/omi-tools.json</a> or monitor service health at <a href="/health">/health</a>.</p>
            </div>

            <footer>
                <p>Built for Omi AI Wearables | Sourced from OpenSky Network Open Data</p>
            </footer>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health():
    """Local, I/O-free deployment health check probe for Railway and Docker."""
    return {
        "status": "healthy",
        "service": "omi-flight-tracker-app",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health/upstream")
async def health_upstream():
    """Diagnostic health check probing upstream OpenSky Network status with caching."""
    cached_status = cache.get("upstream_health_status")
    if cached_status is not None:
        return cached_status

    upstream_ok = True
    message = "OpenSky Network flight tracker upstream is healthy and operational."
    try:
        # Probe OpenSky with a small 0.1 degree bounding box over London Heathrow
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                OPENSKY_STATES_URL,
                params={"lamin": "51.4", "lomin": "-0.5", "lamax": "51.5", "lomax": "-0.4"},
                headers={"User-Agent": "OmiHealthProbe/1.0"}
            )
            if resp.status_code not in (200, 429):
                upstream_ok = False
                message = f"Upstream OpenSky API returned HTTP {resp.status_code}."
    except Exception as exc:
        upstream_ok = False
        message = f"Upstream OpenSky connectivity check failed: {str(exc)}"

    status_data = {
        "status": "healthy" if upstream_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "upstream_connected": upstream_ok,
        "message": message,
    }
    cache.set("upstream_health_status", status_data, ttl=60.0)
    return status_data


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest():
    """Official Omi tools manifest registering all available chat tools."""
    return {
        "name": "Live Aviation Radar & Flight Tracker",
        "description": "Real-time ADS-B transponder flight tracking and overhead aircraft identification for Omi AI wearables.",
        "version": "1.0.0",
        "author": "Omi Community",
        "homepage": "https://opensky-network.org",
        "auth_required": False,
        "tools": [
            {
                "name": "get_flights_overhead",
                "description": "Identifies aircraft flying overhead or near a geographic location. Calculates distance, compass bearing, altitude, speed, and climbing status for wearable users looking up at the sky.",
                "endpoint": "/tools/get_flights_overhead",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "Observer latitude in decimal degrees (-90.0 to 90.0)."
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Observer longitude in decimal degrees (-180.0 to 180.0)."
                        },
                        "location": {
                            "type": "string",
                            "description": "City or airport name (e.g. 'London', 'New York', 'Paris', 'Tokyo')."
                        },
                        "radius_km": {
                            "type": "number",
                            "description": "Search radius in kilometers around observer (default: 30 km, max: 150 km)."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of aircraft to return (default: 5, max: 20)."
                        }
                    }
                }
            },
            {
                "name": "track_flight_by_callsign",
                "description": "Tracks a specific commercial or private aircraft in real time by its flight callsign (e.g. 'UAL123', 'BAW28') or 6-character ICAO address. Reports current altitude, ground speed, coordinates, and flight status.",
                "endpoint": "/tools/track_flight_by_callsign",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "callsign": {
                            "type": "string",
                            "description": "Commercial flight callsign (e.g. 'UAL123', 'DLH400', 'BAW28') or hex ICAO address."
                        }
                    },
                    "required": ["callsign"]
                }
            },
            {
                "name": "get_airspace_activity",
                "description": "Provides a live summary of active air traffic and aircraft volume across a country, metro region, or altitude band.",
                "endpoint": "/tools/get_airspace_activity",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Country of aircraft registration to filter by (e.g. 'United States', 'United Kingdom', 'Germany')."
                        },
                        "location": {
                            "type": "string",
                            "description": "Major metro area (e.g. 'New York', 'London', 'Frankfurt')."
                        },
                        "min_altitude_meters": {
                            "type": "number",
                            "description": "Filter for aircraft above a minimum altitude in meters (e.g. 9000 for cruising flight)."
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of aircraft to list (default: 8)."
                        }
                    }
                }
            }
        ]
    }


@app.post("/tools/get_flights_overhead", response_model=ChatToolResponse)
async def get_flights_overhead(req: FlightsOverheadRequest) -> ChatToolResponse:
    """Tool: Identifies aircraft flying overhead near a GPS coordinate or named city."""
    try:
        obs_lat, obs_lon, location_label = resolve_coordinates(req.latitude, req.longitude, req.location)
    except ValueError as err:
        return ChatToolResponse(error=str(err))

    boxes = compute_bounding_boxes(obs_lat, obs_lon, req.radius_km)

    try:
        timestamp, raw_states = await fetch_opensky_states_for_boxes(boxes)
    except HTTPException as exc:
        return ChatToolResponse(error=exc.detail)
    except Exception as exc:
        return ChatToolResponse(error=f"Error fetching flight data: {str(exc)}")

    if not raw_states:
        return ChatToolResponse(
            result=f"No active aircraft detected within {req.radius_km:.0f} km of {location_label} at this moment."
        )

    # Parse and sort aircraft by proximity to observer
    parsed_flights: List[Dict[str, Any]] = []
    for state in raw_states:
        f = format_flight_entry(state, obs_lat, obs_lon)
        if f["distance_km"] is not None and f["distance_km"] <= req.radius_km:
            parsed_flights.append(f)

    if not parsed_flights:
        return ChatToolResponse(
            result=f"No active aircraft currently within {req.radius_km:.0f} km of {location_label}."
        )

    parsed_flights.sort(key=lambda x: x["distance_km"] or 999999.0)
    top_flights = parsed_flights[: req.limit]

    # Build voice-optimized Markdown synthesis
    lines = [
        f"✈️ **Live Overhead Radar for {location_label}** ({len(parsed_flights)} aircraft within {req.radius_km:.0f} km):",
        ""
    ]

    for idx, f in enumerate(top_flights, 1):
        dist_str = f"{f['distance_miles']:.1f} mi ({f['distance_km']:.1f} km)"
        bearing_str = f"{f['compass_direction']}" if f["compass_direction"] else "nearby"
        lines.append(
            f"**{idx}. Flight {f['callsign']}** ({f['country']})\n"
            f"   • **Position**: {dist_str} to your **{bearing_str}**\n"
            f"   • **Altitude**: {f['altitude']} — {f['vertical_status']}\n"
            f"   • **Speed & Heading**: {f['speed']} heading {f['heading']}"
        )

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/track_flight_by_callsign", response_model=ChatToolResponse)
async def track_flight_by_callsign(req: TrackFlightRequest) -> ChatToolResponse:
    """Tool: Tracks a flight in real time by callsign or ICAO address (exact match only)."""
    target = req.callsign.upper()

    try:
        timestamp, raw_states = await fetch_opensky_states(bbox=None)
    except HTTPException as exc:
        return ChatToolResponse(error=exc.detail)
    except Exception as exc:
        return ChatToolResponse(error=f"Error fetching flight tracking data: {str(exc)}")

    if not raw_states:
        return ChatToolResponse(error="No flight telemetry currently available from OpenSky Network.")

    # Search for exact matching callsign or icao24 (no partial substring match)
    matches: List[List[Any]] = []
    for state in raw_states:
        callsign = (state[1] or "").strip().upper()
        icao = (state[0] or "").strip().upper()
        if callsign == target or icao == target:
            matches.append(state)

    if not matches:
        return ChatToolResponse(
            result=f"Flight '{target}' was not detected in active airspace. It may be between radar coverage zones, on the ground without an active transponder, or scheduled for a later departure."
        )

    best_match = matches[0]
    f = format_flight_entry(best_match)

    lat_str = f"{f['latitude']:.4f}" if f["latitude"] is not None else "Unknown"
    lon_str = f"{f['longitude']:.4f}" if f["longitude"] is not None else "Unknown"

    result_md = (
        f"✈️ **Live Tracking: Flight {f['callsign']}**\n\n"
        f"• **Country of Origin**: {f['country']}\n"
        f"• **ICAO 24-bit Address**: `{f['icao24'].upper()}`\n"
        f"• **Flight Status**: {f['vertical_status']}\n"
        f"• **Altitude**: {f['altitude']}\n"
        f"• **Ground Speed**: {f['speed']}\n"
        f"• **Current Coordinates**: {lat_str}, {lon_str}\n"
        f"• **Heading**: {f['heading']}"
    )

    return ChatToolResponse(result=result_md)


@app.post("/tools/get_airspace_activity", response_model=ChatToolResponse)
async def get_airspace_activity(req: AirspaceActivityRequest) -> ChatToolResponse:
    """Tool: Reports airspace traffic volume and active flights by country or region."""
    bbox = None
    area_label = "Global Airspace"

    if req.location:
        norm = req.location.strip().lower()
        coords = None
        matched_name = req.location.strip().title()
        if norm in KNOWN_METRO_COORDINATES:
            coords = KNOWN_METRO_COORDINATES[norm]
        else:
            for k, c in KNOWN_METRO_COORDINATES.items():
                if k in norm or norm in k:
                    coords = c
                    matched_name = k.title()
                    break

        if not coords:
            return ChatToolResponse(
                error=(
                    f"Location '{req.location}' is not in the built-in city registry. "
                    "Please choose a supported metro area such as London, New York, Frankfurt, Tokyo, Paris, or Atlanta."
                )
            )

        lat, lon = coords
        boxes = compute_bounding_boxes(lat, lon, radius_km=100.0)
        bbox = boxes[0] if boxes else None
        area_label = f"Greater {matched_name} Airspace (100km radius)"

    try:
        timestamp, raw_states = await fetch_opensky_states(bbox=bbox)
    except HTTPException as exc:
        return ChatToolResponse(error=exc.detail)
    except Exception as exc:
        return ChatToolResponse(error=f"Error fetching airspace activity data: {str(exc)}")

    if not raw_states:
        return ChatToolResponse(result=f"No active aircraft currently reported for {area_label}.")

    filtered_states = raw_states

    # Filter by country if requested
    if req.country:
        target_country = req.country.strip().lower()
        filtered_states = [s for s in filtered_states if s[2] and target_country in s[2].lower()]
        area_label = f"{req.country.title()} registered aircraft in {area_label}"

    # Filter by minimum altitude if requested
    if req.min_altitude_meters is not None:
        filtered_states = [
            s for s in filtered_states
            if s[7] is not None and s[7] >= req.min_altitude_meters
        ]

    total_count = len(filtered_states)
    if total_count == 0:
        return ChatToolResponse(
            result=f"No aircraft matched the specified filters for {area_label}."
        )

    # Airborne vs on-ground count
    airborne = sum(1 for s in filtered_states if not s[8])
    on_ground = total_count - airborne

    # Sample top flights
    sample = filtered_states[: req.limit]
    sample_lines = []
    for s in sample:
        f = format_flight_entry(s)
        sample_lines.append(
            f"• **{f['callsign']}** ({f['country']}) — {f['altitude']}, {f['speed']}"
        )

    output = [
        f"🌐 **Airspace Activity Report: {area_label}**",
        f"• **Total Tracked Aircraft**: {total_count:,}",
        f"• **Airborne**: {airborne:,} | **On Ground**: {on_ground:,}",
        "",
        f"**Sample Active Flights (showing {len(sample)} of {total_count:,}):**",
        *sample_lines
    ]

    return ChatToolResponse(result="\n".join(output))
