"""
USGS Earthquake chat tools for Omi.

This app gives Omi users no-auth earthquake lookup tools backed by the public
USGS FDSN event API.
"""

from __future__ import annotations

import math
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import FastAPI, Request

try:
    from .models import (
        ChatToolResponse,
        EarthquakeDetailsRequest,
        NearbyEarthquakesRequest,
        RecentEarthquakesRequest,
    )
except ImportError:
    try:
        from models import (
            ChatToolResponse,
            EarthquakeDetailsRequest,
            NearbyEarthquakesRequest,
            RecentEarthquakesRequest,
        )
    except ImportError:
        from pydantic import BaseModel

        class ChatToolResponse(BaseModel):
            success: bool
            message: str
            data: Optional[Dict[str, Any]] = None

        class RecentEarthquakesRequest(BaseModel):
            hours: Optional[int] = 24
            min_magnitude: Optional[float] = 2.5
            limit: Optional[int] = 5
            orderby: Optional[str] = "time"

        class NearbyEarthquakesRequest(BaseModel):
            latitude: float
            longitude: float
            radius_km: Optional[float] = 250.0
            hours: Optional[int] = 168
            min_magnitude: Optional[float] = 2.5
            limit: Optional[int] = 5

        class EarthquakeDetailsRequest(BaseModel):
            event_id: str


USGS_QUERY_URL = os.getenv(
    "USGS_QUERY_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query"
).strip()
USGS_USER_AGENT = os.getenv(
    "USGS_USER_AGENT",
    "OmiUsgsEarthquakeApp/1.0 (https://github.com/BasedHardware/omi)",
)
REQUEST_TIMEOUT_SECONDS = float(os.getenv("USGS_TIMEOUT_SECONDS", "8"))
DATA_NOTE = "USGS earthquake data can be preliminary and may change after review."
ORDER_BY_VALUES = {"time", "time-asc", "magnitude", "magnitude-asc"}
INVALID_JSON_MESSAGE = "Invalid or missing JSON body"


def _headers() -> Dict[str, str]:
    return {
        "Accept": "application/geo+json, application/json",
        "User-Agent": USGS_USER_AGENT,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(
        headers=_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(
    title="USGS Earthquake Omi Integration",
    description="Recent, nearby, and event-specific earthquake lookup tools for Omi.",
    version="1.0.0",
    lifespan=lifespan,
)


def _get_http_client() -> Tuple[httpx.AsyncClient, bool]:
    client = getattr(app.state, "http_client", None)
    if client is not None and not getattr(client, "is_closed", False):
        return client, False
    return (
        httpx.AsyncClient(headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS),
        True,
    )


def _safe_int(value: Any, default: int, minimum: int = 1, maximum: int = 10) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _parse_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _safe_float(
    value: Any,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    number = _parse_float(value)
    if number is None:
        return default
    return max(minimum, min(maximum, number))


def _starttime_from_hours(hours: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(hours=hours)
    return start.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_to_utc(value: Any) -> Optional[str]:
    number = _parse_float(value)
    if number is None:
        return None
    try:
        return (
            datetime.fromtimestamp(number / 1000, timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except (ValueError, OverflowError, OSError):
        return None


def _safe_orderby(value: Any) -> str:
    orderby = str(value or "time").strip()
    if orderby not in ORDER_BY_VALUES:
        return "time"
    return orderby


def _invalid_json_response() -> ChatToolResponse:
    return ChatToolResponse(
        success=False,
        message=INVALID_JSON_MESSAGE,
        data={"error": "invalid request body"},
    )


async def _read_json_body(
    request: Request,
) -> tuple[Optional[Dict[str, Any]], Optional[ChatToolResponse]]:
    try:
        body = await request.json()
    except Exception:
        return None, _invalid_json_response()

    if not isinstance(body, dict):
        return None, _invalid_json_response()
    return body, None


def _query_params(body: Dict[str, Any], default_hours: int = 24) -> Dict[str, Any]:
    hours = _safe_int(body.get("hours"), default=default_hours, minimum=1, maximum=168)
    min_magnitude = _parse_float(body.get("min_magnitude"))
    if min_magnitude is None or not math.isfinite(min_magnitude):
        min_magnitude = 2.5
    return {
        "format": "geojson",
        "starttime": _starttime_from_hours(hours),
        "minmagnitude": min(10.0, min_magnitude),
        "limit": _safe_int(body.get("limit"), default=5, minimum=1, maximum=10),
        "orderby": _safe_orderby(body.get("orderby")),
    }


def _summarize_feature(feature: Any) -> Dict[str, Any]:
    if not isinstance(feature, dict):
        feature = {}
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        geometry = {}
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)):
        coordinates = []

    longitude = None
    latitude = None
    depth_km = None

    if len(coordinates) > 0:
        longitude = _parse_float(coordinates[0])
    if len(coordinates) > 1:
        latitude = _parse_float(coordinates[1])
    if len(coordinates) > 2:
        depth_km = _parse_float(coordinates[2])

    event_id = str(feature.get("id") or properties.get("code") or "").strip()
    place = str(properties.get("place") or "Unknown location").strip() or "Unknown location"
    event_url = str(properties.get("url") or "").strip()
    detail_url = str(properties.get("detail") or "").strip()

    return {
        "event_id": event_id,
        "magnitude": properties.get("mag"),
        "place": place,
        "time_utc": _timestamp_to_utc(properties.get("time")),
        "updated_utc": _timestamp_to_utc(properties.get("updated")),
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
            "depth_km": depth_km,
        },
        "alert": properties.get("alert"),
        "status": properties.get("status"),
        "tsunami": bool(properties.get("tsunami")),
        "felt_reports": properties.get("felt"),
        "significance": properties.get("sig"),
        "event_url": event_url,
        "detail_url": detail_url,
    }


async def _usgs_get(params: Dict[str, Any]) -> Dict[str, Any]:
    client, should_close = _get_http_client()
    try:
        response = await client.get(USGS_QUERY_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return {"error": "USGS returned an invalid non-dict payload"}
        return data
    except httpx.HTTPError as exc:
        return {"error": f"USGS request failed: {exc}"}
    except ValueError:
        return {"error": "USGS returned a non-JSON response"}
    finally:
        if should_close:
            await client.aclose()


async def _list_earthquakes(params: Dict[str, Any]) -> Dict[str, Any]:
    payload = await _usgs_get(params)
    if "error" in payload:
        return payload

    if not isinstance(payload, dict):
        return {"error": "USGS returned an unexpected response format"}

    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raw_features = []

    features = [_summarize_feature(f) for f in raw_features if isinstance(f, dict)]
    raw_metadata = payload.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}

    return {
        "earthquakes": features,
        "count": len(features),
        "metadata": metadata,
        "data_note": DATA_NOTE,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "omi-usgs-earthquake-app"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "recent_earthquakes",
                "description": (
                    "Find recent earthquakes globally by time window, minimum magnitude, "
                    "and result limit. Use for questions like 'show earthquakes above "
                    "magnitude 5 in the last day'."
                ),
                "endpoint": "/tools/recent_earthquakes",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "How many hours back to search. Defaults to 24 and is capped at 168.",
                        },
                        "min_magnitude": {
                            "type": "number",
                            "description": "Minimum earthquake magnitude. Defaults to 2.5.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of events to return. Defaults to 5 and is capped at 10.",
                        },
                        "orderby": {
                            "type": "string",
                            "description": "Sort order: time, time-asc, magnitude, or magnitude-asc.",
                        },
                    },
                    "required": [],
                },
                "auth_required": False,
                "status_message": "Checking recent USGS earthquakes...",
            },
            {
                "name": "nearby_earthquakes",
                "description": (
                    "Find earthquakes near a latitude and longitude within a radius. "
                    "Use when the user asks about earthquake activity near a city, "
                    "trip, or exact coordinates."
                ),
                "endpoint": "/tools/nearby_earthquakes",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "Latitude in decimal degrees.",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude in decimal degrees.",
                        },
                        "radius_km": {
                            "type": "number",
                            "description": "Search radius in kilometers. Defaults to 250 and is capped at 2000.",
                        },
                        "hours": {
                            "type": "integer",
                            "description": "How many hours back to search. Defaults to 168 and is capped at 168.",
                        },
                        "min_magnitude": {
                            "type": "number",
                            "description": "Minimum earthquake magnitude. Defaults to 2.5.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of events to return. Defaults to 5 and is capped at 10.",
                        },
                    },
                    "required": ["latitude", "longitude"],
                },
                "auth_required": False,
                "status_message": "Searching nearby USGS earthquakes...",
            },
            {
                "name": "earthquake_details",
                "description": (
                    "Look up a specific USGS earthquake event by event ID and return "
                    "magnitude, place, time, review status, alert level, depth, "
                    "coordinates, and USGS links."
                ),
                "endpoint": "/tools/earthquake_details",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "event_id": {
                            "type": "string",
                            "description": "USGS event ID, such as us7000abcd.",
                        }
                    },
                    "required": ["event_id"],
                },
                "auth_required": False,
                "status_message": "Looking up the USGS earthquake event...",
            },
        ]
    }


@app.get("/manifest.json")
async def get_manifest_alias():
    return await get_omi_tools_manifest()


@app.post("/tools/recent_earthquakes", response_model=ChatToolResponse)
async def tool_recent_earthquakes(request: Request):
    body, error = await _read_json_body(request)
    if error:
        return error
    result = await _list_earthquakes(_query_params(body, default_hours=24))
    if "error" in result:
        return ChatToolResponse(success=False, message=result["error"], data=result)

    count = result["count"]
    message = (
        f"Found {count} earthquake event(s)."
        if count
        else "No USGS earthquake events found for the requested filters."
    )
    return ChatToolResponse(success=True, message=message, data=result)


@app.post("/tools/nearby_earthquakes", response_model=ChatToolResponse)
async def tool_nearby_earthquakes(request: Request):
    body, error = await _read_json_body(request)
    if error:
        return error
    latitude = _parse_float(body.get("latitude"))
    longitude = _parse_float(body.get("longitude"))
    if latitude is None or longitude is None:
        return ChatToolResponse(
            success=False,
            message="latitude and longitude are required",
            data={"error": "latitude and longitude are required"},
        )
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return ChatToolResponse(
            success=False,
            message="latitude must be between -90 and 90 and longitude between -180 and 180",
            data={"error": "coordinates are out of range"},
        )

    params = _query_params(body, default_hours=168)
    params.update(
        {
            "latitude": latitude,
            "longitude": longitude,
            "maxradiuskm": _safe_float(
                body.get("radius_km"), default=250.0, minimum=1.0, maximum=2000.0
            ),
        }
    )
    result = await _list_earthquakes(params)
    if "error" in result:
        return ChatToolResponse(success=False, message=result["error"], data=result)

    count = result["count"]
    message = (
        f"Found {count} nearby earthquake event(s)."
        if count
        else "No nearby USGS earthquake events found for the requested filters."
    )
    return ChatToolResponse(success=True, message=message, data=result)


@app.post("/tools/earthquake_details", response_model=ChatToolResponse)
async def tool_earthquake_details(request: Request):
    body, error = await _read_json_body(request)
    if error:
        return error
    event_id = str(body.get("event_id") or "").strip()
    if not event_id:
        return ChatToolResponse(
            success=False,
            message="event_id is required",
            data={"error": "event_id is required"},
        )

    payload = await _usgs_get({"format": "geojson", "eventid": event_id})
    if "error" in payload:
        return ChatToolResponse(success=False, message=payload["error"], data=payload)
    if not isinstance(payload, dict) or payload.get("type") != "Feature" or not isinstance(payload.get("properties"), dict):
        return ChatToolResponse(
            success=False,
            message=f"No USGS earthquake event found for {event_id}.",
            data={"error": "event not found", "event_id": event_id, "data_note": DATA_NOTE},
        )

    event = _summarize_feature(payload)
    return ChatToolResponse(
        success=True,
        message=f"Earthquake event {event['event_id'] or event_id} found.",
        data={"earthquake": event, "data_note": DATA_NOTE},
    )
