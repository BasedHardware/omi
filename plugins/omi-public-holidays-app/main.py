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

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return _normalize_country_code(value)


class NextHolidayRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    limit: int = Field(default=8, ge=1, le=MAX_ITEMS)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return _normalize_country_code(value)


class LongWeekendRequest(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    year: int = Field(..., ge=1970, le=2100)
    limit: int = Field(default=MAX_ITEMS, ge=1, le=MAX_ITEMS)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return _normalize_country_code(value)


def _normalize_country_code(value: str) -> str:
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


def _format_holiday(holiday: dict[str, Any]) -> str:
    regional = "global" if holiday.get("global") else _format_list(holiday.get("counties"))
    types = ", ".join(holiday.get("types") or [])
    type_text = f"; {types}" if types else ""
    local_name = holiday.get("localName")
    name = holiday.get("name")
    display_name = name if name == local_name or not local_name else f"{name} / {local_name}"
    return f"- {holiday.get('date')}: {display_name} ({regional}{type_text})"


def _format_long_weekend(item: dict[str, Any]) -> str:
    raw_bridge_days = item.get("bridgeDays")
    bridge_days = raw_bridge_days if isinstance(raw_bridge_days, list) else []
    if bridge_days:
        bridge_text = f"; bridge day: {', '.join(bridge_days)}"
    elif item.get("needBridgeDay"):
        bridge_text = "; bridge day needed"
    else:
        bridge_text = "; no bridge day needed"
    return f"- {item.get('startDate')} to {item.get('endDate')}: {item.get('dayCount')} days{bridge_text}"


async def _request_json(path: str) -> Any:
    client: httpx.AsyncClient = app.state.http_client
    response = await client.get(f"{NAGER_BASE_URL}{path}")
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
        holidays = await _request_json(f"/PublicHolidays/{request.year}/{request.country_code}")
        if not holidays:
            return ChatToolResponse(error=f"no holidays returned for {request.country_code} in {request.year}")
        lines = [f"Public holidays for {request.country_code} in {request.year}:"]
        lines.extend(_format_holiday(item) for item in holidays[: request.limit])
        if len(holidays) > request.limit:
            lines.append(f"... {len(holidays) - request.limit} more")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"holiday lookup failed: {exc}")


@app.post("/tools/get_next_public_holidays", response_model=ChatToolResponse)
async def get_next_public_holidays(request: NextHolidayRequest) -> ChatToolResponse:
    try:
        holidays = await _request_json(f"/NextPublicHolidays/{request.country_code}")
        if not holidays:
            return ChatToolResponse(error=f"no upcoming holidays returned for {request.country_code}")
        lines = [f"Upcoming public holidays for {request.country_code}:"]
        lines.extend(_format_holiday(item) for item in holidays[: request.limit])
        if len(holidays) > request.limit:
            lines.append(f"... {len(holidays) - request.limit} more")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"upcoming holiday lookup failed: {exc}")


@app.post("/tools/get_long_weekends", response_model=ChatToolResponse)
async def get_long_weekends(request: LongWeekendRequest) -> ChatToolResponse:
    try:
        weekends = await _request_json(f"/LongWeekend/{request.year}/{request.country_code}")
        if not weekends:
            return ChatToolResponse(error=f"no long weekends returned for {request.country_code} in {request.year}")
        lines = [f"Long weekends for {request.country_code} in {request.year}:"]
        lines.extend(_format_long_weekend(item) for item in weekends[: request.limit])
        if len(weekends) > request.limit:
            lines.append(f"... {len(weekends) - request.limit} more")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"long-weekend lookup failed: {exc}")


@app.post("/tools/list_supported_countries", response_model=ChatToolResponse)
async def list_supported_countries() -> ChatToolResponse:
    try:
        countries = await _request_json("/AvailableCountries")
        if not isinstance(countries, list) or not countries:
            return ChatToolResponse(error="country list request returned no countries")
        lines = ["Supported countries:"]
        for item in countries:
            lines.append(f"- {item.get('countryCode')}: {item.get('name')}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"country list request failed: {exc}")
