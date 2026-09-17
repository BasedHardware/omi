"""
Open-Meteo Integration App for Omi.

Provides chat tools for current weather, short forecasts, and basic air-quality
lookups using public Open-Meteo APIs.
"""

from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
REQUEST_TIMEOUT_SECONDS = 10
MAX_FORECAST_DAYS = 7


app = FastAPI(
    title="Omi Open-Meteo Integration",
    description="Get current weather, short forecasts, and air quality from Omi chat tools",
    version="1.0.0",
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class CurrentWeatherRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=120)
    temperature_unit: Literal["celsius", "fahrenheit"] = "celsius"


class ForecastRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=120)
    days: int = Field(default=3, ge=1, le=MAX_FORECAST_DAYS)
    temperature_unit: Literal["celsius", "fahrenheit"] = "celsius"


class AirQualityRequest(BaseModel):
    location: str = Field(..., min_length=1, max_length=120)


def _clean_location(value: str) -> str:
    return " ".join(value.strip().split())


def _format_number(value: Any, suffix: str = "") -> str:
    if value is None or isinstance(value, bool):
        return "n/a"
    clean_suffix = str(suffix) if suffix is not None else ""
    if isinstance(value, float):
        rounded = round(value, 1)
        if rounded.is_integer():
            return f"{int(rounded)}{clean_suffix}"
        return f"{rounded}{clean_suffix}"
    return f"{value}{clean_suffix}"


def _safe_item(items: Any, index: int, default: Any = None) -> Any:
    """Safely index a sequence without raising IndexError or TypeError."""
    if isinstance(items, (list, tuple)) and 0 <= index < len(items):
        return items[index]
    return default


def _format_unit_suffix(unit_val: Any, prefix: str = "") -> str:
    """Safely format a unit suffix, avoiding TypeError if unit_val is None or non-string."""
    if not unit_val or not isinstance(unit_val, str):
        return ""
    return f"{prefix}{unit_val}"


def _format_weather_code(code: Optional[int]) -> str:
    if code is None:
        return "unknown"

    descriptions = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "depositing rime fog",
        51: "light drizzle",
        53: "moderate drizzle",
        55: "dense drizzle",
        56: "light freezing drizzle",
        57: "dense freezing drizzle",
        61: "slight rain",
        63: "moderate rain",
        65: "heavy rain",
        66: "light freezing rain",
        67: "heavy freezing rain",
        71: "slight snow fall",
        73: "moderate snow fall",
        75: "heavy snow fall",
        77: "snow grains",
        80: "slight rain showers",
        81: "moderate rain showers",
        82: "violent rain showers",
        85: "slight snow showers",
        86: "heavy snow showers",
        95: "thunderstorm",
        96: "thunderstorm with slight hail",
        99: "thunderstorm with heavy hail",
    }
    return descriptions.get(code, f"weather code {code}")


def _format_observed_at(current: dict[str, Any], payload: dict[str, Any]) -> str:
    """Render the observation time with the response timezone/offset when present."""
    observed = current.get("time") or "unknown time"
    # Keep prior minute-precision normalization for display consistency.
    if observed != "unknown time":
        try:
            from datetime import datetime

            observed = datetime.fromisoformat(str(observed)).isoformat(timespec="minutes")
        except ValueError:
            pass
    tz = payload.get("timezone") or ""
    offset = payload.get("utc_offset_seconds")
    suffix_parts = []
    if tz:
        suffix_parts.append(tz)
    if offset is not None:
        try:
            total_minutes = int(round(int(offset) / 60))
            sign = "+" if total_minutes >= 0 else "-"
            total_minutes = abs(total_minutes)
            whole, minutes = divmod(total_minutes, 60)
            suffix_parts.append(f"UTC{sign}{whole:02d}:{minutes:02d}")
        except (TypeError, ValueError):
            pass
    if suffix_parts:
        return f"{observed} ({', '.join(suffix_parts)})"
    return observed


def _format_place(place: dict[str, Any]) -> str:
    parts = [place.get("name")]
    admin = place.get("admin1")
    country = place.get("country")
    if admin and admin != place.get("name"):
        parts.append(admin)
    if country:
        parts.append(country)
    return ", ".join(part for part in parts if part)


async def _resolve_location(client: httpx.AsyncClient, location: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    cleaned = _clean_location(location)
    if not cleaned:
        return None, "location is required"

    response = await client.get(
        GEOCODING_URL,
        params={"name": cleaned, "count": 1, "language": "en", "format": "json"},
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") or []
    if not results:
        return None, f"no Open-Meteo geocoding result for '{cleaned}'"
    return results[0], None


async def _request_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi Open-Meteo Integration</title></head>
      <body>
        <h1>Omi Open-Meteo Integration</h1>
        <p>Use Omi chat tools to check weather, forecasts, and air quality.</p>
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
        "name": "Open-Meteo",
        "description": "Check current weather, short forecasts, and basic air quality from Omi.",
        "tools": [
            {
                "name": "get_current_weather",
                "description": "Get current weather for a place.",
                "endpoint": "/tools/get_current_weather",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City, address, or place name, such as 'San Francisco'.",
                        },
                        "temperature_unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "default": "celsius",
                        },
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "get_weather_forecast",
                "description": "Get a daily weather forecast for the next 1-7 days.",
                "endpoint": "/tools/get_weather_forecast",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"},
                        "days": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
                        "temperature_unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "default": "celsius",
                        },
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "get_air_quality",
                "description": "Get current air-quality readings for a place.",
                "endpoint": "/tools/get_air_quality",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        ],
    }


@app.post("/tools/get_current_weather", response_model=ChatToolResponse)
async def get_current_weather(request: CurrentWeatherRequest) -> ChatToolResponse:
    unit = request.temperature_unit

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            place, error = await _resolve_location(client, request.location)
            if error:
                return ChatToolResponse(error=error)

            payload = await _request_json(
                client,
                FORECAST_URL,
                {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "apparent_temperature",
                        "precipitation",
                        "weather_code",
                        "wind_speed_10m",
                    ],
                    "temperature_unit": unit,
                    "wind_speed_unit": "mph" if unit == "fahrenheit" else "kmh",
                    "timezone": "auto",
                },
            )

        current = payload.get("current") or {}
        units = payload.get("current_units") or {}
        place_name = _format_place(place)
        condition = _format_weather_code(current.get("weather_code"))
        observed_at = _format_observed_at(current, payload)

        wind_suffix = _format_unit_suffix(units.get("wind_speed_10m"), " ")
        temp_suffix = str(units.get("temperature_2m") or "")
        apparent_temp_suffix = str(units.get("apparent_temperature") or "")
        humidity_suffix = str(units.get("relative_humidity_2m") or "")
        precip_suffix = str(units.get("precipitation") or "")

        lines = [
            f"Current weather for {place_name}",
            f"Observed: {observed_at}",
            f"Condition: {condition}",
            f"Temperature: {_format_number(current.get('temperature_2m'), temp_suffix)}",
            f"Feels like: {_format_number(current.get('apparent_temperature'), apparent_temp_suffix)}",
            f"Humidity: {_format_number(current.get('relative_humidity_2m'), humidity_suffix)}",
            f"Precipitation: {_format_number(current.get('precipitation'), precip_suffix)}",
            f"Wind: {_format_number(current.get('wind_speed_10m'), wind_suffix)}",
        ]
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Open-Meteo request failed: {exc}")


@app.post("/tools/get_weather_forecast", response_model=ChatToolResponse)
async def get_weather_forecast(request: ForecastRequest) -> ChatToolResponse:
    unit = request.temperature_unit
    days = request.days

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            place, error = await _resolve_location(client, request.location)
            if error:
                return ChatToolResponse(error=error)

            payload = await _request_json(
                client,
                FORECAST_URL,
                {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "daily": [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                        "wind_speed_10m_max",
                    ],
                    "temperature_unit": unit,
                    "wind_speed_unit": "mph" if unit == "fahrenheit" else "kmh",
                    "timezone": "auto",
                    "forecast_days": days,
                },
            )

        daily = payload.get("daily") or {}
        units = payload.get("daily_units") or {}
        place_name = _format_place(place)

        time_list = daily.get("time") or []
        if not time_list:
            return ChatToolResponse(result=f"No forecast data available for {place_name}.")

        lines = [f"{days}-day forecast for {place_name}"]
        temp_max_suffix = str(units.get("temperature_2m_max") or "")
        temp_min_suffix = str(units.get("temperature_2m_min") or "")
        precip_suffix = str(units.get("precipitation_probability_max") or "%")
        wind_suffix = _format_unit_suffix(units.get("wind_speed_10m_max"), " ")

        for index, day in enumerate(time_list[:days]):
            condition = _format_weather_code(_safe_item(daily.get("weather_code"), index))
            high = _format_number(_safe_item(daily.get("temperature_2m_max"), index), temp_max_suffix)
            low = _format_number(_safe_item(daily.get("temperature_2m_min"), index), temp_min_suffix)
            rain = _format_number(_safe_item(daily.get("precipitation_probability_max"), index), precip_suffix)
            wind = _format_number(_safe_item(daily.get("wind_speed_10m_max"), index), wind_suffix)
            lines.append(f"- {day}: {condition}; high {high}, low {low}; rain {rain}; wind up to {wind}")

        return ChatToolResponse(result="\n".join(lines))
    except (httpx.HTTPError, IndexError) as exc:
        return ChatToolResponse(error=f"Open-Meteo forecast request failed: {exc}")


@app.post("/tools/get_air_quality", response_model=ChatToolResponse)
async def get_air_quality(request: AirQualityRequest) -> ChatToolResponse:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            place, error = await _resolve_location(client, request.location)
            if error:
                return ChatToolResponse(error=error)

            payload = await _request_json(
                client,
                AIR_QUALITY_URL,
                {
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": ["pm2_5", "pm10", "ozone", "nitrogen_dioxide", "us_aqi"],
                    "timezone": "auto",
                },
            )

        current = payload.get("current") or {}
        units = payload.get("current_units") or {}
        place_name = _format_place(place)
        observed_at = _format_observed_at(current, payload)

        pm25_suffix = _format_unit_suffix(units.get("pm2_5"), " ")
        pm10_suffix = _format_unit_suffix(units.get("pm10"), " ")
        ozone_suffix = _format_unit_suffix(units.get("ozone"), " ")
        no2_suffix = _format_unit_suffix(units.get("nitrogen_dioxide"), " ")

        lines = [
            f"Air quality for {place_name}",
            f"Observed: {observed_at}",
            f"US AQI: {_format_number(current.get('us_aqi'))}",
            f"PM2.5: {_format_number(current.get('pm2_5'), pm25_suffix)}",
            f"PM10: {_format_number(current.get('pm10'), pm10_suffix)}",
            f"Ozone: {_format_number(current.get('ozone'), ozone_suffix)}",
            f"Nitrogen dioxide: {_format_number(current.get('nitrogen_dioxide'), no2_suffix)}",
        ]
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Open-Meteo air-quality request failed: {exc}")
