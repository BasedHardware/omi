"""Classical Poetry & Spoken Verse Integration App for Omi.

Provides instant access to thousands of public-domain poems, sonnets,
and literary verses from classical poets for Omi AI wearable users.
Requires zero external authentication or API keys.
"""

from collections import OrderedDict
from contextlib import asynccontextmanager
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetPoemByTitleRequest,
    GetRandomPoemRequest,
    ListPoetsRequest,
    SearchPoemsByAuthorRequest,
)

POETRYDB_API_URL = "https://poetrydb.org"
REQUEST_TIMEOUT_SECONDS = 15.0
USER_AGENT = "omi-poetry-app/1.0 (https://omi.me)"


# ---------------------------------------------------------------------------
# In-Memory Bounded LRU Cache with TTL
# ---------------------------------------------------------------------------
class SimpleTTLCache:
    """Thread-safe, bounded LRU cache with expiration."""

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 3600):
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


poetry_cache = SimpleTTLCache(maxsize=256, ttl_seconds=3600)


# ---------------------------------------------------------------------------
# Lifespan & FastAPI App Setup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi Classical Poetry & Verse Integration",
    description="Spoken poetry, famous sonnets, and classical literature lookup for Omi AI wearables.",
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
# Formatting Helpers
# ---------------------------------------------------------------------------
def _format_poem(poem: Dict[str, Any], max_lines: Optional[int] = None) -> str:
    """Format a poem dict into an engaging voice-friendly prompt."""
    title = poem.get("title", "Untitled").strip()
    author = poem.get("author", "Unknown").strip()
    lines = poem.get("lines", [])
    total_lines = len(lines)

    if max_lines and total_lines > max_lines:
        displayed_lines = lines[:max_lines]
        truncated_note = f"\n\n... [{total_lines - max_lines} more lines in full poem]"
    else:
        displayed_lines = lines
        truncated_note = ""

    body = "\n".join(displayed_lines)
    return (
        f"📜 \"{title}\"\n"
        f"✍️ by {author} ({total_lines} lines)\n\n"
        f"{body}"
        f"{truncated_note}"
    )


# ---------------------------------------------------------------------------
# Tool Endpoints
# ---------------------------------------------------------------------------
@app.post("/tools/get_random_poem", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_random_poem(request: GetRandomPoemRequest) -> ChatToolResponse:
    """Retrieve a random classical poem or sonnet, optionally filtered by poet and length."""
    client: httpx.AsyncClient = app.state.http_client
    max_lines = request.max_lines or 30
    try:
        if request.author:
            safe_author = urllib.parse.quote(request.author, safe="")
            url = f"{POETRYDB_API_URL}/author/{safe_author}"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and data.get("status") == 404:
                return ChatToolResponse(error=f"No poems found for author '{request.author}'.")

            if not isinstance(data, list) or not data:
                return ChatToolResponse(error=f"Could not retrieve poems for author '{request.author}'.")

            # Filter poems within max_lines if possible; otherwise fall back to truncating
            matching = [p for p in data if int(p.get("linecount", 0)) <= max_lines]
            candidate = random.choice(matching) if matching else random.choice(data)
            return ChatToolResponse(result=_format_poem(candidate, max_lines=max_lines))

        # Random poem without author constraint
        url = f"{POETRYDB_API_URL}/random/5"
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

        if not isinstance(data, list) or not data:
            return ChatToolResponse(error="Could not retrieve a random poem at this moment.")

        matching = [p for p in data if int(p.get("linecount", 0)) <= max_lines]
        candidate = matching[0] if matching else data[0]
        return ChatToolResponse(result=_format_poem(candidate, max_lines=max_lines))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            author_msg = f" for author '{request.author}'" if request.author else ""
            return ChatToolResponse(error=f"No poems found{author_msg}.")
        return ChatToolResponse(error=f"Upstream poetry service error: HTTP {exc.response.status_code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to retrieve poem: {exc}")


@app.post("/tools/search_poems_by_author", response_model=ChatToolResponse, response_model_exclude_none=True)
async def search_poems_by_author(request: SearchPoemsByAuthorRequest) -> ChatToolResponse:
    """Search and browse poems by a classical poet (e.g. Shakespeare, Poe, Dickinson, Keats)."""
    client: httpx.AsyncClient = app.state.http_client
    cache_key = f"author:{request.author.lower()}"
    cached = poetry_cache.get(cache_key)

    try:
        if not cached:
            safe_author = urllib.parse.quote(request.author, safe="")
            url = f"{POETRYDB_API_URL}/author/{safe_author}"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and data.get("status") == 404:
                return ChatToolResponse(error=f"No poems found for poet '{request.author}'. Use list_poets to see available authors.")

            if not isinstance(data, list) or not data:
                return ChatToolResponse(error=f"Could not retrieve poems for poet '{request.author}'.")

            cached = data
            poetry_cache.set(cache_key, cached)

        total_found = len(cached)
        max_results = request.max_results or 3
        selected = cached[: max_results]

        output_parts = [f"📚 Found {total_found} poem{'s' if total_found != 1 else ''} by {request.author}:\n"]
        for idx, p in enumerate(selected, 1):
            title = p.get("title", "Untitled").strip()
            linecount = p.get("linecount", len(p.get("lines", [])))
            preview_lines = p.get("lines", [])[:4]
            preview = "\n  ".join(preview_lines)
            output_parts.append(f"{idx}. \"{title}\" ({linecount} lines):\n  {preview}\n  ...")

        return ChatToolResponse(result="\n".join(output_parts))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(error=f"No poems found for poet '{request.author}'. Use list_poets to see available authors.")
        return ChatToolResponse(error=f"Upstream poetry service error: HTTP {exc.response.status_code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to search poems by author '{request.author}': {exc}")


@app.post("/tools/get_poem_by_title", response_model=ChatToolResponse, response_model_exclude_none=True)
async def get_poem_by_title(request: GetPoemByTitleRequest) -> ChatToolResponse:
    """Look up a specific poem or sonnet by title (e.g. 'Ozymandias', 'The Raven', 'Sonnet 18')."""
    client: httpx.AsyncClient = app.state.http_client
    cache_key = f"title:{request.title.lower()}:{request.author.lower() if request.author else ''}"
    cached = poetry_cache.get(cache_key)

    try:
        if not cached:
            if request.author:
                safe_author = urllib.parse.quote(request.author, safe="")
                safe_title = urllib.parse.quote(request.title, safe="")
                url = f"{POETRYDB_API_URL}/author,title/{safe_author};{safe_title}"
            else:
                safe_title = urllib.parse.quote(request.title, safe="")
                url = f"{POETRYDB_API_URL}/title/{safe_title}"

            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and data.get("status") == 404:
                return ChatToolResponse(error=f"Poem titled '{request.title}' not found in the public domain library.")

            if not isinstance(data, list) or not data:
                return ChatToolResponse(error=f"No results found for poem title '{request.title}'.")

            cached = data[0]
            poetry_cache.set(cache_key, cached)

        return ChatToolResponse(result=_format_poem(cached))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(error=f"Poem titled '{request.title}' not found in the public domain library.")
        return ChatToolResponse(error=f"Upstream poetry service error: HTTP {exc.response.status_code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to get poem '{request.title}': {exc}")


@app.post("/tools/list_poets", response_model=ChatToolResponse, response_model_exclude_none=True)
async def list_poets(request: ListPoetsRequest) -> ChatToolResponse:
    """List available classical poets and literary figures in the poetry library."""
    client: httpx.AsyncClient = app.state.http_client
    cached_authors = poetry_cache.get("all_authors")

    try:
        if not cached_authors:
            url = f"{POETRYDB_API_URL}/author"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            authors = data.get("authors", [])
            cached_authors = sorted(authors)
            poetry_cache.set("all_authors", cached_authors)

        if request.query:
            q = request.query.lower()
            filtered = [a for a in cached_authors if q in a.lower()]
            if not filtered:
                return ChatToolResponse(error=f"No poets matching query '{request.query}' found.")
            lines = [f"🖋️ Poets matching '{request.query}' ({len(filtered)}):"]
            for a in filtered:
                lines.append(f"• {a}")
            return ChatToolResponse(result="\n".join(lines))

        lines = [f"🖋️ Classical Poets in Library ({len(cached_authors)} available):"]
        for a in cached_authors[:30]:
            lines.append(f"• {a}")
        if len(cached_authors) > 30:
            lines.append(f"\n... and {len(cached_authors) - 30} more poets. Use a search query to filter.")

        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Upstream poetry service error: HTTP {exc.response.status_code}")
    except Exception as exc:
        return ChatToolResponse(error=f"Failed to list poets: {exc}")


# ---------------------------------------------------------------------------
# Health & Manifest Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "service": "omi-poetry-app", "version": "1.0.0"}


@app.get("/.well-known/omi-tools.json")
async def omi_tools() -> Dict[str, Any]:
    """Omi Function Calling Chat Tools Manifest."""
    return {
        "schema_version": "1.0",
        "auth": {"type": "none"},
        "tools": [
            {
                "name": "get_random_poem",
                "description": "Recite or read aloud a random classical poem, sonnet, or verse with optional author and length filters.",
                "endpoint": "/tools/get_random_poem",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "author": {
                            "type": "string",
                            "description": "Optional poet name (e.g. 'Emily Dickinson', 'Shakespeare', 'Robert Frost').",
                        },
                        "max_lines": {
                            "type": "integer",
                            "description": "Maximum line count (default 30, optimal for voice recitation).",
                        },
                    },
                },
            },
            {
                "name": "search_poems_by_author",
                "description": "Browse and discover classical poems by a specific poet (e.g. Shakespeare, Poe, Keats, Dickinson).",
                "endpoint": "/tools/search_poems_by_author",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "author": {
                            "type": "string",
                            "description": "Name of the author or poet (e.g. 'Edgar Allan Poe', 'Walt Whitman').",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of poems to summarize (default 3).",
                        },
                    },
                    "required": ["author"],
                },
            },
            {
                "name": "get_poem_by_title",
                "description": "Retrieve the full text of a famous classical poem by title (e.g. 'Ozymandias', 'The Raven', 'Sonnet 18').",
                "endpoint": "/tools/get_poem_by_title",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Exact or partial title of the poem.",
                        },
                        "author": {
                            "type": "string",
                            "description": "Optional poet name to narrow search.",
                        },
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "list_poets",
                "description": "Browse and search available classical poets and authors in the literature library.",
                "endpoint": "/tools/list_poets",
                "method": "POST",
                "auth_required": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional keyword or name to filter poets (e.g. 'Shelley', 'Dickinson').",
                        },
                    },
                },
            },
        ],
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """Service landing page."""
    return HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Omi Classical Poetry & Verse App</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 48px auto; padding: 0 16px; line-height: 1.6; color: #24292f; }
                h1 { font-size: 24px; color: #0969da; }
                code { background: #f6f8fa; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
                pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }
                ul { padding-left: 20px; }
            </style>
        </head>
        <body>
            <h1>📜 Omi Classical Poetry & Verse App</h1>
            <p>Spoken poetry, classical literature, and sonnet recitation for Omi AI wearables powered by PoetryDB.</p>
            <h3>Registered Chat Tools:</h3>
            <ul>
                <li><code>get_random_poem</code>: Random classical poem or sonnet recitation.</li>
                <li><code>search_poems_by_author</code>: Discover works by famous poets.</li>
                <li><code>get_poem_by_title</code>: Retrieve full poem text by title.</li>
                <li><code>list_poets</code>: Browse poets in the public domain collection.</li>
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
