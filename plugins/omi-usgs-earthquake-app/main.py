"""
USGS Earthquake chat tools for Omi.

This app gives Omi users no-auth earthquake lookup tools backed by the public
USGS FDSN event API.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel


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


class ChatToolResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


app = FastAPI(
    title="USGS Earthquake Omi Integration",
    description="Recent, nearby, and event-specific earthquake lookup tools for Omi.",
    version="1.0.0",
)


def _headers() -> Dict[str, str]:
    return {
        "Accept": "application/geo+json, application/json",
        "User-Agent": USGS_USER_AGENT,
    }


def _safe_int(value: Any, default: int, minimum: int = 1, maximum: int = 10) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _parse_float(value: Any) -> Optional[float]:
    try:
        return float(value)
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
    return (
        datetime.fromtimestamp(number / 1000, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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


async def _read_json_body(request: Request) -> tuple[Optional[Dict[str, Any]], Optional[ChatToolResponse]]:
    try:
        body = await request.json()
    except ValueError:
        return None, _invalid_json_response()

    if not isinstance(body, dict):
        return None, _invalid_json_response()
    return body, None


def _query_params(body: Dict[str, Any], default_hours: int = 24) -> Dict[str, Any]:
    hours = _safe_int(body.get("hours"), default=default_hours, minimum=1, maximum=168)
    return {
        "format": "geojson",
        "starttime": _starttime_from_hours(hours),
        "minmagnitude": _safe_float(
            body.get("min_magnitude"), default=2.5, minimum=0.0, maximum=10.0
        ),
        "limit": _safe_int(body.get("limit"), default=5, minimum=1, maximum=10),
        "orderby": _safe_orderby(body.get("orderby")),
    }


def _summarize_feature(feature: Dict[str, Any]) -> Dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    longitude = coordinates[0] if len(coordinates) > 0 else None
    latitude = coordinates[1] if len(coordinates) > 1 else None
    depth_km = coordinates[2] if len(coordinates) > 2 else None

    return {
        "event_id": feature.get("id") or properties.get("code") or "",
        "magnitude": properties.get("mag"),
        "place": properties.get("place") or "Unknown location",
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
        "event_url": properties.get("url") or "",
        "detail_url": properties.get("detail") or "",
    }


async def _usgs_get(params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(
            headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(USGS_QUERY_URL, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        return {"error": f"USGS request failed: {exc}"}
    except ValueError:
        return {"error": "USGS returned a non-JSON response"}


async def _list_earthquakes(params: Dict[str, Any]) -> Dict[str, Any]:
    payload = await _usgs_get(params)
    if "error" in payload:
        return payload

    features = payload.get("features") or []
    return {
        "earthquakes": [_summarize_feature(feature) for feature in features],
        "count": len(features),
        "metadata": payload.get("metadata") or {},
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
    if payload.get("type") != "Feature" or not payload.get("properties"):
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
