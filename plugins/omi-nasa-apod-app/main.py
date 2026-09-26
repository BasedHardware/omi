"""
NASA Astronomy Picture of the Day & Space Exploration Integration Plugin for Omi.

Provides chat tools for retrieving NASA's Astronomy Picture of the Day (APOD),
searching NASA's Image & Video Library (Hubble, JWST, Mars Rovers, Apollo),
and exploring space science imagery from Omi chat assistants.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

NASA_APOD_URL = "https://api.nasa.gov/planetary/apod"
NASA_IMAGE_LIBRARY_URL = "https://images-api.nasa.gov/search"
REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_API_KEY = "DEMO_KEY"

_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "OmiNasaApp/1.0 (https://omi.me)"},
    )
    yield
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


app = FastAPI(
    title="Omi NASA Astronomy & Space App",
    description="Explore NASA Astronomy Picture of the Day (APOD) and space media from Omi chat tools",
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


class ApodRequest(BaseModel):
    date: Optional[str] = Field(
        None,
        max_length=10,
        description="Optional date in YYYY-MM-DD format (defaults to today's APOD). Must be >= 1995-06-16.",
    )
    count: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Optional number of random astronomy pictures to return (1-5)",
    )


class NasaImageSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Search term (e.g. 'James Webb', 'Mars Perseverance', 'Hubble Deep Field', 'Jupiter')",
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of images to return (1-10)",
    )


def format_apod_result(data: Dict[str, Any]) -> str:
    """Format a single APOD payload into markdown text."""
    title = data.get("title") or "Astronomy Picture of the Day"
    date = data.get("date") or ""
    explanation = data.get("explanation") or ""
    url = data.get("hdurl") or data.get("url") or ""
    media_type = data.get("media_type") or "image"
    copyright_holder = data.get("copyright")

    # Shorten explanation to 400 chars if long
    if len(explanation) > 400:
        explanation = explanation[:397].rsplit(" ", 1)[0] + "..."

    lines = [
        f"🌌 **{title}** ({date})",
        f"📝 {explanation}",
    ]
    if copyright_holder:
        lines.append(f"📸 Image Credit / Copyright: {copyright_holder.strip()}")
    if url:
        lines.append(f"🔗 View {media_type.capitalize()}: {url}")

    return "\n".join(lines)


async def fetch_apod(
    date: Optional[str] = None,
    count: Optional[int] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Any:
    """Fetch Astronomy Picture of the Day."""
    params: Dict[str, Any] = {"api_key": DEFAULT_API_KEY}
    if count:
        params["count"] = count
    elif date:
        params["date"] = date.strip()

    http_client = client or get_http_client()
    try:
        response = await http_client.get(NASA_APOD_URL, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"NASA APOD API error: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to connect to NASA APOD API: {exc}") from exc


async def fetch_nasa_image_library(
    query: str,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Search NASA's open image and video archive."""
    params = {"q": query.strip(), "media_type": "image"}
    http_client = client or get_http_client()
    try:
        response = await http_client.get(NASA_IMAGE_LIBRARY_URL, params=params)
        response.raise_for_status()
        data = response.json()
        collection = data.get("collection") or {}
        items = collection.get("items") or []
        return items
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"NASA Image Library API error: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to connect to NASA Image Library API: {exc}") from exc


@app.post("/tools/astronomy_picture_of_the_day", response_model=ChatToolResponse)
async def tool_astronomy_picture_of_the_day(request: ApodRequest) -> ChatToolResponse:
    """Retrieve NASA's Astronomy Picture of the Day (APOD) with scientific explanation."""
    try:
        data = await fetch_apod(date=request.date, count=request.count)
        if isinstance(data, list):
            cards = [format_apod_result(item) for item in data]
            header = f"🚀 NASA Astronomy Pictures ({len(cards)}):\n"
            return ChatToolResponse(result=f"{header}\n" + "\n\n".join(cards))
        elif isinstance(data, dict):
            return ChatToolResponse(result=format_apod_result(data))
        else:
            return ChatToolResponse(result="No APOD data found.")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/search_nasa_images", response_model=ChatToolResponse)
async def tool_search_nasa_images(request: NasaImageSearchRequest) -> ChatToolResponse:
    """Search NASA's official mission media library for telescopes, rovers, and space missions."""
    query = request.query.strip()
    if not query:
        return ChatToolResponse(error="Search query cannot be empty.")

    try:
        items = await fetch_nasa_image_library(query=query)
        if not items:
            return ChatToolResponse(result=f"No NASA mission media found matching '{query}'.")

        limited = items[: request.limit]
        cards = []
        for item in limited:
            data_list = item.get("data") or [{}]
            meta = data_list[0] if data_list else {}
            title = meta.get("title") or "NASA Image"
            desc = meta.get("description") or ""
            date_created = meta.get("date_created", "")[:10]
            nasa_id = meta.get("nasa_id") or ""

            if len(desc) > 250:
                desc = desc[:247].rsplit(" ", 1)[0] + "..."

            links = item.get("links") or [{}]
            img_href = links[0].get("href") if links else ""

            card_lines = [
                f"🛰️ **{title}** ({date_created})",
                f"📝 {desc}" if desc else "📝 NASA Space Mission Photo",
            ]
            if img_href:
                card_lines.append(f"🔗 View Image: {img_href}")
            cards.append("\n".join(card_lines))

        header = f"🔭 NASA Mission Imagery Search for '{query}' (Found {len(cards)}):\n"
        return ChatToolResponse(result=f"{header}\n" + "\n\n".join(cards))
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
        <title>Omi NASA Space App</title>
        <style>
            :root {
                --bg: #070913;
                --surface: #0f1225;
                --border: #1e2448;
                --text: #ffffff;
                --text-muted: #8c93b6;
                --accent: #818cf8;
                --accent-rgb: 129, 140, 248;
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
                border: 1px solid var(--border);
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
                border: 1px solid var(--border);
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
                border: 1px solid var(--border);
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
                <div class="icon">🚀</div>
                <div>
                    <h1>Omi NASA Space App</h1>
                    <p class="sub">Astronomy Picture of the Day & NASA Mission Media for Omi Assistants.</p>
                </div>
            </div>

            <div class="card">
                <h2>⚡ Available Chat Tools</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">POST</span>/tools/astronomy_picture_of_the_day</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/search_nasa_images</div>
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
                Built for the Omi Open Source Ecosystem • Powered by NASA Open APIs
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
            "name_for_human": "NASA Astronomy & Space",
            "name_for_model": "nasa_space_app",
            "description_for_human": "Discover NASA Astronomy Picture of the Day (APOD) and search NASA space mission imagery (JWST, Hubble, Mars Rovers).",
            "description_for_model": "Retrieve NASA Astronomy Picture of the Day (APOD) with scientific explanations, and search official NASA space mission photos.",
            "auth": {"type": "none"},
            "api": {
                "type": "openapi",
                "url": "/openapi.json",
                "is_user_authenticated": False,
            },
            "logo_url": "https://raw.githubusercontent.com/BasedHardware/omi/main/plugins/logos/nasa.png",
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
    return {"status": "ok", "app": "omi-nasa-apod-app"}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy() -> HTMLResponse:
    """Privacy policy declaration."""
    return HTMLResponse(
        """
        <html>
            <body>
                <h1>Privacy Policy</h1>
                <p>The Omi NASA Space App does not collect or retain personal user data. All requests are routed to public NASA Open APIs.</p>
            </body>
        </html>
        """
    )
