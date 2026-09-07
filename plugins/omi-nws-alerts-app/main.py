"""National Weather Service (NWS / NOAA) Severe Weather & Safety Hazards Omi Integration Plugin.

Provides real-time local, state, and national weather warnings, severe storm tracking,
tornado/flood alerts, and protective safety instructions for Omi wearable AI devices.
"""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import copy
from datetime import datetime
import ipaddress
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
import httpx

from models import (
    ChatToolResponse,
    LocationAlertRequest,
    NationalSummaryRequest,
    StateAlertRequest,
    US_STATES_MAP,
    WeatherAlertItem,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omi-nws-alerts-app")

NWS_API_BASE_URL = os.getenv("NWS_API_BASE_URL", "https://api.weather.gov")
NWS_USER_AGENT = os.getenv(
    "NWS_USER_AGENT",
    "(OmiNwsAlertsApp/1.0, contact: team@basedhardware.com)",
)
REQUEST_TIMEOUT = float(os.getenv("NWS_REQUEST_TIMEOUT", "10.0"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = float(os.getenv("RATE_LIMIT_WINDOW", "60.0"))
MAX_RATE_LIMITER_KEYS = int(os.getenv("MAX_RATE_LIMITER_KEYS", "5000"))
TRUSTED_PROXIES = set(
    ip.strip()
    for ip in os.getenv(
        "TRUSTED_PROXIES",
        "127.0.0.1,::1,testclient",
    ).split(",")
    if ip.strip()
)


class LRUCache:
    """Bounded in-memory LRU cache with TTL expiration and deep-copy mutation isolation."""

    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self.max_size = max_size
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        expires_at, value = self._cache[key]
        if time.time() > expires_at:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return copy.deepcopy(value)

    def set(self, key: str, value: Any, ttl_seconds: float = 120.0) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (time.time() + ttl_seconds, copy.deepcopy(value))
        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


cache = LRUCache()


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter per client IP."""

    def __init__(
        self,
        requests_per_window: int = RATE_LIMIT_REQUESTS,
        window_seconds: float = RATE_LIMIT_WINDOW,
        max_keys: int = MAX_RATE_LIMITER_KEYS,
    ):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._records: OrderedDict[str, List[float]] = OrderedDict()

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        if client_ip in self._records:
            self._records.move_to_end(client_ip)
            self._records[client_ip] = [
                ts for ts in self._records[client_ip] if ts > cutoff
            ]
        else:
            if len(self._records) >= self.max_keys:
                self._records.popitem(last=False)
            self._records[client_ip] = []

        if len(self._records[client_ip]) >= self.requests_per_window:
            return False

        self._records[client_ip].append(now)
        return True


rate_limiter = SlidingWindowRateLimiter()


def is_trusted_proxy(ip_str: str) -> bool:
    """Check if direct connection host matches trusted proxy configuration."""
    if not ip_str or ip_str == "unknown":
        return False
    if ip_str in TRUSTED_PROXIES or "*" in TRUSTED_PROXIES:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for entry in TRUSTED_PROXIES:
            try:
                if "/" in entry and ip_obj in ipaddress.ip_network(entry, strict=False):
                    return True
            except ValueError:
                continue
        return False
    except ValueError:
        return False


def get_client_ip(request: Request) -> str:
    """Safely extracts client IP, only trusting X-Forwarded-For if forwarded by trusted proxy."""
    direct_ip = request.client.host if request.client else "unknown"
    if is_trusted_proxy(direct_ip):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
            if ips:
                return ips[0]
    return direct_ip


def rate_limit_dependency(request: Request) -> None:
    client_ip = get_client_ip(request)
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per minute.",
        )


http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Returns the active AsyncClient, lazily creating one if not yet initialized."""
    global http_client
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": NWS_USER_AGENT,
                "Accept": "application/geo+json",
            },
        )
    return http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    owns_client = False
    if http_client is None or http_client.is_closed:
        http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": NWS_USER_AGENT,
                "Accept": "application/geo+json",
            },
        )
        owns_client = True
        logger.info("Initialized NWS API HTTP client.")
    yield
    if owns_client and http_client and not http_client.is_closed:
        await http_client.aclose()
        http_client = None
        logger.info("Closed NWS API HTTP client.")


app = FastAPI(
    title="Omi National Weather Service (NWS) Severe Weather Alerts Plugin",
    description="Official NOAA/NWS real-time severe weather warnings, storm tracking, tornado/flood advisories, and life-safety instructions for Omi wearable devices.",
    version="1.0.0",
    lifespan=lifespan,
)


def get_event_emoji(event_name: str) -> str:
    """Returns a context-appropriate warning emoji based on the meteorological hazard type."""
    ev = event_name.lower()
    if "tornado" in ev:
        return "🌪️"
    if "flood" in ev:
        return "🌊"
    if "thunderstorm" in ev or "lightning" in ev:
        return "⛈️"
    if any(w in ev for w in ["blizzard", "winter", "snow", "ice", "freeze", "frost"]):
        return "❄️"
    if any(w in ev for w in ["fire", "red flag", "smoke"]):
        return "🔥"
    if any(w in ev for w in ["hurricane", "tropical", "typhoon"]):
        return "🌀"
    if "heat" in ev:
        return "🌡️"
    if any(w in ev for w in ["wind", "gale", "high surf", "marine"]):
        return "💨"
    return "⚠️"


def parse_alert_feature(feat: Dict[str, Any]) -> Optional[WeatherAlertItem]:
    """Parses a GeoJSON feature from api.weather.gov into a typed WeatherAlertItem."""
    props = feat.get("properties", {})
    if not props:
        return None

    onset_dt = None
    onset_raw = props.get("onset")
    if onset_raw:
        try:
            onset_dt = datetime.fromisoformat(onset_raw)
        except (ValueError, TypeError):
            onset_dt = None

    expires_dt = None
    expires_raw = props.get("expires")
    if expires_raw:
        try:
            expires_dt = datetime.fromisoformat(expires_raw)
        except (ValueError, TypeError):
            expires_dt = None

    return WeatherAlertItem(
        id=props.get("id") or feat.get("id") or "unknown",
        event=props.get("event") or "Weather Hazard",
        severity=props.get("severity") or "Unknown",
        urgency=props.get("urgency") or "Unknown",
        certainty=props.get("certainty") or "Unknown",
        headline=props.get("headline")
        or props.get("event")
        or "Active Weather Warning",
        description=props.get("description"),
        instruction=props.get("instruction"),
        onset=onset_dt,
        expires=expires_dt,
        area_desc=props.get("areaDesc"),
        sender_name=props.get("senderName"),
    )


def format_alert_card(alert: WeatherAlertItem) -> str:
    """Formats a single WeatherAlertItem into a voice-friendly, rich markdown section."""
    emoji = get_event_emoji(alert.event)
    severity_badge = f"**[{alert.severity.upper()}]**"
    urgency_badge = f"**Urgency:** {alert.urgency}"

    lines = [
        f"### {emoji} {alert.event} {severity_badge}",
        f"📢 **Headline:** {alert.headline.strip()}",
        f"⚡ {urgency_badge} | **Certainty:** {alert.certainty}",
    ]

    if alert.area_desc:
        # Truncate area list if excessively long
        areas = alert.area_desc.strip()
        if len(areas) > 160:
            areas = areas[:157] + "..."
        lines.append(f"📍 **Affected Areas:** {areas}")

    if alert.expires:
        lines.append(f"⏳ **Expires:** {alert.expires.strftime('%Y-%m-%d %H:%M %Z')}")

    if alert.instruction:
        inst = alert.instruction.strip().replace("\n\n", " ").replace("\n", " ")
        if len(inst) > 350:
            cutoff = inst[:347].rfind(" ")
            inst = inst[:cutoff] + "..." if cutoff > 0 else inst[:347] + "..."
        lines.append(f"🛡️ **Protective Action:** {inst}")
    elif alert.description:
        desc = alert.description.strip().replace("\n\n", " ").replace("\n", " ")
        if len(desc) > 250:
            cutoff = desc[:247].rfind(" ")
            desc = desc[:cutoff] + "..." if cutoff > 0 else desc[:247] + "..."
        lines.append(f"ℹ️ **Details:** {desc}")

    return "\n".join(lines)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "online",
        "service": "Omi National Weather Service (NWS) Severe Weather Alerts Plugin",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "tools_manifest": "/.well-known/omi-tools.json",
            "alerts_by_location": "/tools/get-active-alerts-by-location",
            "alerts_by_state": "/tools/get-active-alerts-by-state",
            "national_summary": "/tools/get-national-severe-weather-summary",
        },
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint with cached probe to NWS active alert counts."""
    cached_status = cache.get("health_upstream_status")

    if cached_status is None:
        upstream_ok = False
        client = get_http_client()
        try:
            resp = await client.get(
                f"{NWS_API_BASE_URL}/alerts/active/count",
                timeout=3.5,
            )
            upstream_ok = resp.status_code == 200
        except Exception as e:
            logger.warning("NWS upstream health probe failed: %s", e)
        cached_status = upstream_ok
        cache.set("health_upstream_status", upstream_ok, ttl_seconds=60.0)

    return {
        "status": "healthy" if cached_status else "degraded",
        "upstream_nws_api": "reachable" if cached_status else "unreachable",
        "cached_entries": cache.size(),
        "timestamp": time.time(),
    }


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest() -> Dict[str, Any]:
    """Exposes Omi function calling tools manifest for NWS Weather Alerts."""
    return {
        "schema_version": "1.0",
        "name": "National Weather Service (NWS) Severe Weather Alerts",
        "description": "Official NOAA/NWS real-time severe storm warnings, tornado/flood advisories, and life-safety instructions for wearable voice devices.",
        "tools": [
            {
                "name": "get_active_alerts_by_location",
                "description": "Check for active severe weather warnings, tornado watches, flood alerts, or advisories for a specific GPS location (latitude, longitude).",
                "endpoint": "/tools/get-active-alerts-by-location",
                "method": "POST",
                "auth_required": False,
                "status_message": "Checking active NWS severe weather alerts for your coordinates...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "WGS84 latitude of the user's location (e.g. 32.7767 for Dallas, TX).",
                        },
                        "longitude": {
                            "type": "number",
                            "description": "WGS84 longitude of the user's location (e.g. -96.7970 for Dallas, TX).",
                        },
                        "severity": {
                            "type": "string",
                            "description": "Optional minimum severity filter ('Extreme', 'Severe', 'Moderate', 'Minor').",
                        },
                    },
                    "required": ["latitude", "longitude"],
                },
            },
            {
                "name": "get_active_alerts_by_state",
                "description": "Get all active severe weather warnings, watches, and advisories for any US state (e.g. 'TX', 'CA', 'Florida').",
                "endpoint": "/tools/get-active-alerts-by-state",
                "method": "POST",
                "auth_required": False,
                "status_message": "Retrieving active weather alerts for state...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "description": "US state postal code (e.g. 'TX', 'CA') or full state name (e.g. 'Texas', 'California').",
                        },
                        "severity": {
                            "type": "string",
                            "description": "Optional severity filter ('Extreme', 'Severe', 'Moderate', 'Minor').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of alerts to return (1-10, default 5).",
                        },
                    },
                    "required": ["state"],
                },
            },
            {
                "name": "get_national_severe_weather_summary",
                "description": "Get a high-level summary of active severe weather hazards and life-threatening emergencies across the United States.",
                "endpoint": "/tools/get-national-severe-weather-summary",
                "method": "POST",
                "auth_required": False,
                "status_message": "Scanning nationwide severe weather emergencies...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "severity_threshold": {
                            "type": "string",
                            "description": "Minimum severity to highlight in detailed breakdown ('Extreme' or 'Severe', default 'Severe').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of critical warnings to list (1-10, default 5).",
                        },
                    },
                },
            },
        ],
    }


@app.post(
    "/tools/get-active-alerts-by-location",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_active_alerts_by_location(
    payload: LocationAlertRequest,
) -> ChatToolResponse:
    """Retrieve active weather alerts for specific GPS coordinates."""
    cache_key = f"loc:{payload.latitude:.4f}:{payload.longitude:.4f}:{payload.severity}"
    cached = cache.get(cache_key)

    if cached is None:
        client = get_http_client()
        params: Dict[str, Any] = {
            "point": f"{payload.latitude:.4f},{payload.longitude:.4f}"
        }
        if payload.severity:
            params["severity"] = payload.severity

        try:
            resp = await client.get(
                f"{NWS_API_BASE_URL}/alerts/active",
                params=params,
            )
            if resp.status_code == 404:
                return ChatToolResponse(
                    result=f"No National Weather Service coverage or active warnings for coordinates ({payload.latitude}, {payload.longitude})."
                )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream NWS returned HTTP {resp.status_code}: {resp.text}",
                )
            cached = resp.json()
            cache.set(cache_key, cached, ttl_seconds=120.0)  # 2 minutes
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching NWS location alerts: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with NWS API: {str(e)}",
            )

    features = cached.get("features", [])
    if not features:
        return ChatToolResponse(
            result=(
                f"✅ **No Active Weather Alerts** for coordinates ({payload.latitude:.4f}, {payload.longitude:.4f}).\n"
                "There are currently no active warnings, watches, or advisories issued by the National Weather Service for this location."
            )
        )

    alerts: List[WeatherAlertItem] = []
    for f in features:
        parsed = parse_alert_feature(f)
        if parsed:
            alerts.append(parsed)

    # Sort alerts by severity order: Extreme > Severe > Moderate > Minor
    severity_rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
    alerts.sort(key=lambda a: severity_rank.get(a.severity, 5))

    header = f"🚨 **Active NWS Weather Alerts ({len(alerts)} Found)** for ({payload.latitude:.4f}, {payload.longitude:.4f}):\n"
    cards = [format_alert_card(a) for a in alerts[:5]]
    return ChatToolResponse(result=header + "\n\n---\n\n".join(cards))


@app.post(
    "/tools/get-active-alerts-by-state",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_active_alerts_by_state(payload: StateAlertRequest) -> ChatToolResponse:
    """Retrieve active weather warnings and watches for a US state."""
    state_code = payload.state
    state_name = US_STATES_MAP.get(state_code, state_code)
    cache_key = f"state:{state_code}:{payload.severity}:{payload.limit}"
    cached = cache.get(cache_key)

    if cached is None:
        client = get_http_client()
        params: Dict[str, Any] = {"area": state_code}
        if payload.severity:
            params["severity"] = payload.severity

        try:
            resp = await client.get(
                f"{NWS_API_BASE_URL}/alerts/active",
                params=params,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream NWS returned HTTP {resp.status_code}: {resp.text}",
                )
            cached = resp.json()
            cache.set(cache_key, cached, ttl_seconds=120.0)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching NWS state alerts: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with NWS API: {str(e)}",
            )

    features = cached.get("features", [])
    if not features:
        return ChatToolResponse(
            result=f"✅ **No Active Weather Alerts** for **{state_name} ({state_code})**.\nThere are currently no active NWS warnings or watches in effect."
        )

    alerts: List[WeatherAlertItem] = []
    for f in features:
        parsed = parse_alert_feature(f)
        if parsed:
            alerts.append(parsed)

    severity_rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3, "Unknown": 4}
    alerts.sort(key=lambda a: severity_rank.get(a.severity, 5))

    shown_alerts = alerts[: payload.limit]
    header = (
        f"⚠️ **Active Weather Alerts for {state_name} ({state_code})**\n"
        f"Total Active in State: **{len(alerts)}** | Showing top **{len(shown_alerts)}** by severity:\n"
    )
    cards = [format_alert_card(a) for a in shown_alerts]
    return ChatToolResponse(result=header + "\n\n---\n\n".join(cards))


@app.post(
    "/tools/get-national-severe-weather-summary",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_national_severe_weather_summary(
    payload: NationalSummaryRequest,
) -> ChatToolResponse:
    """Retrieve high-level summary of severe weather emergencies across the United States."""
    cache_key = f"national:{payload.severity_threshold}:{payload.limit}"
    cached = cache.get(cache_key)

    if cached is None:
        client = get_http_client()
        try:
            count_task = client.get(
                f"{NWS_API_BASE_URL}/alerts/active/count",
                timeout=4.0,
            )
            # Fetch severe/extreme alerts
            sev_params = (
                {"severity": "Extreme"}
                if payload.severity_threshold == "Extreme"
                else {"severity": "Extreme,Severe"}
            )
            alerts_task = client.get(
                f"{NWS_API_BASE_URL}/alerts/active",
                params=sev_params,
                timeout=6.0,
            )
            count_resp, alerts_resp = await asyncio.gather(
                count_task, alerts_task, return_exceptions=True
            )

            if isinstance(count_resp, Exception) or count_resp.status_code != 200:
                total_active = 0
            else:
                total_active = count_resp.json().get("total", 0)

            if isinstance(alerts_resp, Exception) or alerts_resp.status_code != 200:
                features = []
            else:
                features = alerts_resp.json().get("features", [])

            cached = {
                "total_active": total_active,
                "features": features,
            }
            cache.set(cache_key, cached, ttl_seconds=120.0)
        except Exception as e:
            logger.error("Error fetching NWS national summary: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with NWS API: {str(e)}",
            )

    total_active = cached.get("total_active", 0)
    features = cached.get("features", [])

    alerts: List[WeatherAlertItem] = []
    for f in features:
        parsed = parse_alert_feature(f)
        if parsed:
            alerts.append(parsed)

    extreme_count = sum(1 for a in alerts if a.severity == "Extreme")
    severe_count = sum(1 for a in alerts if a.severity == "Severe")

    header_lines = [
        "🇺🇸 **US National Severe Weather Situation Summary**",
        f"• **Total Active Weather Alerts (Nationwide):** {total_active}",
        f"• **Life-Threatening (Extreme):** {extreme_count}",
        f"• **Severe Hazards:** {severe_count}",
        "",
    ]

    if not alerts:
        header_lines.append(
            f"✅ No {payload.severity_threshold.lower()} or higher weather emergencies currently active nationwide."
        )
        return ChatToolResponse(result="\n".join(header_lines))

    header_lines.append(
        f"Top **{min(len(alerts), payload.limit)}** critical hazard warnings in effect:"
    )
    cards = [format_alert_card(a) for a in alerts[: payload.limit]]
    return ChatToolResponse(
        result="\n".join(header_lines) + "\n\n" + "\n\n---\n\n".join(cards)
    )
