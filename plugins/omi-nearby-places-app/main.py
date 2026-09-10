"""
Nearby Places Integration App for Omi.

Answers everyday "where is the nearest ..." questions from OpenStreetMap data:
Nominatim for geocoding and the Overpass API for points of interest. No API key
is required.

Distances are straight-line estimates and walking times are indicative, not
routing results: they help the assistant say "about a 4 minute walk" without
claiming turn-by-turn accuracy.
"""

import math
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
REQUEST_TIMEOUT_SECONDS = 25
USER_AGENT = "omi-nearby-places-app/1.0 (+https://github.com/BasedHardware/omi)"
DEFAULT_RADIUS_METERS = 1000
MAX_RADIUS_METERS = 5000
DEFAULT_LIMIT = 3
MAX_LIMIT = 10
WALKING_METERS_PER_MINUTE = 80.0
STREET_DETOUR_FACTOR = 1.25


app = FastAPI(
    title="Omi Nearby Places Integration",
    description="Find nearby pharmacies, ATMs, cafes, transit stops, and more from Omi chat tools",
    version="1.0.0",
)


# OpenStreetMap tag for each supported category. Keeping this a fixed lookup
# table also keeps caller input out of the Overpass query.
CATEGORY_TAGS: dict[str, tuple[str, str]] = {
    "pharmacy": ("amenity", "pharmacy"),
    "hospital": ("amenity", "hospital"),
    "clinic": ("amenity", "clinic"),
    "doctors": ("amenity", "doctors"),
    "dentist": ("amenity", "dentist"),
    "atm": ("amenity", "atm"),
    "bank": ("amenity", "bank"),
    "police": ("amenity", "police"),
    "post_office": ("amenity", "post_office"),
    "toilets": ("amenity", "toilets"),
    "drinking_water": ("amenity", "drinking_water"),
    "cafe": ("amenity", "cafe"),
    "restaurant": ("amenity", "restaurant"),
    "fast_food": ("amenity", "fast_food"),
    "bar": ("amenity", "bar"),
    "supermarket": ("shop", "supermarket"),
    "bakery": ("shop", "bakery"),
    "convenience": ("shop", "convenience"),
    "laundry": ("shop", "laundry"),
    "fuel": ("amenity", "fuel"),
    "charging_station": ("amenity", "charging_station"),
    "parking": ("amenity", "parking"),
    "bicycle_parking": ("amenity", "bicycle_parking"),
    "bus_stop": ("highway", "bus_stop"),
    "train_station": ("railway", "station"),
    "taxi": ("amenity", "taxi"),
    "hotel": ("tourism", "hotel"),
    "library": ("amenity", "library"),
    "playground": ("leisure", "playground"),
    "park": ("leisure", "park"),
    "museum": ("tourism", "museum"),
    "attraction": ("tourism", "attraction"),
    "place_of_worship": ("amenity", "place_of_worship"),
    "recycling": ("amenity", "recycling"),
}

# Everyday words people actually say, mapped onto the canonical categories.
CATEGORY_ALIASES: dict[str, str] = {
    "drugstore": "pharmacy",
    "chemist": "pharmacy",
    "emergency": "hospital",
    "er": "hospital",
    "doctor": "doctors",
    "gp": "doctors",
    "cash": "atm",
    "cash_machine": "atm",
    "cashpoint": "atm",
    "money": "atm",
    "wc": "toilets",
    "bathroom": "toilets",
    "restroom": "toilets",
    "toilet": "toilets",
    "water": "drinking_water",
    "fountain": "drinking_water",
    "coffee": "cafe",
    "coffee_shop": "cafe",
    "food": "restaurant",
    "fastfood": "fast_food",
    "takeaway": "fast_food",
    "pub": "bar",
    "grocery": "supermarket",
    "groceries": "supermarket",
    "convenience_store": "convenience",
    "gas": "fuel",
    "petrol": "fuel",
    "gas_station": "fuel",
    "ev": "charging_station",
    "ev_charging": "charging_station",
    "charger": "charging_station",
    "car_park": "parking",
    "bus": "bus_stop",
    "bus_station": "bus_stop",
    "train": "train_station",
    "railway": "train_station",
    "subway": "train_station",
    "metro": "train_station",
    "recycling_bins": "recycling",
}


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class NearbyPlacesRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=160)
    category: str = Field(..., min_length=1, max_length=40)
    radius_meters: int = Field(
        default=DEFAULT_RADIUS_METERS, ge=100, le=MAX_RADIUS_METERS
    )
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class NearestPlaceRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=160)
    category: str = Field(..., min_length=1, max_length=40)
    radius_meters: int = Field(
        default=DEFAULT_RADIUS_METERS, ge=100, le=MAX_RADIUS_METERS
    )


def _normalize_category(value: str) -> Optional[str]:
    """Return the canonical category for a spoken category name, or None."""
    cleaned = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if cleaned in CATEGORY_TAGS:
        return cleaned
    return CATEGORY_ALIASES.get(cleaned)


def _parse_coordinates(value: str) -> Optional[tuple[float, float]]:
    """Parse 'lat,lon' input. Returns None when the text is not a coordinate pair."""
    parts = [p.strip() for p in (value or "").split(",")]
    if len(parts) != 2:
        return None
    try:
        latitude = float(parts[0])
        longitude = float(parts[1])
    except ValueError:
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return latitude, longitude


def _haversine_meters(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    """Great-circle distance between two coordinates, in meters."""
    radius = 6371000.0
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def _walking_minutes(meters: float) -> int:
    """Indicative walking time, allowing for street detours."""
    return max(1, int(round(meters * STREET_DETOUR_FACTOR / WALKING_METERS_PER_MINUTE)))


def _format_distance(meters: float) -> str:
    if meters < 1000:
        return f"{int(round(meters))} m"
    return f"{meters / 1000:.1f} km"


def _format_address(tags: dict[str, Any]) -> Optional[str]:
    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    if street and number:
        return f"{street} {number}"
    if street:
        return str(street)
    return tags.get("addr:full")


def _element_coordinates(element: dict[str, Any]) -> Optional[tuple[float, float]]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def _format_element(
    element: dict[str, Any], origin: tuple[float, float], rank: int
) -> Optional[str]:
    coordinates = _element_coordinates(element)
    if coordinates is None:
        return None

    tags = element.get("tags") or {}
    name = tags.get("name") or tags.get("operator") or "Unnamed place"
    meters = _haversine_meters(origin[0], origin[1], coordinates[0], coordinates[1])

    details = [f"{_format_distance(meters)} (~{_walking_minutes(meters)} min walk)"]
    address = _format_address(tags)
    if address:
        details.append(str(address))
    if tags.get("opening_hours"):
        details.append(f"hours: {tags['opening_hours']}")
    if tags.get("phone"):
        details.append(f"phone: {tags['phone']}")

    return f"{rank}. {name} — " + " | ".join(details)


async def _request_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> Any:
    response = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


async def _resolve_location(
    client: httpx.AsyncClient, location: str
) -> tuple[Optional[tuple[float, float]], Optional[str], Optional[str]]:
    """Resolve a place name or coordinate pair into (coordinates, label, error)."""
    cleaned = location.strip()
    if not cleaned:
        return None, None, "location must not be empty"

    coordinates = _parse_coordinates(cleaned)
    if coordinates:
        return coordinates, cleaned, None

    payload = await _request_json(
        client,
        NOMINATIM_URL,
        {"q": cleaned, "format": "jsonv2", "limit": 1, "addressdetails": 0},
    )
    if not payload:
        return None, None, f"I could not find a place called '{cleaned}'."

    best = payload[0]
    try:
        resolved = (float(best["lat"]), float(best["lon"]))
    except (KeyError, TypeError, ValueError):
        return None, None, f"I could not read coordinates for '{cleaned}'."

    label = best.get("display_name") or cleaned
    return resolved, str(label), None


async def _search_places(
    client: httpx.AsyncClient,
    origin: tuple[float, float],
    key: str,
    value: str,
    radius_meters: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Query Overpass for tagged places around the origin, nearest first."""
    query = (
        f"[out:json][timeout:{REQUEST_TIMEOUT_SECONDS}];"
        f'nwr(around:{radius_meters},{origin[0]},{origin[1]})["{key}"="{value}"];'
        f"out center 60;"
    )
    payload = await _request_json(client, OVERPASS_URL, {"data": query})
    elements = payload.get("elements") or []

    ranked: list[tuple[float, dict[str, Any]]] = []
    for element in elements:
        coordinates = _element_coordinates(element)
        if coordinates is None:
            continue
        distance = _haversine_meters(origin[0], origin[1], coordinates[0], coordinates[1])
        ranked.append((distance, element))

    ranked.sort(key=lambda item: item[0])
    return [element for _, element in ranked[:limit]]


async def _find(
    location: str, category: str, radius_meters: int, limit: int
) -> ChatToolResponse:
    canonical = _normalize_category(category)
    if canonical is None:
        supported = ", ".join(sorted(CATEGORY_TAGS))
        return ChatToolResponse(
            error=f"Unsupported category '{category}'. Supported categories: {supported}."
        )

    key, value = CATEGORY_TAGS[canonical]
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            origin, label, error = await _resolve_location(client, location)
            if error or origin is None:
                return ChatToolResponse(error=error or "I could not resolve that location.")

            elements = await _search_places(
                client, origin, key, value, radius_meters, limit
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(
            error=f"The map service did not respond ({exc.__class__.__name__}). Please try again."
        )

    if not elements:
        return ChatToolResponse(
            result=(
                f"No {canonical.replace('_', ' ')} found within "
                f"{_format_distance(float(radius_meters))} of {label}."
            )
        )

    lines = [
        f"Nearest {canonical.replace('_', ' ')} around {label} "
        f"(within {_format_distance(float(radius_meters))}):"
    ]
    rank = 0
    for element in elements:
        formatted = _format_element(element, origin, rank + 1)
        if formatted is None:
            continue
        rank += 1
        lines.append(formatted)

    if rank == 0:
        return ChatToolResponse(
            result=(
                f"No {canonical.replace('_', ' ')} with usable coordinates found near {label}."
            )
        )

    lines.append("Distances and walking times are straight-line estimates.")
    return ChatToolResponse(result="\n".join(lines))


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi Nearby Places Integration</title></head>
      <body>
        <h1>Omi Nearby Places Integration</h1>
        <p>Ask Omi for the nearest pharmacy, ATM, cafe, transit stop, and more.</p>
        <p>Data: OpenStreetMap contributors (Nominatim + Overpass API).</p>
        <p><a href="/.well-known/omi-tools.json">Tool manifest</a></p>
      </body>
    </html>
    """


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "name": "Nearby Places",
        "description": "Find nearby pharmacies, ATMs, cafes, transit stops, and more using OpenStreetMap.",
        "tools": [
            {
                "name": "find_nearby_places",
                "description": "List the closest places of one category around a location, with distance and walking time.",
                "endpoint": "/tools/find_nearby_places",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Place name, address, or 'lat,lon' coordinates.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Place category, such as 'pharmacy', 'atm', 'cafe', 'toilets', or 'train_station'.",
                        },
                        "radius_meters": {
                            "type": "integer",
                            "minimum": 100,
                            "maximum": MAX_RADIUS_METERS,
                            "default": DEFAULT_RADIUS_METERS,
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_LIMIT,
                            "default": DEFAULT_LIMIT,
                        },
                    },
                    "required": ["location", "category"],
                },
            },
            {
                "name": "find_nearest_place",
                "description": "Find the single closest place of one category, for questions like 'where is the nearest pharmacy'.",
                "endpoint": "/tools/find_nearest_place",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "Place name, address, or 'lat,lon' coordinates.",
                        },
                        "category": {"type": "string"},
                        "radius_meters": {
                            "type": "integer",
                            "minimum": 100,
                            "maximum": MAX_RADIUS_METERS,
                            "default": DEFAULT_RADIUS_METERS,
                        },
                    },
                    "required": ["location", "category"],
                },
            },
            {
                "name": "list_place_categories",
                "description": "List the place categories this app can search for.",
                "endpoint": "/tools/list_place_categories",
                "method": "POST",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    }


@app.post("/tools/find_nearby_places", response_model=ChatToolResponse)
async def find_nearby_places(request: NearbyPlacesRequest) -> ChatToolResponse:
    return await _find(
        request.location, request.category, request.radius_meters, request.limit
    )


@app.post("/tools/find_nearest_place", response_model=ChatToolResponse)
async def find_nearest_place(request: NearestPlaceRequest) -> ChatToolResponse:
    return await _find(request.location, request.category, request.radius_meters, 1)


@app.post("/tools/list_place_categories", response_model=ChatToolResponse)
async def list_place_categories() -> ChatToolResponse:
    categories = ", ".join(sorted(CATEGORY_TAGS))
    return ChatToolResponse(
        result=f"Supported place categories: {categories}."
    )
