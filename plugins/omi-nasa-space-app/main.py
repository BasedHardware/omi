"""NASA Space & Astronomy Intelligence Omi Integration Plugin.

Provides real-time cosmological insights, NASA Astronomy Picture of the Day (APOD),
Near-Earth Asteroid (NEO) tracking, and official mission archives for Omi wearable devices.
"""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import copy
from datetime import datetime, timezone
import ipaddress
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
import httpx

from models import (
    ApodDetail,
    ApodRequest,
    AsteroidFeedRequest,
    AsteroidItem,
    ChatToolResponse,
    NasaMediaSummary,
    NasaSearchRequest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omi-nasa-space-app")

NASA_API_BASE_URL = os.getenv("NASA_API_BASE_URL", "https://api.nasa.gov")
NASA_IMAGES_BASE_URL = os.getenv("NASA_IMAGES_BASE_URL", "https://images-api.nasa.gov")
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
REQUEST_TIMEOUT = float(os.getenv("NASA_REQUEST_TIMEOUT", "10.0"))
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

    def set(self, key: str, value: Any, ttl_seconds: float = 3600.0) -> None:
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
    if http_client is None:
        http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": "OmiNasaSpaceApp/1.0 (contact: team@basedhardware.com)",
                "Accept": "application/json",
            },
        )
    return http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    owns_client = False
    if http_client is None:
        http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": "OmiNasaSpaceApp/1.0 (contact: team@basedhardware.com)",
                "Accept": "application/json",
            },
        )
        owns_client = True
        logger.info("Initialized NASA API HTTP client.")
    yield
    if owns_client and http_client:
        await http_client.aclose()
        http_client = None
        logger.info("Closed NASA API HTTP client.")


app = FastAPI(
    title="Omi NASA Space & Astronomy Intelligence Plugin",
    description="Live space science, NASA Astronomy Picture of the Day (APOD), Near-Earth Asteroid tracking, and official mission archives for Omi wearable devices.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "online",
        "service": "Omi NASA Space & Astronomy Intelligence Plugin",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "tools_manifest": "/.well-known/omi-tools.json",
            "astronomy_picture": "/tools/get-astronomy-picture",
            "near_earth_asteroids": "/tools/get-near-earth-asteroids",
            "search_nasa_media": "/tools/search-nasa-media",
        },
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint probing keyless NASA upstream (images-api.nasa.gov).

    Probes the keyless images API to verify upstream NASA connectivity without
    consuming rate-limited NASA_API_KEY or DEMO_KEY quota during routine
    container/deployment healthchecks.
    """
    cached_status = cache.get("health_upstream_status")

    if cached_status is None:
        upstream_ok = False
        client = get_http_client()
        try:
            resp = await client.get(
                f"{NASA_IMAGES_BASE_URL}/search",
                params={"q": "sun", "media_type": "image"},
                timeout=3.5,
            )
            upstream_ok = resp.status_code == 200
        except Exception as e:
            logger.warning("NASA upstream health probe failed: %s", e)
        cached_status = upstream_ok
        cache.set("health_upstream_status", upstream_ok, ttl_seconds=60.0)

    return {
        "status": "healthy" if cached_status else "degraded",
        "upstream_nasa_api": "reachable" if cached_status else "unreachable",
        "cached_entries": cache.size(),
        "timestamp": time.time(),
    }


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest() -> Dict[str, Any]:
    """Exposes Omi function calling tools manifest in standard repository format."""
    return {
        "schema_version": "1.0",
        "name": "NASA Space & Astronomy Intelligence",
        "description": "Live space science, NASA Astronomy Picture of the Day (APOD), Near-Earth Asteroid tracking, and official mission archives.",
        "tools": [
            {
                "name": "get_astronomy_picture",
                "description": "Get NASA's official Astronomy Picture of the Day (APOD) with expert cosmological explanation, title, and high-res imagery.",
                "endpoint": "/tools/get-astronomy-picture",
                "method": "POST",
                "auth_required": False,
                "status_message": "Retrieving NASA Astronomy Picture of the Day...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "Optional date in YYYY-MM-DD format (e.g. '2024-07-20'). Defaults to today.",
                        },
                        "thumbs": {
                            "type": "boolean",
                            "description": "Whether to return thumbnail URLs if the APOD feature is a video (default true).",
                        },
                    },
                },
            },
            {
                "name": "get_near_earth_asteroids",
                "description": "Get real-time tracking of near-Earth asteroids passing by our planet today, with diameters, speeds, miss distances, and hazard status.",
                "endpoint": "/tools/get-near-earth-asteroids",
                "method": "POST",
                "auth_required": False,
                "status_message": "Scanning Near-Earth asteroid trajectories...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of asteroids to return (1-10, default 5).",
                        },
                        "hazardous_only": {
                            "type": "boolean",
                            "description": "Filter exclusively for asteroids classified as potentially hazardous (default false).",
                        },
                    },
                },
            },
            {
                "name": "search_nasa_media",
                "description": "Search NASA's official photo and mission archive (Hubble, James Webb Space Telescope, Mars rovers, Apollo, nebulae).",
                "endpoint": "/tools/search-nasa-media",
                "method": "POST",
                "auth_required": False,
                "status_message": "Searching NASA multimedia archive...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g. 'James Webb', 'Pillars of Creation', 'Mars Curiosity', 'Europa', 'Saturn rings').",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of media assets to return (1-10, default 5).",
                        },
                    },
                    "required": ["query"],
                },
            },
        ],
    }


@app.post(
    "/tools/get-astronomy-picture",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_astronomy_picture(payload: ApodRequest) -> ChatToolResponse:
    """Retrieve NASA Astronomy Picture of the Day."""
    date_str = payload.date.isoformat() if payload.date else None
    cache_key = f"apod:{date_str or 'today'}:{payload.thumbs}"
    cached = cache.get(cache_key)

    if cached is None:
        client = get_http_client()
        params: Dict[str, Any] = {"api_key": NASA_API_KEY}
        if date_str:
            params["date"] = date_str
        if payload.thumbs:
            params["thumbs"] = "true"

        try:
            resp = await client.get(
                f"{NASA_API_BASE_URL}/planetary/apod", params=params
            )
            if resp.status_code in (400, 404):
                error_detail = ""
                try:
                    err_json = resp.json()
                    if isinstance(err_json, dict):
                        error_detail = (
                            err_json.get("msg")
                            or err_json.get("error", {}).get("message")
                            or ""
                        )
                except Exception:
                    pass
                target = f" for date '{date_str}'" if date_str else ""
                if error_detail:
                    return ChatToolResponse(
                        result=f"No NASA Astronomy Picture of the Day found{target}: {error_detail}"
                    )
                return ChatToolResponse(
                    result=f"No NASA Astronomy Picture of the Day found{target}."
                )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream NASA APOD returned HTTP {resp.status_code}: {resp.text}",
                )
            cached = resp.json()
            # If historical date, cache longer (24h); if today or unspecified, cache for 1 hour
            today_utc = datetime.now(timezone.utc).date()
            ttl = 3600.0 if (not payload.date or payload.date == today_utc) else 86400.0
            cache.set(cache_key, cached, ttl_seconds=ttl)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching NASA APOD: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with NASA APOD API: {str(e)}",
            )

    apod = ApodDetail(
        date=cached.get("date", "Unknown Date"),
        title=cached.get("title", "Untitled"),
        explanation=cached.get("explanation", "No description available."),
        media_type=cached.get("media_type", "image"),
        url=cached.get("url", ""),
        hdurl=cached.get("hdurl"),
        thumbnail_url=cached.get("thumbnail_url"),
        copyright=cached.get("copyright"),
    )

    lines = [
        f"🌌 **NASA Astronomy Picture of the Day — {apod.date}**",
        f"**Title:** {apod.title}",
    ]
    if apod.copyright:
        lines.append(f"**Credit/Copyright:** {apod.copyright.strip()}")

    # Truncate explanation cleanly for voice/chat synthesis if very long
    explanation = apod.explanation.strip()
    if len(explanation) > 500:
        cutoff = explanation[:497].rfind(" ")
        explanation = (
            explanation[:cutoff] + "..." if cutoff > 0 else explanation[:497] + "..."
        )
    lines.append(f"\n{explanation}\n")

    links = []
    if apod.url:
        label = "View HD Image" if apod.media_type == "image" else "Watch Video"
        links.append(f"[{label}]({apod.url})")
    if apod.hdurl and apod.hdurl != apod.url:
        links.append(f"[Full Resolution]({apod.hdurl})")
    if apod.thumbnail_url:
        links.append(f"[Video Thumbnail]({apod.thumbnail_url})")

    if links:
        lines.append(f"**Media Link:** {' • '.join(links)}")

    return ChatToolResponse(result="\n".join(lines))


@app.post(
    "/tools/get-near-earth-asteroids",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_near_earth_asteroids(payload: AsteroidFeedRequest) -> ChatToolResponse:
    """Retrieve near-Earth asteroids passing Earth today."""
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    cache_key = f"neo_feed:{today_str}"
    cached_data = cache.get(cache_key)

    if cached_data is None:
        client = get_http_client()
        params = {
            "start_date": today_str,
            "end_date": today_str,
            "detailed": "false",
            "api_key": NASA_API_KEY,
        }
        try:
            resp = await client.get(
                f"{NASA_API_BASE_URL}/neo/rest/v1/feed", params=params
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream NASA NeoWs returned HTTP {resp.status_code}: {resp.text}",
                )
            cached_data = resp.json()
            cache.set(cache_key, cached_data, ttl_seconds=1800.0)  # 30 min
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching NASA NeoWs: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with NASA NeoWs API: {str(e)}",
            )

    neo_dict = cached_data.get("near_earth_objects", {})
    raw_asteroids: List[Dict[str, Any]] = []
    for date_key in neo_dict:
        raw_asteroids.extend(neo_dict[date_key])

    if not raw_asteroids:
        return ChatToolResponse(
            result=f"No near-Earth asteroid encounters recorded for today ({today_str})."
        )

    parsed_asteroids: List[AsteroidItem] = []
    for a in raw_asteroids:
        is_hazard = bool(a.get("is_potentially_hazardous_asteroid", False))
        if payload.hazardous_only and not is_hazard:
            continue

        diam_info = a.get("estimated_diameter", {}).get("meters", {})
        close_data = a.get("close_approach_data", [])
        miss_km = 0.0
        velocity_kmh = 0.0
        time_raw = None
        if close_data:
            first_approach = close_data[0]
            time_raw = first_approach.get(
                "close_approach_date_full"
            ) or first_approach.get("close_approach_date")
            try:
                miss_km = float(
                    first_approach.get("miss_distance", {}).get("kilometers", 0.0)
                )
            except (ValueError, TypeError):
                miss_km = 0.0
            try:
                velocity_kmh = float(
                    first_approach.get("relative_velocity", {}).get(
                        "kilometers_per_hour", 0.0
                    )
                )
            except (ValueError, TypeError):
                velocity_kmh = 0.0

        if not time_raw:
            time_raw = datetime.now(timezone.utc)

        parsed_asteroids.append(
            AsteroidItem(
                name=a.get("name", "Unknown Asteroid"),
                estimated_diameter_min_m=float(
                    diam_info.get("estimated_diameter_min", 0.0)
                ),
                estimated_diameter_max_m=float(
                    diam_info.get("estimated_diameter_max", 0.0)
                ),
                is_potentially_hazardous=is_hazard,
                close_approach_time=time_raw,
                miss_distance_km=miss_km,
                relative_velocity_kmh=velocity_kmh,
            )
        )

    if not parsed_asteroids:
        filter_note = (
            " classified as potentially hazardous" if payload.hazardous_only else ""
        )
        return ChatToolResponse(
            result=f"No near-Earth asteroids{filter_note} detected for today ({today_str})."
        )

    # Sort by closest miss distance
    parsed_asteroids.sort(key=lambda x: x.miss_distance_km)
    selected = parsed_asteroids[: payload.limit]

    total_count = cached_data.get("element_count", len(raw_asteroids))
    hazard_count = sum(
        1 for a in raw_asteroids if a.get("is_potentially_hazardous_asteroid")
    )

    lines = [
        f"☄️ **NASA Near-Earth Asteroid Tracking — {today_str}**",
        f"**Active Encounters Today:** {total_count} asteroids ({hazard_count} potentially hazardous)\n",
    ]

    for idx, item in enumerate(selected, 1):
        status_flag = (
            "⚠️ **POTENTIALLY HAZARDOUS**"
            if item.is_potentially_hazardous
            else "🟢 Safe Trajectory"
        )
        avg_diam = (item.estimated_diameter_min_m + item.estimated_diameter_max_m) / 2.0
        time_display = item.close_approach_time.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(
            f"{idx}. **Asteroid {item.name}** ({status_flag})\n"
            f"   - **Est. Diameter:** ~{avg_diam:.1f} meters ({item.estimated_diameter_min_m:.0f}m – {item.estimated_diameter_max_m:.0f}m)\n"
            f"   - **Miss Distance:** {item.miss_distance_km:,.0f} km\n"
            f"   - **Relative Speed:** {item.relative_velocity_kmh:,.0f} km/h\n"
            f"   - **Close Approach Time:** {time_display}"
        )

    return ChatToolResponse(result="\n\n".join(lines))


@app.post(
    "/tools/search-nasa-media",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def search_nasa_media(payload: NasaSearchRequest) -> ChatToolResponse:
    """Search official NASA image and video archive."""
    cache_key = f"nasa_search:{payload.query.lower()}:{payload.limit}"
    cached_results = cache.get(cache_key)

    if cached_results is None:
        client = get_http_client()
        params = {
            "q": payload.query,
            "media_type": "image",
            "page_size": payload.limit,
        }
        try:
            resp = await client.get(f"{NASA_IMAGES_BASE_URL}/search", params=params)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream NASA Image Library returned HTTP {resp.status_code}: {resp.text}",
                )
            cached_results = resp.json()
            cache.set(cache_key, cached_results, ttl_seconds=1800.0)  # 30 min
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error searching NASA image library: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with NASA Image Library: {str(e)}",
            )

    items = cached_results.get("collection", {}).get("items", [])
    if not items:
        return ChatToolResponse(
            result=f"No NASA multimedia records found matching '{payload.query}'."
        )

    summaries: List[NasaMediaSummary] = []
    for it in items[: payload.limit]:
        data_list = it.get("data", [])
        if not data_list:
            continue
        primary = data_list[0]
        links = it.get("links", [])
        thumb_url = links[0].get("href") if links else None

        desc = primary.get("description") or "No description provided."
        if len(desc) > 220:
            cutoff = desc[:217].rfind(" ")
            desc = desc[:cutoff] + "..." if cutoff > 0 else desc[:217] + "..."

        summaries.append(
            NasaMediaSummary(
                nasa_id=primary.get("nasa_id", "Unknown"),
                title=primary.get("title", "Untitled"),
                date_created=(primary.get("date_created") or "Unknown Date")[:10],
                description=desc,
                center=primary.get("center"),
                thumbnail_url=thumb_url,
            )
        )

    if not summaries:
        return ChatToolResponse(
            result=f"Matches found for '{payload.query}', but detailed imagery records are currently unavailable."
        )

    lines = [
        f"🔭 **NASA Official Media Archive — Results for '{payload.query}'** ({len(summaries)} assets shown):\n"
    ]
    for idx, s in enumerate(summaries, 1):
        center_str = f" • Center: {s.center}" if s.center else ""
        img_str = f" • [Preview Image]({s.thumbnail_url})" if s.thumbnail_url else ""
        lines.append(
            f"{idx}. **{s.title}** ({s.date_created})\n"
            f"   - **NASA ID:** `{s.nasa_id}`{center_str}{img_str}\n"
            f"   - **Summary:** {s.description}"
        )

    return ChatToolResponse(result="\n\n".join(lines))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
