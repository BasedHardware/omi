"""The Metropolitan Museum of Art Omi Integration Plugin.

Provides access to over 470,000 artworks, 19 curatorial departments,
and cultural intelligence from The Met collection for Omi wearable devices.
"""

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
import copy
import ipaddress
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
import httpx

from models import (
    ArtworkDetail,
    ArtworkDetailsRequest,
    ArtworkSummary,
    ChatToolResponse,
    DepartmentHighlightsRequest,
    DepartmentItem,
    SearchArtworksRequest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omi-met-museum-app")

MET_API_BASE_URL = os.getenv(
    "MET_API_BASE_URL", "https://collectionapi.metmuseum.org/public/collection/v1"
)
REQUEST_TIMEOUT = float(os.getenv("MET_API_TIMEOUT", "10.0"))
MAX_CACHE_SIZE = int(os.getenv("MAX_CACHE_SIZE", "1000"))
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = float(os.getenv("RATE_LIMIT_WINDOW", "60.0"))
MAX_RATE_LIMITER_KEYS = int(os.getenv("MAX_RATE_LIMITER_KEYS", "5000"))
TRUSTED_PROXIES = set(
    ip.strip()
    for ip in os.getenv(
        "TRUSTED_PROXIES",
        "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,testclient",
    ).split(",")
    if ip.strip()
)

# Shared HTTP client managed by FastAPI lifespan
http_client: Optional[httpx.AsyncClient] = None


class LRUCache:
    """Bounded, thread-safe In-Memory LRU Cache with TTL expiry."""

    def __init__(self, max_size: int = MAX_CACHE_SIZE) -> None:
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

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time() + ttl_seconds, copy.deepcopy(value))

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


cache = LRUCache(max_size=MAX_CACHE_SIZE)


class SlidingWindowRateLimiter:
    """Sliding-window in-memory rate limiter with bounded storage."""

    def __init__(
        self,
        requests_per_window: int = RATE_LIMIT_REQUESTS,
        window_seconds: float = RATE_LIMIT_WINDOW,
        max_keys: int = MAX_RATE_LIMITER_KEYS,
    ) -> None:
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._records: OrderedDict[str, List[float]] = OrderedDict()

    def _purge_idle_keys(self, now: float) -> None:
        stale_keys = [
            k
            for k, timestamps in self._records.items()
            if not timestamps or (now - timestamps[-1]) > self.window_seconds
        ]
        for k in stale_keys:
            del self._records[k]

        while len(self._records) >= self.max_keys:
            self._records.popitem(last=False)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        self._purge_idle_keys(now)

        if client_ip not in self._records:
            self._records[client_ip] = []
        else:
            self._records.move_to_end(client_ip)

        window_start = now - self.window_seconds
        self._records[client_ip] = [
            ts for ts in self._records[client_ip] if ts > window_start
        ]

        if len(self._records[client_ip]) >= self.requests_per_window:
            return False

        self._records[client_ip].append(now)
        return True


rate_limiter = SlidingWindowRateLimiter()


def is_trusted_proxy(ip_str: str) -> bool:
    """Check if direct connection host matches trusted proxy configuration or private network."""
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
        return ip_obj.is_loopback or ip_obj.is_private
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
            detail="Rate limit exceeded. Maximum 60 requests per minute.",
        )


def get_http_client() -> httpx.AsyncClient:
    """Returns the active AsyncClient, lazily creating one if not yet initialized."""
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={
                "User-Agent": "OmiMetMuseumApp/1.0 (contact: team@basedhardware.com)",
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
                "User-Agent": "OmiMetMuseumApp/1.0 (contact: team@basedhardware.com)",
                "Accept": "application/json",
            },
        )
        owns_client = True
        logger.info("Initialized Met Museum HTTP client.")
    yield
    if owns_client and http_client:
        await http_client.aclose()
        http_client = None
        logger.info("Closed Met Museum HTTP client.")


app = FastAPI(
    title="Omi Met Museum Art Collection Plugin",
    description="Explore 470,000+ artworks and 19 curatorial departments from The Metropolitan Museum of Art.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)



async def _fetch_object(object_id: int) -> Optional[Dict[str, Any]]:
    """Fetch individual object details with caching.

    Returns:
        Dict: Object details on success.
        None: When object does not exist (HTTP 404, with 5-minute negative cache).
    Raises:
        HTTPException(502): When upstream Met API fails, times out, or returns a 5xx error.
    """
    cache_key = f"object:{object_id}"
    cached = cache.get(cache_key)
    if cached == "NOT_FOUND":
        return None
    elif cached is not None:
        return cached

    client = get_http_client()
    try:
        resp = await client.get(f"{MET_API_BASE_URL}/objects/{object_id}")
        if resp.status_code == 200:
            data = resp.json()
            cache.set(cache_key, data, ttl_seconds=3600.0)  # 1 hour
            return data
        elif resp.status_code == 404:
            cache.set(cache_key, "NOT_FOUND", ttl_seconds=300.0)  # 5 min negative cache
            return None
        else:
            logger.warning(
                "Upstream Met object %d returned HTTP %d", object_id, resp.status_code
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"The Metropolitan Museum of Art API returned status {resp.status_code} for object {object_id}.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching Met object %d: %s", object_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with The Metropolitan Museum of Art API: {str(e)}",
        )


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "app": "Omi Met Museum Art Collection Plugin",
        "status": "online",
        "description": "Access 470,000+ public domain artworks from The Metropolitan Museum of Art.",
        "endpoints": {
            "tools_manifest": "/.well-known/omi-tools.json",
            "search_artworks": "/tools/search-artworks",
            "get_artwork_details": "/tools/get-artwork-details",
            "list_departments": "/tools/list-departments",
            "get_department_highlights": "/tools/get-department-highlights",
            "health": "/health",
        },
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health probe with cached upstream check to prevent Met API flooding."""
    cached_status = cache.get("health_upstream_status")
    if cached_status is None:
        upstream_ok = False
        client = get_http_client()
        try:
            resp = await client.get(
                f"{MET_API_BASE_URL}/departments", timeout=3.0
            )
            upstream_ok = resp.status_code == 200
        except Exception as e:
            logger.warning("Met Museum health probe failed: %s", e)
        cached_status = upstream_ok
        cache.set("health_upstream_status", upstream_ok, ttl_seconds=60.0)

    return {
        "status": "healthy" if cached_status else "degraded",
        "upstream_met_api": "reachable" if cached_status else "unreachable",
        "cached_entries": cache.size(),
        "timestamp": time.time(),
    }


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest() -> Dict[str, Any]:
    """Exposes Omi function calling tools manifest in standard repository format."""
    return {
        "schema_version": "1.0",
        "name": "Metropolitan Museum of Art",
        "description": "Explore 470,000+ artworks and 19 curatorial departments from The Metropolitan Museum of Art.",
        "tools": [
            {
                "name": "search_artworks",
                "description": "Search 470,000+ artworks from The Metropolitan Museum of Art collection by keyword, artist, or culture.",
                "endpoint": "/tools/search-artworks",
                "method": "POST",
                "auth_required": False,
                "status_message": "Searching the Met Collection...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search term (e.g. 'water lilies', 'Rembrandt', 'Greek vase', 'armor')",
                        },
                        "artist_or_culture": {
                            "type": "boolean",
                            "description": "Whether to restrict matches to artist names or cultural origins (optional)",
                        },
                        "department_id": {
                            "type": "integer",
                            "description": "Filter by curatorial department ID (optional)",
                        },
                        "has_images": {
                            "type": "boolean",
                            "description": "Only return artworks with public digital images (default true)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of artwork summaries to return (1-10, default 5)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_artwork_details",
                "description": "Get comprehensive details for a specific Metropolitan Museum artwork by its object ID.",
                "endpoint": "/tools/get-artwork-details",
                "method": "POST",
                "auth_required": False,
                "status_message": "Retrieving Met artwork details...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "object_id": {
                            "type": "integer",
                            "description": "Unique object ID of the artwork in the Met collection",
                        }
                    },
                    "required": ["object_id"],
                },
            },
            {
                "name": "list_departments",
                "description": "List all 19 curatorial departments at The Metropolitan Museum of Art with their department IDs.",
                "endpoint": "/tools/list-departments",
                "method": "POST",
                "auth_required": False,
                "status_message": "Loading Met curatorial departments...",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "get_department_highlights",
                "description": "Retrieve curated masterwork highlights from a specified Met curatorial department.",
                "endpoint": "/tools/get-department-highlights",
                "method": "POST",
                "auth_required": False,
                "status_message": "Fetching department highlights...",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "department_id": {
                            "type": "integer",
                            "description": "Department ID (e.g. 11 for European Paintings, 10 for Egyptian Art, 6 for Asian Art)",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max number of highlights to return (1-10, default 5)",
                        },
                    },
                    "required": ["department_id"],
                },
            },
        ],
    }


@app.post(
    "/tools/search-artworks",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def search_artworks(payload: SearchArtworksRequest) -> ChatToolResponse:
    cache_key = f"search:{payload.query}:{payload.artist_or_culture}:{payload.department_id}:{payload.has_images}"
    cached_ids = cache.get(cache_key)

    if cached_ids is None:
        client = get_http_client()
        params: Dict[str, Any] = {"q": payload.query}
        if payload.has_images:
            params["hasImages"] = "true"
        if payload.artist_or_culture is True:
            params["artistOrCulture"] = "true"
        if payload.department_id is not None:
            params["departmentId"] = str(payload.department_id)

        try:
            resp = await client.get(
                f"{MET_API_BASE_URL}/search", params=params
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream Met Museum search returned HTTP {resp.status_code}",
                )
            data = resp.json()
            raw_ids = data.get("objectIDs")
            cached_ids = raw_ids if raw_ids is not None else []
            cache.set(cache_key, cached_ids, ttl_seconds=600.0)  # 10 min
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error executing Met search: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to communicate with The Metropolitan Museum of Art API: {str(e)}",
            )

    if not cached_ids:
        return ChatToolResponse(
            result=f"No artworks found in The Metropolitan Museum of Art collection matching '{payload.query}'."
        )

    target_ids = cached_ids[: payload.limit]
    tasks = [_fetch_object(oid) for oid in target_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summaries: List[ArtworkSummary] = []
    for data in results:
        if not data or isinstance(data, Exception):
            continue
        summaries.append(
            ArtworkSummary(
                object_id=data.get("objectID", 0),
                title=data.get("title") or "Untitled",
                artist_display_name=data.get("artistDisplayName") or "Unknown Artist",
                object_date=data.get("objectDate") or "Date Unknown",
                medium=data.get("medium") or "Not specified",
                department=data.get("department") or "General Collection",
                primary_image_small=data.get("primaryImageSmall") or None,
                object_url=data.get("objectURL")
                or f"https://www.metmuseum.org/art/collection/search/{data.get('objectID')}",
            )
        )

    if not summaries:
        return ChatToolResponse(
            result=f"Found matches for '{payload.query}', but detailed records are temporarily unavailable."
        )

    lines = [
        f"🎨 **Metropolitan Museum of Art — Search Results for '{payload.query}'** ({len(summaries)} shown, {len(cached_ids)} total):\n"
    ]
    for idx, s in enumerate(summaries, 1):
        img_str = f" • [Image]({s.primary_image_small})" if s.primary_image_small else ""
        lines.append(
            f"{idx}. **{s.title}** ({s.object_date})\n"
            f"   - **Artist:** {s.artist_display_name}\n"
            f"   - **Medium & Dept:** {s.medium} | {s.department}\n"
            f"   - **Object ID:** `{s.object_id}` • [Met Link]({s.object_url}){img_str}"
        )

    return ChatToolResponse(result="\n\n".join(lines))


@app.post(
    "/tools/get-artwork-details",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_artwork_details(payload: ArtworkDetailsRequest) -> ChatToolResponse:
    data = await _fetch_object(payload.object_id)
    if not data:
        return ChatToolResponse(
            result=f"Artwork with Object ID `{payload.object_id}` was not found in The Metropolitan Museum of Art collection."
        )

    tags_list = [
        t.get("term")
        for t in data.get("tags") or []
        if isinstance(t, dict) and t.get("term")
    ]

    detail = ArtworkDetail(
        object_id=data.get("objectID", payload.object_id),
        title=data.get("title") or "Untitled",
        artist_display_name=data.get("artistDisplayName") or "Unknown Artist",
        artist_display_bio=data.get("artistDisplayBio") or None,
        artist_nationality=data.get("artistNationality") or None,
        culture=data.get("culture") or None,
        period=data.get("period") or None,
        object_date=data.get("objectDate") or "Date Unknown",
        medium=data.get("medium") or "Not specified",
        dimensions=data.get("dimensions") or None,
        department=data.get("department") or "General Collection",
        credit_line=data.get("creditLine") or None,
        classification=data.get("classification") or None,
        is_highlight=bool(data.get("isHighlight", False)),
        is_public_domain=bool(data.get("isPublicDomain", False)),
        primary_image=data.get("primaryImage") or None,
        primary_image_small=data.get("primaryImageSmall") or None,
        object_url=data.get("objectURL")
        or f"https://www.metmuseum.org/art/collection/search/{payload.object_id}",
        tags=tags_list,
    )

    lines = [
        f"🖼️ **{detail.title}**",
        f"**Artist:** {detail.artist_display_name}"
        + (f" ({detail.artist_display_bio})" if detail.artist_display_bio else ""),
        f"**Date:** {detail.object_date}",
        f"**Department:** {detail.department}",
        f"**Medium:** {detail.medium}",
    ]
    if detail.dimensions:
        lines.append(f"**Dimensions:** {detail.dimensions}")
    if detail.culture:
        lines.append(f"**Culture:** {detail.culture}")
    if detail.period:
        lines.append(f"**Period:** {detail.period}")
    if detail.classification:
        lines.append(f"**Classification:** {detail.classification}")
    if detail.credit_line:
        lines.append(f"**Credit Line:** {detail.credit_line}")

    flags = []
    if detail.is_highlight:
        flags.append("🌟 Met Highlight")
    if detail.is_public_domain:
        flags.append("🔓 Open Access / Public Domain")
    if flags:
        lines.append(f"**Status:** {' | '.join(flags)}")

    if detail.tags:
        lines.append(f"**Tags:** {', '.join(detail.tags[:6])}")

    links = [f"[View on Met Collection]({detail.object_url})"]
    if detail.primary_image:
        links.append(f"[High-Res Image]({detail.primary_image})")
    elif detail.primary_image_small:
        links.append(f"[Thumbnail Image]({detail.primary_image_small})")

    lines.append(f"**Links:** {' • '.join(links)}")

    return ChatToolResponse(result="\n".join(lines))


@app.post(
    "/tools/list-departments",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def list_departments() -> ChatToolResponse:
    cache_key = "departments_list"
    cached = cache.get(cache_key)

    if cached is None:
        client = get_http_client()
        try:
            resp = await client.get(f"{MET_API_BASE_URL}/departments")
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream Met departments returned HTTP {resp.status_code}",
                )
            departments_data = resp.json().get("departments", [])
            cached = [
                DepartmentItem(
                    department_id=d["departmentId"],
                    display_name=d["displayName"],
                ).model_dump()
                for d in departments_data
            ]
            cache.set(cache_key, cached, ttl_seconds=86400.0)  # 24 hours
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching Met departments: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch curatorial departments: {str(e)}",
            )

    items = [DepartmentItem(**d) for d in cached]
    lines = [
        "🏛️ **The Metropolitan Museum of Art — Curatorial Departments**:\n",
        "Use these department IDs with `search_artworks` or `get_department_highlights`:\n",
    ]
    for dept in items:
        lines.append(f"- **ID {dept.department_id}**: {dept.display_name}")

    return ChatToolResponse(result="\n".join(lines))


@app.post(
    "/tools/get-department-highlights",
    response_model=ChatToolResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
async def get_department_highlights(
    payload: DepartmentHighlightsRequest,
) -> ChatToolResponse:
    cache_key = f"dept_highlights:{payload.department_id}"
    cached_ids = cache.get(cache_key)

    if cached_ids is None:
        client = get_http_client()
        params = {
            "departmentId": str(payload.department_id),
            "isHighlight": "true",
            "q": "*",
        }
        try:
            resp = await client.get(
                f"{MET_API_BASE_URL}/search", params=params
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Upstream Met search returned HTTP {resp.status_code}",
                )
            raw_ids = resp.json().get("objectIDs")
            cached_ids = raw_ids if raw_ids is not None else []
            cache.set(cache_key, cached_ids, ttl_seconds=3600.0)  # 1 hour
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Error fetching department highlights: %s", e)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch highlights for department {payload.department_id}: {str(e)}",
            )

    if not cached_ids:
        return ChatToolResponse(
            result=f"No curated highlights found for Met department ID `{payload.department_id}`."
        )

    target_ids = cached_ids[: payload.limit]
    tasks = [_fetch_object(oid) for oid in target_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summaries: List[ArtworkSummary] = []
    for data in results:
        if not data or isinstance(data, Exception):
            continue
        summaries.append(
            ArtworkSummary(
                object_id=data.get("objectID", 0),
                title=data.get("title") or "Untitled",
                artist_display_name=data.get("artistDisplayName") or "Unknown Artist",
                object_date=data.get("objectDate") or "Date Unknown",
                medium=data.get("medium") or "Not specified",
                department=data.get("department") or "General Collection",
                primary_image_small=data.get("primaryImageSmall") or None,
                object_url=data.get("objectURL")
                or f"https://www.metmuseum.org/art/collection/search/{data.get('objectID')}",
            )
        )

    dept_name = summaries[0].department if summaries else f"Department {payload.department_id}"
    lines = [
        f"⭐ **Metropolitan Museum of Art — Highlights from {dept_name}** ({len(summaries)} masterpieces shown):\n"
    ]
    for idx, s in enumerate(summaries, 1):
        img_str = f" • [Image]({s.primary_image_small})" if s.primary_image_small else ""
        lines.append(
            f"{idx}. **{s.title}** ({s.object_date})\n"
            f"   - **Artist:** {s.artist_display_name}\n"
            f"   - **Medium:** {s.medium}\n"
            f"   - **Object ID:** `{s.object_id}` • [View on Met]({s.object_url}){img_str}"
        )

    return ChatToolResponse(result="\n\n".join(lines))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
