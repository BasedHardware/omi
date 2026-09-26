"""
World Universities and Higher Education Directory Integration Plugin for Omi.

Provides chat tools for searching universities worldwide, discovering college websites,
official domains, state/province locations, and exploring higher education institutions by country.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import FastAPI, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

UNIVERSITIES_API_URL = "http://universities.hipolabs.com/search"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESULTS_LIMIT = 25
DEFAULT_RESULTS_LIMIT = 10

# Shared async HTTP client for lifespan management
_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "OmiUniversitiesApp/1.0 (https://omi.me)"},
    )
    yield
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


app = FastAPI(
    title="Omi World Universities App",
    description="Explore universities, official websites, domains, and global colleges from Omi chat tools",
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


class SearchUniversitiesRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Name or search keyword for the university (e.g. 'Stanford', 'Oxford', 'Tech')",
    )
    country: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional country filter (e.g. 'United States', 'India', 'Germany')",
    )
    limit: int = Field(
        default=DEFAULT_RESULTS_LIMIT,
        ge=1,
        le=MAX_RESULTS_LIMIT,
        description="Maximum number of universities to return (1-25)",
    )


class UniversitiesByCountryRequest(BaseModel):
    country: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Country name to list universities from (e.g. 'Japan', 'Canada', 'France')",
    )
    limit: int = Field(
        default=DEFAULT_RESULTS_LIMIT,
        ge=1,
        le=MAX_RESULTS_LIMIT,
        description="Maximum number of universities to return (1-25)",
    )


class UniversityDetailsRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="University name to retrieve full details and links for",
    )
    country: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional country name to disambiguate identical names",
    )


def format_university_card(uni: Dict[str, Any]) -> str:
    """Format a single university record into structured text."""
    name = uni.get("name") or "Unknown Institution"
    country = uni.get("country") or "Unknown Country"
    state = uni.get("state-province")
    code = uni.get("alpha_two_code") or ""
    web_pages = uni.get("web_pages") or []
    domains = uni.get("domains") or []

    lines = [f"🏫 {name}"]
    loc_parts = []
    if state:
        loc_parts.append(state)
    if country:
        loc_parts.append(country)
    if code:
        loc_parts.append(f"({code})")
    if loc_parts:
        lines.append(f"📍 Location: {', '.join(loc_parts)}")

    if domains:
        lines.append(f"🌐 Domain: {', '.join(domains[:2])}")
    if web_pages:
        lines.append(f"🔗 Website: {web_pages[0]}")

    return "\n".join(lines)


async def fetch_universities(
    name: Optional[str] = None,
    country: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Query the Hipo Universities API."""
    params: Dict[str, str] = {}
    if name:
        params["name"] = name.strip()
    if country:
        params["country"] = country.strip()

    http_client = client or get_http_client()
    try:
        response = await http_client.get(UNIVERSITIES_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        return []
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Universities API error: status {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to connect to Universities API: {exc}") from exc


@app.post("/tools/search_universities", response_model=ChatToolResponse)
async def tool_search_universities(request: SearchUniversitiesRequest) -> ChatToolResponse:
    """Search universities worldwide by name or keyword with optional country filtering."""
    query = request.query.strip()
    if not query:
        return ChatToolResponse(error="Search query cannot be empty.")

    try:
        results = await fetch_universities(name=query, country=request.country)
        if not results:
            loc_msg = f" in {request.country}" if request.country else ""
            return ChatToolResponse(result=f"No universities found matching '{query}'{loc_msg}.")

        limited = results[: request.limit]
        cards = [format_university_card(u) for u in limited]
        total_found = len(results)
        showing_str = f"Showing top {len(limited)} of {total_found}" if total_found > len(limited) else f"Found {total_found}"

        header = f"🎓 Global Universities Search: '{query}' ({showing_str})\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/universities_by_country", response_model=ChatToolResponse)
async def tool_universities_by_country(request: UniversitiesByCountryRequest) -> ChatToolResponse:
    """List higher education institutions and universities in a specific country."""
    country = request.country.strip()
    if not country:
        return ChatToolResponse(error="Country name cannot be empty.")

    try:
        results = await fetch_universities(country=country)
        if not results:
            return ChatToolResponse(result=f"No universities found for country '{country}'.")

        limited = results[: request.limit]
        cards = [format_university_card(u) for u in limited]
        total_found = len(results)
        showing_str = f"Showing top {len(limited)} of {total_found}" if total_found > len(limited) else f"Found {total_found}"

        header = f"🏛️ Universities in {country} ({showing_str})\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/university_details", response_model=ChatToolResponse)
async def tool_university_details(request: UniversityDetailsRequest) -> ChatToolResponse:
    """Retrieve detailed institutional information and official links for a university."""
    name = request.name.strip()
    if not name:
        return ChatToolResponse(error="University name cannot be empty.")

    try:
        results = await fetch_universities(name=name, country=request.country)
        if not results:
            return ChatToolResponse(result=f"Could not find university details for '{name}'.")

        # Pick best match (exact case-insensitive match or first item)
        best_match = results[0]
        for item in results:
            if item.get("name", "").strip().lower() == name.lower():
                best_match = item
                break

        card = format_university_card(best_match)
        web_pages = best_match.get("web_pages") or []
        domains = best_match.get("domains") or []

        details = [
            f"🎓 University Profile: {best_match.get('name')}",
            f"🌍 Country: {best_match.get('country')} ({best_match.get('alpha_two_code', '')})",
            f"📍 State / Province: {best_match.get('state-province') or 'Not specified'}",
            f"🌐 Domains: {', '.join(domains) if domains else 'None listed'}",
            f"🔗 Official Websites: {', '.join(web_pages) if web_pages else 'None listed'}",
        ]

        return ChatToolResponse(result="\n".join(details))
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
        <title>Omi World Universities App</title>
        <style>
            :root {
                --bg: #0a0a0f;
                --surface: #13131f;
                --border: #232336;
                --text: #ffffff;
                --text-muted: #8e8ea0;
                --accent: #38bdf8;
                --accent-rgb: 56, 189, 248;
                --radius: 12px;
            }
            body {
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
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
                letter-spacing: -0.02em;
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
                display: flex;
                align-items: center;
                gap: 0.5rem;
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
                <div class="icon">🎓</div>
                <div>
                    <h1>Omi World Universities App</h1>
                    <p class="sub">Global colleges, domains, websites & higher education directory integration for Omi.</p>
                </div>
            </div>

            <div class="card">
                <h2>⚡ Available Chat Tools</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">POST</span>/tools/search_universities</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/universities_by_country</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/university_details</div>
                </div>
            </div>

            <div class="card">
                <h2>🔍 Manifests & Status</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">GET</span><a href="/manifest.json" style="color:var(--accent);">/manifest.json</a> — Omi Plugin Manifest</div>
                    <div class="endpoint"><span class="badge">GET</span><a href="/.well-known/ai-plugin.json" style="color:var(--accent);">/.well-known/ai-plugin.json</a> — AI Plugin Manifest</div>
                    <div class="endpoint"><span class="badge">GET</span><a href="/health" style="color:var(--accent);">/health</a> — Health Status</div>
                </div>
            </div>

            <div class="footer">
                Built for the Omi Open Source Ecosystem • Zero API Keys Required
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
            "name_for_human": "World Universities Directory",
            "name_for_model": "world_universities_app",
            "description_for_human": "Search worldwide universities, explore college domains, official websites, and academic locations.",
            "description_for_model": "Search and explore universities worldwide by name, keyword, or country. Get official domains, websites, and location details.",
            "auth": {"type": "none"},
            "api": {
                "type": "openapi",
                "url": "/openapi.json",
                "is_user_authenticated": False,
            },
            "logo_url": "https://raw.githubusercontent.com/BasedHardware/omi/main/plugins/logos/education.png",
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
    return {"status": "ok", "app": "omi-universities-app"}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy() -> HTMLResponse:
    """Privacy policy declaration."""
    return HTMLResponse(
        """
        <html>
            <body>
                <h1>Privacy Policy</h1>
                <p>The Omi World Universities App does not store or process personal data. All search queries are sent directly to the public Hipo Universities API without retaining user identities.</p>
            </body>
        </html>
        """
    )
