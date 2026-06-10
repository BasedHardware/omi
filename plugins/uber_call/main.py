from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from uber_links import build_location, build_uber_deep_links


app = FastAPI(title="Omi Uber Call App")


class CallUberRequest(BaseModel):
    uid: str | None = None
    app_id: str | None = None
    tool_name: str | None = None
    destination: str | None = Field(
        default=None,
        description="The destination the user wants to go to, such as 'SFO airport'.",
    )
    pickup_address: str | None = None
    pickup_latitude: float | None = None
    pickup_longitude: float | None = None
    dropoff_address: str | None = None
    dropoff_latitude: float | None = None
    dropoff_longitude: float | None = None
    product_id: str | None = None
    geolocation: dict[str, Any] | None = None


def _geo_value(geolocation: dict[str, Any] | None, *keys: str) -> Any:
    if not geolocation:
        return None
    for key in keys:
        value = geolocation.get(key)
        if value not in (None, ""):
            return value
    return None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
def omi_tools_manifest() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "call_uber",
                "description": (
                    "Prepare an Uber ride link for the user's requested destination. "
                    "Use this when the user asks to call, book, or open Uber. "
                    "The user must confirm the ride inside Uber."
                ),
                "endpoint": "/api/call_uber",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Required destination name or address, for example 'SFO airport'.",
                        },
                        "dropoff_address": {
                            "type": "string",
                            "description": "Optional exact dropoff formatted address.",
                        },
                        "dropoff_latitude": {
                            "type": "number",
                            "description": "Optional dropoff latitude.",
                        },
                        "dropoff_longitude": {
                            "type": "number",
                            "description": "Optional dropoff longitude.",
                        },
                        "pickup_address": {
                            "type": "string",
                            "description": "Optional pickup formatted address. Defaults to user's current location.",
                        },
                        "pickup_latitude": {
                            "type": "number",
                            "description": "Optional pickup latitude.",
                        },
                        "pickup_longitude": {
                            "type": "number",
                            "description": "Optional pickup longitude.",
                        },
                        "product_id": {
                            "type": "string",
                            "description": "Optional Uber product_id if the app owner wants to preselect a ride type.",
                        },
                    },
                    "required": ["destination"],
                },
                "auth_required": False,
                "status_message": "Preparing Uber ride link...",
            }
        ]
    }


@app.post("/api/call_uber")
def call_uber(payload: CallUberRequest) -> dict[str, str]:
    pickup_latitude = (
        payload.pickup_latitude
        if payload.pickup_latitude is not None
        else _geo_value(payload.geolocation, "latitude", "lat")
    )
    pickup_longitude = (
        payload.pickup_longitude
        if payload.pickup_longitude is not None
        else _geo_value(payload.geolocation, "longitude", "lng", "lon")
    )
    pickup_address = payload.pickup_address or _geo_value(payload.geolocation, "formatted_address", "address")

    try:
        pickup = build_location(
            latitude=pickup_latitude,
            longitude=pickup_longitude,
            formatted_address=pickup_address,
            nickname=(
                "Current location"
                if pickup_address or (pickup_latitude is not None and pickup_longitude is not None)
                else None
            ),
        )
        dropoff = build_location(
            latitude=payload.dropoff_latitude,
            longitude=payload.dropoff_longitude,
            formatted_address=payload.dropoff_address or payload.destination,
            nickname=payload.destination or payload.dropoff_address,
        )
        links = build_uber_deep_links(
            destination=payload.destination,
            pickup=pickup,
            dropoff=dropoff,
            product_id=payload.product_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    destination = payload.destination or payload.dropoff_address or "the selected destination"
    return {
        "result": (
            f"Uber is ready for {destination}. Open this link to review and confirm the ride in Uber: "
            f"{links.web_link}"
        ),
        "web_link": links.web_link,
        "app_link": links.app_link,
    }
