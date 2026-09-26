"""
Open Brewery & Craft Beverage Finder Integration Plugin for Omi.

Provides chat tools for searching craft breweries, taprooms, brewpubs, cideries,
and beverage spots worldwide using the public Open Brewery DB API.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

BREWERIES_API_URL = "https://api.openbrewerydb.org/v1/breweries"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESULTS_LIMIT = 20
DEFAULT_RESULTS_LIMIT = 5

_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "OmiBreweryApp/1.0 (https://omi.me)"},
    )
    yield
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


app = FastAPI(
    title="Omi Craft Brewery Finder App",
    description="Discover craft breweries, taprooms, brewpubs, and locations worldwide from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


def get_http_client() -> httpx.AsyncClient:
    """Return the global client or instantiate a fallback."""
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchBreweriesRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Brewery name or search keyword (e.g. 'Stone', 'Sierra Nevada', 'Dogfish')",
    )
    limit: int = Field(
        default=DEFAULT_RESULTS_LIMIT,
        ge=1,
        le=MAX_RESULTS_LIMIT,
        description="Maximum number of results to return (1-20)",
    )


class BreweriesByLocationRequest(BaseModel):
    city: Optional[str] = Field(
        None,
        max_length=80,
        description="City name (e.g. 'San Diego', 'Portland', 'Denver')",
    )
    state: Optional[str] = Field(
        None,
        max_length=80,
        description="State or province name (e.g. 'California', 'Colorado', 'Texas')",
    )
    country: Optional[str] = Field(
        None,
        max_length=80,
        description="Country name (e.g. 'United States', 'Ireland', 'Germany')",
    )
    brewery_type: Optional[str] = Field(
        None,
        max_length=30,
        description="Brewery type (e.g. 'micro', 'brewpub', 'regional', 'cidery')",
    )
    limit: int = Field(
        default=DEFAULT_RESULTS_LIMIT,
        ge=1,
        le=MAX_RESULTS_LIMIT,
        description="Maximum number of results to return (1-20)",
    )


class RandomBreweryRequest(BaseModel):
    size: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Number of random breweries to discover (1-5)",
    )


def format_brewery_card(b: Dict[str, Any]) -> str:
    """Format a single brewery record into a clear markdown card."""
    name = b.get("name") or "Unnamed Brewery"
    b_type = (b.get("brewery_type") or "brewery").capitalize()
    street = b.get("address_1")
    city = b.get("city")
    state = b.get("state_province") or b.get("state")
    country = b.get("country")
    postal = b.get("postal_code")
    phone = b.get("phone")
    website = b.get("website_url")

    loc_parts = [p for p in [street, city, state, postal, country] if p]
    loc_str = ", ".join(loc_parts) if loc_parts else "Location not specified"

    lines = [
        f"🍺 **{name}** ({b_type})",
        f"📍 Address: {loc_str}",
    ]
    if phone:
        lines.append(f"📞 Phone: {phone}")
    if website:
        lines.append(f"🌐 Website: {website}")

    return "\n".join(lines)


async def fetch_breweries(
    endpoint: str = "",
    params: Optional[Dict[str, Any]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Query the Open Brewery DB API."""
    url = f"{BREWERIES_API_URL}/{endpoint}".rstrip("/")
    http_client = client or get_http_client()
    try:
        response = await http_client.get(url, params=params or {})
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Open Brewery API error: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to connect to Open Brewery API: {exc}") from exc


@app.post("/tools/search_breweries", response_model=ChatToolResponse)
async def tool_search_breweries(request: SearchBreweriesRequest) -> ChatToolResponse:
    """Search breweries, brewpubs, and taprooms by name or keyword."""
    query = request.query.strip()
    if not query:
        return ChatToolResponse(error="Search query cannot be empty.")

    try:
        results = await fetch_breweries(
            endpoint="search",
            params={"query": query, "per_page": request.limit},
        )
        if not results:
            return ChatToolResponse(result=f"No craft breweries found matching '{query}'.")

        cards = [format_brewery_card(b) for b in results[: request.limit]]
        header = f"🍻 Craft Breweries Found for '{query}' (Found {len(cards)}):\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/breweries_by_location", response_model=ChatToolResponse)
async def tool_breweries_by_location(request: BreweriesByLocationRequest) -> ChatToolResponse:
    """Find craft breweries and brewpubs filtered by city, state, or country."""
    params: Dict[str, Any] = {"per_page": request.limit}
    loc_labels = []

    if request.city:
        params["by_city"] = request.city.strip().lower().replace(" ", "_")
        loc_labels.append(request.city.strip())
    if request.state:
        params["by_state"] = request.state.strip().lower().replace(" ", "_")
        loc_labels.append(request.state.strip())
    if request.country:
        params["by_country"] = request.country.strip().lower().replace(" ", "_")
        loc_labels.append(request.country.strip())
    if request.brewery_type:
        params["by_type"] = request.brewery_type.strip().lower()

    if not (request.city or request.state or request.country):
        return ChatToolResponse(error="Please specify at least a city, state, or country.")

    try:
        results = await fetch_breweries(params=params)
        loc_desc = ", ".join(loc_labels) if loc_labels else "location"
        if not results:
            return ChatToolResponse(result=f"No craft breweries found for {loc_desc}.")

        cards = [format_brewery_card(b) for b in results[: request.limit]]
        header = f"🍻 Craft Breweries in {loc_desc} (Found {len(cards)}):\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/random_brewery", response_model=ChatToolResponse)
async def tool_random_brewery(request: RandomBreweryRequest) -> ChatToolResponse:
    """Discover random craft breweries and taprooms."""
    try:
        results = await fetch_breweries(
            endpoint="random",
            params={"size": request.size},
        )
        if not results:
            return ChatToolResponse(result="Could not fetch random breweries at this time.")

        cards = [format_brewery_card(b) for b in results[: request.size]]
        header = f"🎲 Random Craft Brewery Discovery:\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve an interactive status and documentation dashboard."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Omi Craft Brewery Finder App</title>
        <style>
            :root {
                --bg: #0b0c10;
                --surface: #1f2833;
                --border: #45a29e;
                --text: #ffffff;
                --text-muted: #c5c6c7;
                --accent: #66fcf1;
                --accent-rgb: 102, 252, 241;
                --radius: 12px;
            }
            body {
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                padding: 2.5rem 1.5rem;
                display: flex;
                justify-content: center;
            }
            .container {
                max-width: 760px;
                width: 100%;
            }
            .header {
                display: flex;
                align-items: center;
                gap: 1rem;
                margin-bottom: 2rem;
            }
            .icon {
                font-size: 2.5rem;
                background: var(--surface);
                padding: 0.75rem;
                border-radius: var(--radius);
                border: 1px solid rgba(102, 252, 241, 0.2);
            }
            h1 {
                margin: 0 0 0.25rem 0;
                font-size: 1.75rem;
            }
            p.sub {
                margin: 0;
                color: var(--text-muted);
                font-size: 0.95rem;
            }
            .card {
                background: var(--surface);
                border: 1px solid rgba(102, 252, 241, 0.2);
                border-radius: var(--radius);
                padding: 1.5rem;
                margin-bottom: 1.5rem;
            }
            h2 {
                margin-top: 0;
                font-size: 1.2rem;
                color: var(--accent);
            }
            .endpoint-list {
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
            }
            .endpoint {
                background: var(--bg);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 0.75rem 1rem;
                font-family: monospace;
                font-size: 0.9rem;
            }
            .badge {
                background: rgba(var(--accent-rgb), 0.15);
                color: var(--accent);
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
                margin-right: 0.5rem;
            }
            .footer {
                text-align: center;
                color: var(--text-muted);
                font-size: 0.85rem;
                margin-top: 2rem;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="icon">🍺</div>
                <div>
                    <h1>Omi Craft Brewery Finder App</h1>
                    <p class="sub">Breweries, taprooms, brewpubs & craft beverage discovery for Omi.</p>
                </div>
            </div>

            <div class="card">
                <h2>⚡ Available Chat Tools</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">POST</span>/tools/search_breweries</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/breweries_by_location</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/random_brewery</div>
                </div>
            </div>

            <div class="card">
                <h2>🔍 Manifests & Endpoints</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">GET</span><a href="/manifest.json" style="color:var(--accent);">/manifest.json</a> — Omi Plugin Manifest</div>
                    <div class="endpoint"><span class="badge">GET</span><a href="/.well-known/ai-plugin.json" style="color:var(--accent);">/.well-known/ai-plugin.json</a> — AI Plugin Manifest</div>
                    <div class="endpoint"><span class="badge">GET</span><a href="/health" style="color:var(--accent);">/health</a> — Health Status</div>
                </div>
            </div>

            <div class="footer">
                Built for the Omi Open Source Ecosystem • Powered by Open Brewery DB
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/manifest.json")
async def manifest() -> JSONResponse:
    """Return the Omi plugin manifest."""
    return JSONResponse(
        {
            "schema_version": "v1",
            "name_for_human": "Craft Brewery Finder",
            "name_for_model": "craft_brewery_finder_app",
            "description_for_human": "Discover craft breweries, taprooms, brewpubs, cideries, and local beverage spots worldwide.",
            "description_for_model": "Search breweries, brewpubs, taprooms, and cideries by name, city, state, or country. Get addresses, phone numbers, and websites.",
            "auth": {"type": "none"},
            "api": {
                "type": "openapi",
                "url": "/openapi.json",
                "is_user_authenticated": False,
            },
            "logo_url": "https://raw.githubusercontent.com/BasedHardware/omi/main/plugins/logos/beer.png",
            "contact_email": "support@omi.me",
            "legal_info_url": "/privacy",
        }
    )


@app.get("/.well-known/ai-plugin.json")
async def ai_plugin_manifest() -> JSONResponse:
    """Return the OpenAI standard plugin manifest."""
    return await manifest()


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "omi-brewery-finder-app"}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy() -> HTMLResponse:
    """Privacy policy declaration."""
    return HTMLResponse(
        """
        <html>
            <body>
                <h1>Privacy Policy</h1>
                <p>The Omi Craft Brewery Finder App does not collect or retain personal user data. All search queries are sent directly to the public Open Brewery DB API.</p>
            </body>
        </html>
        """
    )
