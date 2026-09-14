"""
Public Holidays Integration App for Omi.

Provides chat tools for public holidays, upcoming holidays, long weekends, and
supported country codes through the public Nager.Date API.
"""

import json
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator


NAGER_BASE_URL = "https://date.nager.at/api/v3"
REQUEST_TIMEOUT_SECONDS = 10
MAX_ITEMS = 20


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi Public Holidays Integration",
    description="Look up public holidays, upcoming holidays, and long weekends from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class HolidayRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    year: int = Field(..., ge=1970, le=2100)
    limit: int = Field(default=MAX_ITEMS, ge=1, le=MAX_ITEMS)

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: Any) -> str:
        return _normalize_country_code(value)


class NextHolidayRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    limit: int = Field(default=8, ge=1, le=MAX_ITEMS)

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: Any) -> str:
        return _normalize_country_code(value)


class LongWeekendRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    year: int = Field(..., ge=1970, le=2100)
    limit: int = Field(default=MAX_ITEMS, ge=1, le=MAX_ITEMS)

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: Any) -> str:
        return _normalize_country_code(value)


def _normalize_country_code(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("country_code must be a 2-letter code, such as US or DE")
    code = value.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("country_code must be a 2-letter code, such as US or DE")
    return code


def _format_list(values: list[str] | None) -> str:
    if not values:
        return "all regions"
    visible = values[:5]
    suffix = "" if len(values) <= 5 else f" +{len(values) - 5} more"
    return ", ".join(visible) + suffix


def _format_holiday(holiday: Any) -> str:
    if not isinstance(holiday, dict):
        return ""
    counties = holiday.get("counties")
    counties_list = counties if isinstance(counties, list) else None
    regional = "global" if holiday.get("global") else _format_list(counties_list)
    raw_types = holiday.get("types")
    types = ", ".join(str(t) for t in raw_types if t) if isinstance(raw_types, list) else ""
    type_text = f"; {types}" if types else ""
    local_name = str(holiday.get("localName") or "").strip()
    name = str(holiday.get("name") or local_name or "Unknown holiday").strip()
    display_name = name if name == local_name or not local_name else f"{name} / {local_name}"
    date_val = str(holiday.get("date") or "unknown date")
    return f"- {date_val}: {display_name} ({regional}{type_text})"


def _format_long_weekend(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    raw_bridge_days = item.get("bridgeDays")
    bridge_days = [str(d) for d in raw_bridge_days if d] if isinstance(raw_bridge_days, list) else []
    if bridge_days:
        bridge_text = f"; bridge day: {', '.join(bridge_days)}"
    elif item.get("needBridgeDay"):
        bridge_text = "; bridge day needed"
    else:
        bridge_text = "; no bridge day needed"
    start_date = str(item.get("startDate") or "unknown")
    end_date = str(item.get("endDate") or "unknown")
    day_count = item.get("dayCount")
    day_text = f"{day_count} days" if day_count is not None else "unknown duration"
    return f"- {start_date} to {end_date}: {day_text}{bridge_text}"


async def _request_json(path: str) -> Any:
    client = getattr(app.state, "http_client", None)
    if client is not None and not getattr(client, "is_closed", False):
        response = await client.get(f"{NAGER_BASE_URL}{path}")
    else:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as fallback_client:
            response = await fallback_client.get(f"{NAGER_BASE_URL}{path}")

    response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return []
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise httpx.HTTPError("public holidays API returned invalid JSON") from exc


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi Public Holidays Integration</title></head>
      <body>
        <h1>Omi Public Holidays Integration</h1>
        <p>Use Omi chat tools to look up holidays, upcoming holidays, and long weekends.</p>
        <p><a href="/.well-known/omi-tools.json">Tool manifest</a></p>
      </body>
    </html>
    """


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> dict[str, Any]:
    country_schema = {"type": "string", "description": "ISO 3166-1 alpha-2 country code, such as US or DE."}
    year_schema = {"type": "integer", "minimum": 1970, "maximum": 2100}
    limit_schema = {"type": "integer", "minimum": 1, "maximum": MAX_ITEMS, "default": MAX_ITEMS}
    return {
        "schema_version": "1.0",
        "name": "Public Holidays",
        "description": "Look up public holidays, upcoming holidays, long weekends, and supported countries.",
        "tools": [
            {
                "name": "get_public_holidays",
                "description": "List public holidays for a country and year.",
                "endpoint": "/tools/get_public_holidays",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {"country_code": country_schema, "year": year_schema, "limit": limit_schema},
                    "required": ["country_code", "year"],
                },
            },
            {
                "name": "get_next_public_holidays",
                "description": "List upcoming public holidays for a country.",
                "endpoint": "/tools/get_next_public_holidays",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country_code": country_schema,
                        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_ITEMS, "default": 8},
                    },
                    "required": ["country_code"],
                },
            },
            {
                "name": "get_long_weekends",
                "description": "List long weekends and bridge days for a country and year.",
                "endpoint": "/tools/get_long_weekends",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {"country_code": country_schema, "year": year_schema, "limit": limit_schema},
                    "required": ["country_code", "year"],
                },
            },
            {
                "name": "list_supported_countries",
                "description": "List countries supported by the public holidays API.",
                "endpoint": "/tools/list_supported_countries",
                "method": "POST",
                "parameters": {"type": "object", "properties": {}},
            },
        ],
    }


@app.post("/tools/get_public_holidays", response_model=ChatToolResponse)
async def get_public_holidays(request: HolidayRequest) -> ChatToolResponse:
    try:
        raw_holidays = await _request_json(f"/PublicHolidays/{request.year}/{request.country_code}")
        if not isinstance(raw_holidays, list) or not raw_holidays:
            return ChatToolResponse(error=f"no holidays returned for {request.country_code} in {request.year}")
        holidays = [item for item in raw_holidays if isinstance(item, dict)]
        if not holidays:
            return ChatToolResponse(error=f"no valid holidays returned for {request.country_code} in {request.year}")
        formatted_items = [_format_holiday(item) for item in holidays[: request.limit]]
        lines = [f"Public holidays for {request.country_code} in {request.year}:"]
        lines.extend(item for item in formatted_items if item)
        if len(holidays) > request.limit:
            lines.append(f"... {len(holidays) - request.limit} more")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"holiday lookup failed: {exc}")


@app.post("/tools/get_next_public_holidays", response_model=ChatToolResponse)
async def get_next_public_holidays(request: NextHolidayRequest) -> ChatToolResponse:
    try:
        raw_holidays = await _request_json(f"/NextPublicHolidays/{request.country_code}")
        if not isinstance(raw_holidays, list) or not raw_holidays:
            return ChatToolResponse(error=f"no upcoming holidays returned for {request.country_code}")
        holidays = [item for item in raw_holidays if isinstance(item, dict)]
        if not holidays:
            return ChatToolResponse(error=f"no valid upcoming holidays returned for {request.country_code}")
        formatted_items = [_format_holiday(item) for item in holidays[: request.limit]]
        lines = [f"Upcoming public holidays for {request.country_code}:"]
        lines.extend(item for item in formatted_items if item)
        if len(holidays) > request.limit:
            lines.append(f"... {len(holidays) - request.limit} more")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"upcoming holiday lookup failed: {exc}")


@app.post("/tools/get_long_weekends", response_model=ChatToolResponse)
async def get_long_weekends(request: LongWeekendRequest) -> ChatToolResponse:
    try:
        raw_weekends = await _request_json(f"/LongWeekend/{request.year}/{request.country_code}")
        if not isinstance(raw_weekends, list) or not raw_weekends:
            return ChatToolResponse(error=f"no long weekends returned for {request.country_code} in {request.year}")
        weekends = [item for item in raw_weekends if isinstance(item, dict)]
        if not weekends:
            return ChatToolResponse(error=f"no valid long weekends returned for {request.country_code} in {request.year}")
        formatted_items = [_format_long_weekend(item) for item in weekends[: request.limit]]
        lines = [f"Long weekends for {request.country_code} in {request.year}:"]
        lines.extend(item for item in formatted_items if item)
        if len(weekends) > request.limit:
            lines.append(f"... {len(weekends) - request.limit} more")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"long-weekend lookup failed: {exc}")


@app.post("/tools/list_supported_countries", response_model=ChatToolResponse)
async def list_supported_countries() -> ChatToolResponse:
    try:
        raw_countries = await _request_json("/AvailableCountries")
        if not isinstance(raw_countries, list) or not raw_countries:
            return ChatToolResponse(error="country list request returned no countries")
        countries = [item for item in raw_countries if isinstance(item, dict)]
        if not countries:
            return ChatToolResponse(error="country list request returned no valid countries")
        lines = ["Supported countries:"]
        for item in countries:
            code = item.get("countryCode", "")
            name = item.get("name", "")
            lines.append(f"- {code}: {name}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"country list request failed: {exc}")
