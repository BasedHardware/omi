"""
iTunes Search Integration App for Omi.

Provides chat tools for searching songs, podcasts, and artist top tracks using
Apple's public iTunes Search API. No API key required.
"""

from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"
REQUEST_TIMEOUT_SECONDS = 10
MAX_RESULTS = 10


app = FastAPI(
    title="Omi iTunes Integration",
    description="Search songs, podcasts, and artist top tracks from Omi chat tools",
    version="1.0.0",
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=120)


def _clean_query(value: str) -> str:
    return " ".join(str(value).strip().split())


def _format_duration_ms(ms: Any) -> str:
    if not isinstance(ms, (int, float)) or isinstance(ms, bool) or ms <= 0:
        return ""
    total = int(ms) // 1000
    return f"{total // 60}:{total % 60:02d}"


def _format_song(item: Any) -> str:
    if not isinstance(item, dict):
        return "Unknown track"
    track = item.get("trackName") or "Untitled"
    artist = item.get("artistName") or "Unknown artist"
    album = item.get("collectionName")
    duration = _format_duration_ms(item.get("trackTimeMillis"))
    parts = [f"{track} — {artist}"]
    if album and album != track:
        parts.append(f"({album})")
    if duration:
        parts.append(duration)
    return " ".join(parts)


def _format_podcast(item: Any) -> str:
    if not isinstance(item, dict):
        return "Unknown podcast"
    name = item.get("collectionName") or item.get("trackName") or "Untitled"
    artist = item.get("artistName")
    genre = item.get("primaryGenreName")
    parts = [name]
    if artist:
        parts.append(f"— {artist}")
    if genre:
        parts.append(f"[{genre}]")
    return " ".join(parts)


async def _request_json(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Any:
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html>
      <head><title>Omi iTunes Integration</title></head>
      <body>
        <h1>Omi iTunes Integration</h1>
        <p>Use Omi chat tools to search songs, podcasts, and artist top tracks.</p>
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
        "name": "iTunes",
        "description": "Search songs, podcasts, and artist top tracks via Apple's iTunes Search API.",
        "tools": [
            {
                "name": "search_songs",
                "description": "Search songs by title, artist, or album.",
                "endpoint": "/tools/search_songs",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search terms, such as 'daft punk get lucky'.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_podcasts",
                "description": "Search podcasts by name or topic.",
                "endpoint": "/tools/search_podcasts",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Podcast name or topic, such as 'technology'.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_artist_top_songs",
                "description": "List an artist's top songs on iTunes.",
                "endpoint": "/tools/get_artist_top_songs",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Artist name, such as 'radiohead'.",
                        },
                    },
                    "required": ["query"],
                },
            },
        ],
    }


@app.post("/tools/search_songs", response_model=ChatToolResponse)
async def search_songs(request: SearchRequest) -> ChatToolResponse:
    query = _clean_query(request.query)
    if not query:
        return ChatToolResponse(error="query is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(
                client,
                ITUNES_SEARCH_URL,
                {"term": query, "media": "music", "entity": "song", "limit": MAX_RESULTS},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"iTunes request failed: {exc}")

    results = payload.get("results") if isinstance(payload, dict) else None
    if not results:
        return ChatToolResponse(result=f"No songs found for '{query}'.")

    lines = [f"Songs matching '{query}':"]
    for item in results[:MAX_RESULTS]:
        lines.append(f"- {_format_song(item)}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/search_podcasts", response_model=ChatToolResponse)
async def search_podcasts(request: SearchRequest) -> ChatToolResponse:
    query = _clean_query(request.query)
    if not query:
        return ChatToolResponse(error="query is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            payload = await _request_json(
                client,
                ITUNES_SEARCH_URL,
                {"term": query, "media": "podcast", "entity": "podcast", "limit": MAX_RESULTS},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"iTunes request failed: {exc}")

    results = payload.get("results") if isinstance(payload, dict) else None
    if not results:
        return ChatToolResponse(result=f"No podcasts found for '{query}'.")

    lines = [f"Podcasts matching '{query}':"]
    for item in results[:MAX_RESULTS]:
        lines.append(f"- {_format_podcast(item)}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_artist_top_songs", response_model=ChatToolResponse)
async def get_artist_top_songs(request: SearchRequest) -> ChatToolResponse:
    artist = _clean_query(request.query)
    if not artist:
        return ChatToolResponse(error="artist name is required")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            search = await _request_json(
                client,
                ITUNES_SEARCH_URL,
                {"term": artist, "media": "music", "entity": "musicArtist", "limit": 1},
            )
            artists = search.get("results") or []
            if not artists:
                return ChatToolResponse(result=f"No artist found for '{artist}'.")
            artist_id = artists[0].get("artistId")
            artist_name = artists[0].get("artistName") or artist
            if artist_id is None:
                return ChatToolResponse(result=f"Could not resolve artist '{artist}'.")

            lookup = await _request_json(
                client,
                ITUNES_LOOKUP_URL,
                {"id": artist_id, "entity": "song", "limit": MAX_RESULTS, "sort": "popular"},
            )
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"iTunes request failed: {exc}")

    results = lookup.get("results") if isinstance(lookup, dict) else None
    songs = [item for item in (results or []) if isinstance(item, dict) and item.get("kind") == "song"]
    if not songs:
        return ChatToolResponse(result=f"No songs found for artist '{artist_name}'.")

    lines = [f"Top songs by {artist_name}:"]
    for item in songs[:MAX_RESULTS]:
        lines.append(f"- {_format_song(item)}")
    return ChatToolResponse(result="\n".join(lines))
