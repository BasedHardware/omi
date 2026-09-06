"""Omi CityBikes Global Micro-Mobility & Transit Integration App.

Provides voice-optimized chat tools for locating bike-share networks, finding
nearby stations, checking real-time available bikes and empty docks across 800+
networks in 400+ cities worldwide using the CityBikes API (api.citybik.es).
"""

import math
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from .models import (
        ChatToolResponse,
        CityOverviewRequest,
        NearbyStationsRequest,
        SearchNetworksRequest,
        StationStatusRequest,
    )
except ImportError:
    from models import (
        ChatToolResponse,
        CityOverviewRequest,
        NearbyStationsRequest,
        SearchNetworksRequest,
        StationStatusRequest,
    )

BASE_API_URL = "https://api.citybik.es/v2"
API_TIMEOUT = 12.0
USER_AGENT = "OmiCityBikesApp/1.0 (https://github.com/BasedHardware/omi)"

# Caching Configuration
NETWORKS_CACHE_TTL = 3600.0  # 1 hour for network list
STATIONS_CACHE_TTL = 60.0    # 1 minute for live station availability
MAX_CACHE_ENTRIES = 500

_networks_cache: Optional[Tuple[float, List[Dict[str, Any]]]] = None
_stations_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

# Rate Limiting Configuration
RATE_LIMIT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_REQUESTS = 60
_rate_limit_records: Dict[str, List[float]] = {}


def check_rate_limit(request: Optional[Request]) -> bool:
    """Sliding-window rate limiter per client IP."""
    if request is None:
        return True

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client and request.client.host:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    now = time.time()
    timestamps = [t for t in _rate_limit_records.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
        _rate_limit_records[client_ip] = timestamps
        return False

    timestamps.append(now)
    _rate_limit_records[client_ip] = timestamps
    return True


def clear_cache() -> None:
    """Flush memory caches (for test isolation)."""
    global _networks_cache
    _networks_cache = None
    _stations_cache.clear()


def clear_rate_limits() -> None:
    """Flush rate limit history (for test isolation)."""
    _rate_limit_records.clear()


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS coordinates in kilometers."""
    earth_radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return earth_radius_km * c


async def fetch_all_networks(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """Fetch global bike networks list with 1-hour in-memory TTL caching."""
    global _networks_cache
    now = time.time()
    if _networks_cache is not None:
        cached_at, networks = _networks_cache
        if now - cached_at < NETWORKS_CACHE_TTL:
            return networks

    resp = await client.get(
        f"{BASE_API_URL}/networks",
        params={"fields": "id,name,location"},
        headers={"User-Agent": USER_AGENT},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"CityBikes API error (HTTP {resp.status_code})")

    data = resp.json()
    networks = data.get("networks", [])
    _networks_cache = (now, networks)
    return networks


async def fetch_network_details(client: httpx.AsyncClient, network_id: str) -> Dict[str, Any]:
    """Fetch real-time station availability for a network with 60-second TTL caching."""
    now = time.time()
    if network_id in _stations_cache:
        cached_at, network_data = _stations_cache[network_id]
        if now - cached_at < STATIONS_CACHE_TTL:
            return network_data

    resp = await client.get(
        f"{BASE_API_URL}/networks/{network_id}",
        headers={"User-Agent": USER_AGENT},
    )
    if resp.status_code == 404:
        raise KeyError(f"Bike network '{network_id}' not found.")
    if resp.status_code != 200:
        raise RuntimeError(f"CityBikes API error (HTTP {resp.status_code})")

    data = resp.json()
    network_data = data.get("network", {})
    if len(_stations_cache) >= MAX_CACHE_ENTRIES:
        oldest_keys = sorted(_stations_cache.keys(), key=lambda k: _stations_cache[k][0])[:100]
        for k in oldest_keys:
            _stations_cache.pop(k, None)

    _stations_cache[network_id] = (now, network_data)
    return network_data


app = FastAPI(
    title="Omi CityBikes Global Micro-Mobility App",
    description="Real-time bike-share intelligence across 800+ networks worldwide for Omi AI wearable.",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return clean ChatToolResponse on validation error."""
    first_error = exc.errors()[0]
    msg = first_error.get("msg", "Invalid request parameters.")
    loc = first_error.get("loc", [])
    field = loc[-1] if loc else "field"
    return JSONResponse(
        status_code=422,
        content={"error": f"Validation error on '{field}': {msg}", "result": None},
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    """Service landing page and capability summary."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Omi CityBikes Integration App</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }
        .container { max-width: 800px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 2rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3); }
        h1 { color: #38bdf8; margin-top: 0; }
        .badge { display: inline-block; background: #10b981; color: white; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }
        .tools { margin-top: 1.5rem; }
        .tool-card { background: #334155; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
        .tool-name { font-weight: bold; color: #38bdf8; font-family: monospace; }
        code { background: #0f172a; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; color: #f59e0b; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Omi CityBikes Integration App <span class="badge">Active</span></h1>
        <p>Real-time micro-mobility and bike-share intelligence across 800+ networks in 400+ cities worldwide (Citi Bike NYC, Vélib' Paris, Santander Cycles London, BIXI Montreal, etc.).</p>
        
        <div class="tools">
            <h3>Registered Chat Tools:</h3>
            <div class="tool-card">
                <div class="tool-name">POST /tools/search_bike_networks</div>
                <p>Find bike-share networks by city, country, or brand name.</p>
                <div><code>"Find bike sharing in Paris"</code></div>
            </div>
            <div class="tool-card">
                <div class="tool-name">POST /tools/get_nearby_bike_stations</div>
                <p>Search stations by street name or GPS coordinates to find live available bikes.</p>
                <div><code>"Are there bikes available near Union Square?"</code></div>
            </div>
            <div class="tool-card">
                <div class="tool-name">POST /tools/check_bike_station_status</div>
                <p>Check detailed availability (bikes, empty docks, e-bikes) for a specific station.</p>
                <div><code>"Check status of Grand Central bike station"</code></div>
            </div>
            <div class="tool-card">
                <div class="tool-name">POST /tools/get_city_bike_overview</div>
                <p>Get citywide micro-mobility stats (total stations, active bikes, capacity ratio).</p>
                <div><code>"How many bikes are available across Barcelona right now?"</code></div>
            </div>
        </div>

        <p><small>Powered by the open CityBikes API (api.citybik.es) &middot; Manifest at <code>/.well-known/omi-tools.json</code></small></p>
    </div>
</body>
</html>"""


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestrators."""
    return {"status": "ok", "service": "omi-citybikes-app"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest():
    """Official Omi tools discovery manifest."""
    return {
        "schema_version": "v1",
        "name": "CityBikes Global Micro-Mobility & Transit",
        "description": "Real-time bike-share intelligence: locate stations, check live available bikes and empty docks across 800+ networks in 400+ cities worldwide.",
        "tools": [
            {
                "name": "search_bike_networks",
                "description": "Search global bike-share systems by city name, country code, or network brand (e.g. 'New York', 'Paris', 'London', 'Citi Bike', 'Santander').",
                "endpoint": "/tools/search_bike_networks",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "City name, country, or system name to search for.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return (1-20, default 5).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_nearby_bike_stations",
                "description": "Find bike stations in a network filtered by street/station name or sorted by GPS distance, showing real-time available bikes and empty docks.",
                "endpoint": "/tools/get_nearby_bike_stations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "network_id": {
                            "type": "string",
                            "description": "CityBikes network ID (e.g. 'citi-bike-nyc', 'velib-metropole').",
                        },
                        "query": {
                            "type": "string",
                            "description": "Optional street or station name filter (e.g. 'Broadway', 'Central Park').",
                        },
                        "latitude": {
                            "type": "number",
                            "description": "Optional user latitude for distance sorting.",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Optional user longitude for distance sorting.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of stations to return (1-25, default 5).",
                        },
                    },
                    "required": ["network_id"],
                },
            },
            {
                "name": "check_bike_station_status",
                "description": "Check live real-time status of a specific station by name or ID, including available bikes, empty docks, and e-bikes.",
                "endpoint": "/tools/check_bike_station_status",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "network_id": {
                            "type": "string",
                            "description": "CityBikes network ID (e.g. 'citi-bike-nyc').",
                        },
                        "station_id_or_name": {
                            "type": "string",
                            "description": "Station ID or street name.",
                        },
                    },
                    "required": ["network_id", "station_id_or_name"],
                },
            },
            {
                "name": "get_city_bike_overview",
                "description": "Get high-level citywide bike transit statistics including total active stations, fleet size, available bikes, and top stations.",
                "endpoint": "/tools/get_city_bike_overview",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city_or_network": {
                            "type": "string",
                            "description": "City name (e.g. 'Barcelona') or network ID (e.g. 'bicing').",
                        },
                    },
                    "required": ["city_or_network"],
                },
            },
        ],
    }


@app.post("/tools/search_bike_networks", response_model=ChatToolResponse)
async def search_bike_networks(request: SearchNetworksRequest, raw_request: Request):
    """Find bike-share networks by city, country, or system name."""
    if not check_rate_limit(raw_request):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded (max 60 requests/minute). Please slow down.", "result": None},
        )

    q = request.query.lower()

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            networks = await fetch_all_networks(client)

        matches = []
        for n in networks:
            name = n.get("name", "")
            loc = n.get("location", {})
            city = loc.get("city", "")
            country = loc.get("country", "")

            if (
                q in name.lower()
                or q in city.lower()
                or q in country.lower()
                or q == n.get("id", "").lower()
            ):
                matches.append(n)

        if not matches:
            return ChatToolResponse(
                result=f"No bike-share networks found matching '{request.query}'."
            )

        limited = matches[: request.limit]
        lines = [f"Found {len(matches)} bike network(s) matching '{request.query}':\n"]
        for idx, n in enumerate(limited, 1):
            name = n.get("name", "Unknown Network")
            loc = n.get("location", {})
            city = loc.get("city", "Unknown City")
            country = loc.get("country", "")
            nid = n.get("id", "")
            loc_str = f"{city}, {country}".strip(", ")
            lines.append(f"{idx}. **{name}** ({loc_str})")
            lines.append(f"   - Network ID: `{nid}`")

        return ChatToolResponse(result="\n".join(lines))

    except Exception as e:
        return ChatToolResponse(
            error=f"Failed to search bike networks: {str(e)}"
        )


@app.post("/tools/get_nearby_bike_stations", response_model=ChatToolResponse)
async def get_nearby_bike_stations(request: NearbyStationsRequest, raw_request: Request):
    """Search stations in a network filtered by name or sorted by GPS distance."""
    if not check_rate_limit(raw_request):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded (max 60 requests/minute). Please slow down.", "result": None},
        )

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            network_data = await fetch_network_details(client, request.network_id)

        stations = network_data.get("stations", [])
        if not stations:
            return ChatToolResponse(
                result=f"No stations found in network '{request.network_id}'."
            )

        # Filter by name query if provided
        filtered = stations
        if request.query:
            sq = request.query.lower()
            filtered = [s for s in stations if sq in s.get("name", "").lower()]

        if not filtered:
            return ChatToolResponse(
                result=f"No stations in '{network_data.get('name')}' matched '{request.query}'."
            )

        # Distance sorting if GPS coordinates provided
        has_coords = request.latitude is not None and request.longitude is not None
        if has_coords:
            u_lat = request.latitude
            u_lon = request.longitude

            def get_dist(s: Dict[str, Any]) -> float:
                s_lat = s.get("latitude")
                s_lon = s.get("longitude")
                if s_lat is None or s_lon is None:
                    return 99999.0
                return haversine_distance(u_lat, u_lon, s_lat, s_lon)

            filtered.sort(key=get_dist)

        limited = filtered[: request.limit]
        net_name = network_data.get("name", request.network_id)
        city = network_data.get("location", {}).get("city", "")

        lines = [f"### 🚲 Bike Stations: {net_name} ({city})\n"]
        for idx, s in enumerate(limited, 1):
            name = s.get("name", "Unknown Station")
            free_bikes = s.get("free_bikes", 0)
            empty_slots = s.get("empty_slots")
            slots_str = f", {empty_slots} empty docks" if empty_slots is not None else ""

            dist_str = ""
            if has_coords and s.get("latitude") and s.get("longitude"):
                dist_km = haversine_distance(request.latitude, request.longitude, s["latitude"], s["longitude"])
                if dist_km < 1.0:
                    dist_str = f" &middot; {int(dist_km * 1000)}m away"
                else:
                    dist_str = f" &middot; {dist_km:.1f}km away"

            lines.append(f"{idx}. **{name}**{dist_str}")
            lines.append(f"   - **{free_bikes} bikes available**{slots_str}")

        return ChatToolResponse(result="\n".join(lines))

    except KeyError:
        return ChatToolResponse(
            error=f"Bike network '{request.network_id}' not found. Use search_bike_networks to find valid network IDs."
        )
    except Exception as e:
        return ChatToolResponse(
            error=f"Failed to retrieve bike stations: {str(e)}"
        )


@app.post("/tools/check_bike_station_status", response_model=ChatToolResponse)
async def check_bike_station_status(request: StationStatusRequest, raw_request: Request):
    """Check detailed live status of a specific station."""
    if not check_rate_limit(raw_request):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded (max 60 requests/minute). Please slow down.", "result": None},
        )

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            network_data = await fetch_network_details(client, request.network_id)

        stations = network_data.get("stations", [])
        needle = request.station_id_or_name.lower()

        matched_station = None
        # Exact ID match first
        for s in stations:
            if s.get("id") and s.get("id").lower() == needle:
                matched_station = s
                break

        # Substring / name match fallback
        if matched_station is None:
            for s in stations:
                if needle in s.get("name", "").lower():
                    matched_station = s
                    break

        if matched_station is None:
            return ChatToolResponse(
                error=f"No station matching '{request.station_id_or_name}' found in network '{request.network_id}'."
            )

        name = matched_station.get("name", "Unknown Station")
        free_bikes = matched_station.get("free_bikes", 0)
        empty_slots = matched_station.get("empty_slots")
        extra = matched_station.get("extra", {})

        ebikes = extra.get("ebikes")
        has_ebikes = ebikes is not None

        lines = [
            f"## 🚲 Station Status: {name}",
            f"**Network**: {network_data.get('name')} ({network_data.get('location', {}).get('city')})",
            f"- **Available Bikes**: {free_bikes}",
        ]
        if has_ebikes:
            lines.append(f"  *Includes E-Bikes*: {ebikes}")
        if empty_slots is not None:
            lines.append(f"- **Empty Return Docks**: {empty_slots}")

        total_docks = (free_bikes or 0) + (empty_slots or 0)
        if total_docks > 0:
            lines.append(f"- **Total Capacity**: {total_docks} docks")

        last_updated = matched_station.get("timestamp")
        if last_updated:
            lines.append(f"\n*Last updated*: {last_updated[:19].replace('T', ' ')} UTC")

        return ChatToolResponse(result="\n".join(lines))

    except KeyError:
        return ChatToolResponse(
            error=f"Bike network '{request.network_id}' not found."
        )
    except Exception as e:
        return ChatToolResponse(
            error=f"Failed to check station status: {str(e)}"
        )


@app.post("/tools/get_city_bike_overview", response_model=ChatToolResponse)
async def get_city_bike_overview(request: CityOverviewRequest, raw_request: Request):
    """Get high-level citywide bike transit overview and fleet statistics."""
    if not check_rate_limit(raw_request):
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded (max 60 requests/minute). Please slow down.", "result": None},
        )

    target = request.city_or_network.lower()

    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            networks = await fetch_all_networks(client)

            # Match network ID first, then city name
            matched_net_id = None
            matched_net_name = None
            matched_city = None

            for n in networks:
                if n.get("id", "").lower() == target:
                    matched_net_id = n.get("id")
                    matched_net_name = n.get("name")
                    matched_city = n.get("location", {}).get("city")
                    break

            if matched_net_id is None:
                for n in networks:
                    if target in n.get("location", {}).get("city", "").lower():
                        matched_net_id = n.get("id")
                        matched_net_name = n.get("name")
                        matched_city = n.get("location", {}).get("city")
                        break

            if matched_net_id is None:
                return ChatToolResponse(
                    error=f"Could not find a bike-share system for '{request.city_or_network}'. Try searching with search_bike_networks."
                )

            network_data = await fetch_network_details(client, matched_net_id)

        stations = network_data.get("stations", [])
        total_stations = len(stations)
        total_bikes = sum(s.get("free_bikes", 0) for s in stations if s.get("free_bikes") is not None)
        total_empty = sum(s.get("empty_slots", 0) for s in stations if s.get("empty_slots") is not None)
        total_capacity = total_bikes + total_empty
        avail_pct = (total_bikes / total_capacity * 100) if total_capacity > 0 else 0

        # Top 3 stations by available bikes
        top_stations = sorted(stations, key=lambda s: s.get("free_bikes", 0), reverse=True)[:3]

        lines = [
            f"## 🚲 Micro-Mobility Overview: {matched_net_name} ({matched_city})",
            f"- **Active Stations**: {total_stations:,}",
            f"- **Available Bikes Fleet**: {total_bikes:,}",
            f"- **Empty Return Docks**: {total_empty:,}",
            f"- **Network Availability**: {avail_pct:.1f}% of docks holding bikes",
            "\n### Top Stations with High Availability:",
        ]
        for s in top_stations:
            lines.append(f"- **{s.get('name')}**: {s.get('free_bikes')} bikes available")

        return ChatToolResponse(result="\n".join(lines))

    except Exception as e:
        return ChatToolResponse(
            error=f"Failed to generate city overview: {str(e)}"
        )
