"""
TVmaze Integration App for Omi.

Provides chat tools for searching TV shows, checking next-episode air dates,
and listing tonight's broadcast/streaming schedule using the public TVmaze API.
"""

from datetime import date
from html import unescape
import re
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


TVMAZE_BASE_URL = "https://api.tvmaze.com"
REQUEST_TIMEOUT_SECONDS = 10
MAX_SEARCH_RESULTS = 5
MAX_SCHEDULE_ITEMS = 15


app = FastAPI(
    title="Omi TVmaze Integration",
    description="Search TV shows, find next episode air dates, and see tonight's schedule from Omi chat tools",
    version="1.0.0",
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class ShowSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=120)


class NextEpisodeRequest(BaseModel):
    show: str = Field(..., min_length=1, max_length=120)


class ScheduleRequest(BaseModel):
    country: str = Field(default="US", min_length=2, max_length=2)


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unescape(_TAG_RE.sub(" ", value)).split())


def _clean_query(value: str) -> str:
    return " ".join(str(value).strip().split())


def _format_show_line(show: Any) -> str:
    """One-line summary of a TVmaze show object."""
    if not isinstance(show, dict):
        return "Unknown show"
    name = show.get("name") or "Untitled"
    year = str(show.get("premiered") or "")[:4]
    channel = (show.get("network") or {}).get("name") or (show.get("webChannel") or {}).get("name") or ""
    status = show.get("status") or ""
    genres = ", ".join(g for g in (show.get("genres") or []) if isinstance(g, str))
    rating = (show.get("rating") or {}).get("average")

    parts = [name]
    if year:
        parts[0] = f"{name} ({year})"
    details = []
    if channel:
        details.append(channel)
    if status:
        details.append(status.lower())
    if rating is not None:
        details.append(f"rated {rating}/10")
    if genres:
        details.append(genres)
    return " — ".join([parts[0], "; ".join(details)]) if details else parts[0]


def _format_episode(episode: Any, show_name: str = "") -> str:
    if not isinstance(episode, dict):
        return ""
    ep_name = episode.get("name") or "Untitled episode"
    season = episode.get("season")
    number = episode.get("number")
    code = ""
    if isinstance(season, int) and isinstance(number, int):
        code = f" (S{season:02d}E{number:02d})"
    airdate = episode.get("airdate") or "date TBD"
    airtime = episode.get("airtime") or ""
    when = f"{airdate} {airtime}".strip()
    prefix = f"{show_name}: " if show_name else ""
    return f"{prefix}\"{ep_name}\"{code} — {when}"


async def _request_json(client: httpx.AsyncClient, url: str, params: Optional[dict[str, Any]] = None) -> Any:
    response = await client.get(url, params=params or {})
    response.raise_for_status()
    return response.json()


async def _search_show(client: httpx.AsyncClient, query: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Resolve a show name to the best TVmaze match."""
    cleaned = _clean_query(query)
    if not cleaned:
        return None, "show name is required"
    payload = await _request_json(client, f"{TVMAZE_BASE_URL}/search/shows", {"q": cleaned})
    if not isinstance(payload, list) or not payload:
        return None, f"no TVmaze result for '{cleaned}'"
    best = payload[0].get("show")
    if not isinstance(best, dict) or not best.get("id"):
        return None, f"no TVmaze result for '{cleaned}'"
    return best, None


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi TVmaze Integration</title></head>
      <body>
        <h1>Omi TVmaze Integration</h1>
        <p>Use Omi chat tools to search shows, find next episode dates, and browse tonight's schedule.</p>
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
        "name": "TVmaze",
        "description": "Search TV shows, find next episode air dates, and see tonight's TV schedule from Omi.",
        "tools": [
            {
                "name": "search_shows",
                "description": "Search for a TV show by name and see its channel, status, rating, and genres.",
                "endpoint": "/tools/search_shows",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Show name to search for, such as 'Severance'.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_next_episode",
                "description": "Find the next episode air date for a TV show, or confirm the show has ended.",
                "endpoint": "/tools/get_next_episode",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "show": {
                            "type": "string",
                            "description": "Show name, such as 'The Bear'.",
                        },
                    },
                    "required": ["show"],
                },
            },
            {
                "name": "get_tonights_schedule",
                "description": "List tonight's TV episodes airing in a country (ISO 3166-1 alpha-2 code, e.g. US or GB).",
                "endpoint": "/tools/get_tonights_schedule",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "country": {
                            "type": "string",
                            "description": "Two-letter country code such as US, GB, or CA.",
                            "default": "US",
                        },
                    },
                },
            },
        ],
    }


@app.post("/tools/search_shows", response_model=ChatToolResponse)
async def search_shows(request: ShowSearchRequest) -> ChatToolResponse:
    query = _clean_query(request.query)
    if not query:
        return ChatToolResponse(error="query is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(client, f"{TVMAZE_BASE_URL}/search/shows", {"q": query})
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"TVmaze request failed: {exc}")

    if not isinstance(payload, list) or not payload:
        return ChatToolResponse(result=f"No shows found matching '{query}'.")

    lines = [f"Top results for '{query}':"]
    for item in payload[:MAX_SEARCH_RESULTS]:
        show = item.get("show") if isinstance(item, dict) else None
        lines.append(f"- {_format_show_line(show)}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_next_episode", response_model=ChatToolResponse)
async def get_next_episode(request: NextEpisodeRequest) -> ChatToolResponse:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            show, error = await _search_show(client, request.show)
            if error:
                return ChatToolResponse(error=error)

            detail = await _request_json(
                client,
                f"{TVMAZE_BASE_URL}/shows/{show['id']}",
                {"embed[]": ["nextepisode", "previousepisode"]},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"TVmaze request failed: {exc}")

    name = detail.get("name") or show.get("name") or request.show
    status = (detail.get("status") or "").lower()
    embedded = detail.get("_embedded") or {}
    next_ep = embedded.get("nextepisode")
    prev_ep = embedded.get("previousepisode")

    lines = [_format_show_line(detail)]
    if next_ep:
        lines.append(f"Next episode: {_format_episode(next_ep)}")
    elif status == "running":
        lines.append("The show is still running, but no next-episode date is announced yet.")
    elif status:
        lines.append(f"No upcoming episode — the show is {status}.")
    else:
        lines.append("No upcoming episode found.")
    if prev_ep:
        lines.append(f"Latest episode: {_format_episode(prev_ep)}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_tonights_schedule", response_model=ChatToolResponse)
async def get_tonights_schedule(request: ScheduleRequest) -> ChatToolResponse:
    country = _clean_query(request.country).upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        return ChatToolResponse(error="country must be a two-letter ISO code such as US, GB, or CA")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(
                client,
                f"{TVMAZE_BASE_URL}/schedule",
                {"country": country, "date": date.today().isoformat()},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"TVmaze request failed: {exc}")

    if not isinstance(payload, list) or not payload:
        return ChatToolResponse(result=f"No scheduled episodes found tonight for {country}.")

    lines = [f"Tonight's schedule ({country}, {date.today().isoformat()}):"]
    for item in payload[:MAX_SCHEDULE_ITEMS]:
        if not isinstance(item, dict):
            continue
        show = item.get("show") or {}
        airtime = item.get("airtime") or "time TBD"
        channel = (show.get("network") or {}).get("name") or (show.get("webChannel") or {}).get("name") or ""
        ep_name = item.get("name") or "Untitled episode"
        channel_part = f" [{channel}]" if channel else ""
        lines.append(f"- {airtime}{channel_part} {show.get('name') or 'Unknown show'}: \"{ep_name}\"")
    return ChatToolResponse(result="\n".join(lines))
