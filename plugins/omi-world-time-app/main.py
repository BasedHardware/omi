"""World Time, Timezone Conversion & Solar Ephemeris Integration App for Omi.

Provides real-time local time queries, international timezone conversion,
time differences, sunrise/sunset, and solar ephemeris for Omi AI wearable users.
Requires zero external authentication or API keys.
"""

from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import date as dt_date, datetime, time as dt_time, timedelta, timezone
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    CalculateTimeDifferenceRequest,
    ChatToolResponse,
    GetCurrentTimeRequest,
    GetSolarTimesRequest,
)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
SOLAR_URL = "https://api.sunrise-sunset.org/json"
REQUEST_TIMEOUT_SECONDS = 15.0
USER_AGENT = "omi-world-time-app/1.0 (https://omi.me)"


# ---------------------------------------------------------------------------
# In-Memory Bounded LRU Cache with TTL
# ---------------------------------------------------------------------------
class SimpleTTLCache:
    """Thread-safe, bounded LRU cache with expiration."""

    def __init__(self, maxsize: int = 512, ttl_seconds: int = 3600):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        created_at, value = self._cache[key]
        if time.time() - created_at > self.ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time(), value)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


geocoding_cache = SimpleTTLCache(maxsize=1024, ttl_seconds=86400)  # 24h
solar_cache = SimpleTTLCache(maxsize=1024, ttl_seconds=1800)       # 30m


# ---------------------------------------------------------------------------
# Common City-to-Timezone & Coordinates for Instant Zero-Latency Resolution
# ---------------------------------------------------------------------------
# Format: "alias": (display_name, iana_timezone, lat, lng, country)
CITY_PRESETS: Dict[str, Tuple[str, str, float, float, str]] = {
    "tokyo": ("Tokyo, Japan", "Asia/Tokyo", 35.6762, 139.6503, "Japan"),
    "japan": ("Tokyo, Japan", "Asia/Tokyo", 35.6762, 139.6503, "Japan"),
    "london": ("London, United Kingdom", "Europe/London", 51.5074, -0.1278, "United Kingdom"),
    "uk": ("London, United Kingdom", "Europe/London", 51.5074, -0.1278, "United Kingdom"),
    "paris": ("Paris, France", "Europe/Paris", 48.8566, 2.3522, "France"),
    "france": ("Paris, France", "Europe/Paris", 48.8566, 2.3522, "France"),
    "berlin": ("Berlin, Germany", "Europe/Berlin", 52.5200, 13.4050, "Germany"),
    "germany": ("Berlin, Germany", "Europe/Berlin", 52.5200, 13.4050, "Germany"),
    "rome": ("Rome, Italy", "Europe/Rome", 41.9028, 12.4964, "Italy"),
    "italy": ("Rome, Italy", "Europe/Rome", 41.9028, 12.4964, "Italy"),
    "madrid": ("Madrid, Spain", "Europe/Madrid", 40.4168, -3.7038, "Spain"),
    "spain": ("Madrid, Spain", "Europe/Madrid", 40.4168, -3.7038, "Spain"),
    "amsterdam": ("Amsterdam, Netherlands", "Europe/Amsterdam", 52.3676, 4.9041, "Netherlands"),
    "netherlands": ("Amsterdam, Netherlands", "Europe/Amsterdam", 52.3676, 4.9041, "Netherlands"),
    "brussels": ("Brussels, Belgium", "Europe/Brussels", 50.8503, 4.3517, "Belgium"),
    "vienna": ("Vienna, Austria", "Europe/Vienna", 48.2082, 16.3738, "Austria"),
    "zurich": ("Zurich, Switzerland", "Europe/Zurich", 47.3769, 8.5417, "Switzerland"),
    "switzerland": ("Zurich, Switzerland", "Europe/Zurich", 47.3769, 8.5417, "Switzerland"),
    "bucharest": ("Bucharest, Romania", "Europe/Bucharest", 44.4268, 26.1025, "Romania"),
    "romania": ("Bucharest, Romania", "Europe/Bucharest", 44.4268, 26.1025, "Romania"),
    "athens": ("Athens, Greece", "Europe/Athens", 37.9838, 23.7275, "Greece"),
    "greece": ("Athens, Greece", "Europe/Athens", 37.9838, 23.7275, "Greece"),
    "istanbul": ("Istanbul, Turkey", "Europe/Istanbul", 41.0082, 28.9784, "Turkey"),
    "turkey": ("Istanbul, Turkey", "Europe/Istanbul", 41.0082, 28.9784, "Turkey"),
    "new york": ("New York, NY, United States", "America/New_York", 40.7128, -74.0060, "United States"),
    "new york city": ("New York, NY, United States", "America/New_York", 40.7128, -74.0060, "United States"),
    "nyc": ("New York, NY, United States", "America/New_York", 40.7128, -74.0060, "United States"),
    "los angeles": ("Los Angeles, CA, United States", "America/Los_Angeles", 34.0522, -118.2437, "United States"),
    "la": ("Los Angeles, CA, United States", "America/Los_Angeles", 34.0522, -118.2437, "United States"),
    "san francisco": ("San Francisco, CA, United States", "America/Los_Angeles", 37.7749, -122.4194, "United States"),
    "sf": ("San Francisco, CA, United States", "America/Los_Angeles", 37.7749, -122.4194, "United States"),
    "seattle": ("Seattle, WA, United States", "America/Los_Angeles", 47.6062, -122.3321, "United States"),
    "chicago": ("Chicago, IL, United States", "America/Chicago", 41.8781, -87.6298, "United States"),
    "houston": ("Houston, TX, United States", "America/Chicago", 29.7604, -95.3698, "United States"),
    "dallas": ("Dallas, TX, United States", "America/Chicago", 32.7767, -96.7970, "United States"),
    "denver": ("Denver, CO, United States", "America/Denver", 39.7392, -104.9903, "United States"),
    "phoenix": ("Phoenix, AZ, United States", "America/Phoenix", 33.4484, -112.0740, "United States"),
    "miami": ("Miami, FL, United States", "America/New_York", 25.7617, -80.1918, "United States"),
    "toronto": ("Toronto, Canada", "America/Toronto", 43.6532, -79.3832, "Canada"),
    "vancouver": ("Vancouver, Canada", "America/Vancouver", 49.2827, -123.1207, "Canada"),
    "montreal": ("Montreal, Canada", "America/Toronto", 45.5017, -73.5673, "Canada"),
    "mexico city": ("Mexico City, Mexico", "America/Mexico_City", 19.4326, -99.1332, "Mexico"),
    "sao paulo": ("São Paulo, Brazil", "America/Sao_Paulo", -23.5505, -46.6333, "Brazil"),
    "buenos aires": ("Buenos Aires, Argentina", "America/Argentina/Buenos_Aires", -34.6037, -58.3816, "Argentina"),
    "sydney": ("Sydney, Australia", "Australia/Sydney", -33.8688, 151.2093, "Australia"),
    "melbourne": ("Melbourne, Australia", "Australia/Melbourne", -37.8136, 144.9631, "Australia"),
    "brisbane": ("Brisbane, Australia", "Australia/Brisbane", -27.4698, 153.0251, "Australia"),
    "perth": ("Perth, Australia", "Australia/Perth", -31.9505, 115.8605, "Australia"),
    "auckland": ("Auckland, New Zealand", "Pacific/Auckland", -36.8485, 174.7633, "New Zealand"),
    "singapore": ("Singapore", "Asia/Singapore", 1.3521, 103.8198, "Singapore"),
    "hong kong": ("Hong Kong", "Asia/Hong_Kong", 22.3193, 114.1694, "China"),
    "seoul": ("Seoul, South Korea", "Asia/Seoul", 37.5665, 126.9780, "South Korea"),
    "south korea": ("Seoul, South Korea", "Asia/Seoul", 37.5665, 126.9780, "South Korea"),
    "beijing": ("Beijing, China", "Asia/Shanghai", 39.9042, 116.4074, "China"),
    "shanghai": ("Shanghai, China", "Asia/Shanghai", 31.2304, 121.4737, "China"),
    "china": ("Shanghai, China", "Asia/Shanghai", 31.2304, 121.4737, "China"),
    "taipei": ("Taipei, Taiwan", "Asia/Taipei", 25.0330, 121.5654, "Taiwan"),
    "bangkok": ("Bangkok, Thailand", "Asia/Bangkok", 13.7563, 100.5018, "Thailand"),
    "jakarta": ("Jakarta, Indonesia", "Asia/Jakarta", -6.2088, 106.8456, "Indonesia"),
    "delhi": ("New Delhi, India", "Asia/Kolkata", 28.6139, 77.2090, "India"),
    "new delhi": ("New Delhi, India", "Asia/Kolkata", 28.6139, 77.2090, "India"),
    "mumbai": ("Mumbai, India", "Asia/Kolkata", 19.0760, 72.8777, "India"),
    "india": ("New Delhi, India", "Asia/Kolkata", 28.6139, 77.2090, "India"),
    "dubai": ("Dubai, UAE", "Asia/Dubai", 25.2048, 55.2708, "United Arab Emirates"),
    "uae": ("Dubai, UAE", "Asia/Dubai", 25.2048, 55.2708, "United Arab Emirates"),
    "cairo": ("Cairo, Egypt", "Africa/Cairo", 30.0444, 31.2357, "Egypt"),
    "egypt": ("Cairo, Egypt", "Africa/Cairo", 30.0444, 31.2357, "Egypt"),
    "johannesburg": ("Johannesburg, South Africa", "Africa/Johannesburg", -26.2041, 28.0473, "South Africa"),
    "south africa": ("Johannesburg, South Africa", "Africa/Johannesburg", -26.2041, 28.0473, "South Africa"),
    "nairobi": ("Nairobi, Kenya", "Africa/Nairobi", -1.2921, 36.8219, "Kenya"),
    "utc": ("UTC", "UTC", 0.0, 0.0, ""),
    "gmt": ("GMT (UTC)", "UTC", 0.0, 0.0, ""),
}

CITY_TIMEZONE_ALIASES: Dict[str, str] = {k: v[1] for k, v in CITY_PRESETS.items()}

_AVAILABLE_TZ = set(available_timezones())


# ---------------------------------------------------------------------------
# Lifespan & FastAPI App Definition
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi World Time & Solar Ephemeris Integration",
    description="Live world time, timezone conversion, time differences, and sunrise/sunset ephemeris for Omi AI wearables.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"Invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Geocoding & Timezone Resolution Helpers
# ---------------------------------------------------------------------------
def _find_iana_timezone(query: str) -> Optional[str]:
    """Check direct IANA timezone match case-insensitively."""
    cleaned = query.strip()
    if cleaned in _AVAILABLE_TZ:
        return cleaned

    cleaned_lower = cleaned.lower()
    for tz in _AVAILABLE_TZ:
        if tz.lower() == cleaned_lower:
            return tz
    return None


async def resolve_location(
    location_query: str,
    client: Optional[httpx.AsyncClient] = None,
    require_coordinates: bool = False,
) -> Tuple[str, str, float, float, str]:
    """Resolve a city or timezone query into (display_name, iana_timezone, lat, lng, country).

    Uses fast local presets/ZoneInfo first, falling back to Open-Meteo geocoding.
    """
    key = location_query.strip().lower()

    # Check cache (skip cache if coordinates are required but cache only has 0, 0)
    cached = geocoding_cache.get(key)
    if cached:
        if not (require_coordinates and cached[2] == 0.0 and cached[3] == 0.0):
            return cached

    # 1. Preset dictionary lookup
    if key in CITY_PRESETS:
        preset = CITY_PRESETS[key]
        if not require_coordinates or (preset[2] != 0.0 and preset[3] != 0.0):
            geocoding_cache.set(key, preset)
            return preset

    # 2. Direct IANA timezone
    direct_tz = _find_iana_timezone(location_query)
    if direct_tz:
        if not require_coordinates:
            display_name = direct_tz.split("/")[-1].replace("_", " ")
            res = (display_name, direct_tz, 0.0, 0.0, "")
            geocoding_cache.set(key, res)
            return res

    display_name = location_query.strip().title()

    # 3. Open-Meteo Geocoding API lookup
    if client is None:
        client = app.state.http_client

    try:
        resp = await client.get(
            GEOCODING_URL,
            params={"name": location_query.strip(), "count": 1, "language": "en"},
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results")
            if results and len(results) > 0:
                first = results[0]
                name = first.get("name", display_name)
                country = first.get("country", "")
                admin1 = first.get("admin1", "")
                lat = float(first.get("latitude", 0.0))
                lng = float(first.get("longitude", 0.0))
                geo_tz = first.get("timezone") or "UTC"

                parts = [name]
                if admin1 and admin1 != name:
                    parts.append(admin1)
                if country:
                    parts.append(country)
                formatted_name = ", ".join(parts)

                result = (formatted_name, geo_tz, lat, lng, country)
                geocoding_cache.set(key, result)
                return result
    except Exception:
        pass

    # Fallback to preset if coordinates were not strictly needed or geocoding failed
    if key in CITY_PRESETS and not require_coordinates:
        return CITY_PRESETS[key]

    raise ValueError(f"Could not resolve timezone or coordinates for location: '{location_query}'")


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------
def _format_utc_offset(dt: datetime) -> str:
    """Format UTC offset string, e.g. UTC+09:00 or UTC-05:00."""
    offset = dt.utcoffset()
    if offset is None:
        return "UTC+00:00"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _format_time_difference(diff_seconds: float) -> str:
    """Format difference between two offsets into human readable string."""
    abs_diff = abs(int(diff_seconds))
    hours = abs_diff // 3600
    minutes = (abs_diff % 3600) // 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes > 0:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    if not parts:
        return "the same time"
    return " and ".join(parts)


def _parse_source_time(time_str: str, base_date: dt_date) -> Tuple[dt_time, dt_date]:
    """Parse time string in various user formats (14:30, 2:30 PM, 2026-09-08 14:30)."""
    cleaned = time_str.strip()

    # Format 1: YYYY-MM-DD HH:MM[:SS]
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s](\d{1,2}):(\d{2})(?::(\d{2}))?$", cleaned)
    if date_match:
        d_str, h_str, m_str, s_str = date_match.groups()
        parsed_date = datetime.strptime(d_str, "%Y-%m-%d").date()
        hours, minutes, seconds = int(h_str), int(m_str), int(s_str or 0)
        if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            raise ValueError(f"Invalid time values in '{cleaned}'.")
        parsed_time = dt_time(hours, minutes, seconds)
        return parsed_time, parsed_date

    # Format 2: 12-hour AM/PM (e.g. "2:30 PM", "02:30pm")
    am_pm_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)$", cleaned, re.IGNORECASE)
    if am_pm_match:
        h, m, s, meridian = am_pm_match.groups()
        hours = int(h)
        minutes = int(m)
        seconds = int(s or 0)
        if not (1 <= hours <= 12):
            raise ValueError(f"12-hour time format requires hours between 1 and 12, got '{hours}'.")
        if not (0 <= minutes <= 59 and 0 <= seconds <= 59):
            raise ValueError(f"Invalid minutes or seconds in time '{cleaned}'.")
        if meridian.lower() == "pm" and hours < 12:
            hours += 12
        elif meridian.lower() == "am" and hours == 12:
            hours = 0
        return dt_time(hours, minutes, seconds), base_date

    # Format 3: 24-hour HH:MM[:SS] (e.g. "14:30", "09:00:00")
    h24_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", cleaned)
    if h24_match:
        h, m, s = h24_match.groups()
        hours, minutes, seconds = int(h), int(m), int(s or 0)
        if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds <= 59):
            raise ValueError(f"Invalid 24-hour time values in '{cleaned}'.")
        return dt_time(hours, minutes, seconds), base_date

    raise ValueError(f"Invalid time format: '{time_str}'. Please use HH:MM, HH:MM AM/PM, or YYYY-MM-DD HH:MM.")


def _resolve_aware_datetime(parsed_date: dt_date, parsed_time: dt_time, tz: ZoneInfo, loc_name: str) -> datetime:
    """Construct a timezone-aware datetime, rejecting DST gaps (nonexistent) and folds (ambiguous)."""
    dt0 = datetime.combine(parsed_date, parsed_time, tzinfo=tz).replace(fold=0)
    dt1 = datetime.combine(parsed_date, parsed_time, tzinfo=tz).replace(fold=1)

    # Check for nonexistent time (DST gap / spring forward, e.g. 2:30 AM skipped)
    dt_utc = dt0.astimezone(timezone.utc)
    dt_rt = dt_utc.astimezone(tz)
    if (dt_rt.date(), dt_rt.time()) != (parsed_date, parsed_time):
        raise ValueError(
            f"The local time {parsed_time.strftime('%H:%M')} on {parsed_date} does not exist in {loc_name} "
            f"due to daylight saving time transition (clocks spring forward)."
        )

    # Check for ambiguous time (DST fold / fall back, e.g. 1:30 AM occurs twice)
    if dt0.utcoffset() != dt1.utcoffset():
        raise ValueError(
            f"The local time {parsed_time.strftime('%H:%M')} on {parsed_date} is ambiguous in {loc_name} "
            f"due to daylight saving time transition (occurs twice)."
        )

    return dt0


# ---------------------------------------------------------------------------
# Tool Endpoints
# ---------------------------------------------------------------------------
@app.post("/tools/get_current_time", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_current_time(request: GetCurrentTimeRequest) -> ChatToolResponse:
    """Get the current time, date, timezone abbreviation, and UTC offset for any location."""
    try:
        display_name, tz_str, _, _, _ = await resolve_location(request.location)
        tz = ZoneInfo(tz_str)
        now_local = datetime.now(tz)

        time_12h = now_local.strftime("%I:%M:%S %p")
        time_24h = now_local.strftime("%H:%M:%S")
        date_str = now_local.strftime("%A, %B %d, %Y")
        tz_abbr = now_local.tzname() or tz_str
        utc_offset = _format_utc_offset(now_local)
        dst_active = bool(now_local.dst() and now_local.dst().total_seconds() != 0)

        result_text = (
            f"Current time in {display_name} ({tz_str}):\n"
            f"• Local Time: {time_12h} ({time_24h})\n"
            f"• Date: {date_str}\n"
            f"• Timezone: {tz_abbr} ({utc_offset})\n"
            f"• Daylight Saving Time (DST): {'Active' if dst_active else 'Inactive'}"
        )
        return ChatToolResponse(result=result_text)
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to get time for '{request.location}': {exc}")


@app.post("/tools/calculate_time_difference", response_model=ChatToolResponse, response_model_exclude_none=True)
async def calculate_time_difference(request: CalculateTimeDifferenceRequest) -> ChatToolResponse:
    """Convert time or calculate the exact time difference between two locations."""
    try:
        src_name, src_tz_str, _, _, _ = await resolve_location(request.source_location)
        tgt_name, tgt_tz_str, _, _, _ = await resolve_location(request.target_location)

        src_tz = ZoneInfo(src_tz_str)
        tgt_tz = ZoneInfo(tgt_tz_str)

        now_src = datetime.now(src_tz)
        if request.source_time:
            parsed_time, parsed_date = _parse_source_time(request.source_time, now_src.date())
            src_dt = _resolve_aware_datetime(parsed_date, parsed_time, src_tz, src_name)
        else:
            src_dt = now_src

        # Convert to target timezone
        tgt_dt = src_dt.astimezone(tgt_tz)

        # Offsets difference
        src_offset = src_dt.utcoffset() or timedelta()
        tgt_offset = tgt_dt.utcoffset() or timedelta()
        diff_seconds = tgt_offset.total_seconds() - src_offset.total_seconds()

        diff_str = _format_time_difference(diff_seconds)
        if diff_seconds > 0:
            rel_str = f"{tgt_name} is {diff_str} ahead of {src_name}"
        elif diff_seconds < 0:
            rel_str = f"{tgt_name} is {diff_str} behind {src_name}"
        else:
            rel_str = f"{tgt_name} is in the same time zone as {src_name}"

        # Calendar day difference
        day_diff = (tgt_dt.date() - src_dt.date()).days
        if day_diff == 1:
            day_note = " (+1 day, tomorrow)"
        elif day_diff > 1:
            day_note = f" (+{day_diff} days, in {day_diff} days)"
        elif day_diff == -1:
            day_note = " (-1 day, yesterday)"
        elif day_diff < -1:
            day_note = f" ({day_diff} days, {abs(day_diff)} days earlier)"
        else:
            day_note = " (same calendar day)"

        result_text = (
            f"Time Comparison:\n"
            f"• Difference: {rel_str}\n"
            f"• {src_name}: {src_dt.strftime('%I:%M %p')} ({src_dt.strftime('%H:%M')}) {src_dt.tzname()} on {src_dt.strftime('%A, %b %d, %Y')}\n"
            f"• {tgt_name}: {tgt_dt.strftime('%I:%M %p')} ({tgt_dt.strftime('%H:%M')}) {tgt_dt.tzname()} on {tgt_dt.strftime('%A, %b %d, %Y')}{day_note}"
        )
        return ChatToolResponse(result=result_text)
    except Exception as exc:
        return ChatToolResponse(
            error=f"Failed to calculate time difference between '{request.source_location}' and '{request.target_location}': {exc}"
        )


@app.post("/tools/get_solar_times", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_solar_times(request: GetSolarTimesRequest) -> ChatToolResponse:
    """Get sunrise, sunset, solar noon, day length, and twilight times for any location."""
    client: httpx.AsyncClient = app.state.http_client
    try:
        display_name, tz_str, lat, lng, _ = await resolve_location(
            request.location, client, require_coordinates=True
        )
        if lat == 0.0 and lng == 0.0:
            raise ValueError(f"Geographic coordinates required for solar ephemeris calculation for '{request.location}'.")

        tz = ZoneInfo(tz_str)
        target_date_str = request.date.strip() if request.date else datetime.now(tz).strftime("%Y-%m-%d")

        # Validate date format
        dt_date.fromisoformat(target_date_str)

        cache_key = f"solar:{lat:.3f}:{lng:.3f}:{target_date_str}"
        solar_data = solar_cache.get(cache_key)

        if not solar_data:
            params = {"lat": lat, "lng": lng, "date": target_date_str, "formatted": 0}
            resp = await client.get(SOLAR_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK":
                raise ValueError(f"Sunrise-Sunset API error: {data.get('status')}")
            solar_data = data["results"]
            solar_cache.set(cache_key, solar_data)

        def _to_local(iso_utc: Optional[str]) -> str:
            if not iso_utc:
                return "N/A"
            dt_utc = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
            dt_loc = dt_utc.astimezone(tz)
            return dt_loc.strftime("%I:%M %p %Z")

        sunrise_loc = _to_local(solar_data.get("sunrise"))
        sunset_loc = _to_local(solar_data.get("sunset"))
        solar_noon_loc = _to_local(solar_data.get("solar_noon"))
        dawn_loc = _to_local(solar_data.get("civil_twilight_begin"))
        dusk_loc = _to_local(solar_data.get("civil_twilight_end"))

        day_length_sec = solar_data.get("day_length", 0)
        day_h = day_length_sec // 3600
        day_m = (day_length_sec % 3600) // 60

        result_text = (
            f"Solar Ephemeris for {display_name} on {target_date_str}:\n"
            f"• Sunrise: {sunrise_loc}\n"
            f"• Sunset: {sunset_loc}\n"
            f"• Solar Noon: {solar_noon_loc}\n"
            f"• Day Length: {day_h}h {day_m:02d}m\n"
            f"• Dawn (First Light): {dawn_loc}\n"
            f"• Dusk (Last Light): {dusk_loc}"
        )
        return ChatToolResponse(result=result_text)
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to get solar times for '{request.location}': {exc}")


# ---------------------------------------------------------------------------
# Health & Manifest Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "service": "omi-world-time-app", "version": "1.0.0"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> Dict[str, Any]:
    """Omi Function Calling Chat Tools Manifest."""
    return {
        "schema_version": "1.0",
        "auth": {"type": "none"},
        "tools": [
            {
                "name": "get_current_time",
                "description": "Get the current time, date, day of week, UTC offset, and timezone for any city, country, or timezone.",
                "endpoint": "/tools/get_current_time",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name (e.g. 'Tokyo', 'London', 'New York') or IANA timezone (e.g. 'Asia/Tokyo', 'UTC').",
                        }
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "calculate_time_difference",
                "description": "Convert time between two cities/timezones or calculate the exact time difference in hours and minutes.",
                "endpoint": "/tools/calculate_time_difference",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_location": {
                            "type": "string",
                            "description": "Source city or timezone (e.g. 'New York', 'America/New_York').",
                        },
                        "target_location": {
                            "type": "string",
                            "description": "Target city or timezone (e.g. 'Tokyo', 'Asia/Tokyo').",
                        },
                        "source_time": {
                            "type": "string",
                            "description": "Optional time in HH:MM or ISO format to convert. Defaults to current time if omitted.",
                        },
                    },
                    "required": ["source_location", "target_location"],
                },
            },
            {
                "name": "get_solar_times",
                "description": "Get sunrise, sunset, solar noon, day length, and twilight (first light / last light) for any location and date.",
                "endpoint": "/tools/get_solar_times",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name or location (e.g. 'Paris', 'San Francisco', 'Sydney').",
                        },
                        "date": {
                            "type": "string",
                            "description": "Optional date in YYYY-MM-DD format. Defaults to today.",
                        },
                    },
                    "required": ["location"],
                },
            },
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Service landing page and API summary."""
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Omi World Time & Solar Ephemeris Integration</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 48px auto; padding: 0 16px; line-height: 1.6; color: #24292f; }
                h1 { font-size: 24px; color: #0969da; }
                code { background: #f6f8fa; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
                pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
                ul { padding-left: 20px; }
            </style>
        </head>
        <body>
            <h1>🌍 Omi World Time & Solar Ephemeris App</h1>
            <p>Standalone, unauthenticated chat tools integration for the Omi AI ecosystem.</p>
            <h3>Registered Chat Tools:</h3>
            <ul>
                <li><code>get_current_time</code>: Current time, date, UTC offset, and DST status.</li>
                <li><code>calculate_time_difference</code>: Timezone conversion and difference between global locations.</li>
                <li><code>get_solar_times</code>: Sunrise, sunset, day length, and twilight ephemeris.</li>
            </ul>
            <h3>Endpoints:</h3>
            <ul>
                <li><a href="/health"><code>GET /health</code></a>: Health check</li>
                <li><a href="/.well-known/omi-tools.json"><code>GET /.well-known/omi-tools.json</code></a>: Chat tools manifest</li>
            </ul>
        </body>
        </html>
        """
    )
