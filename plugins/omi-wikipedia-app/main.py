"""
Wikipedia Integration App for Omi.

Provides chat tools for searching Wikipedia, reading concise article summaries,
and finding a random article for exploration.
"""

from contextlib import asynccontextmanager
from html import unescape
import re
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


REQUEST_TIMEOUT_SECONDS = 10
MAX_LIMIT = 10
DEFAULT_LANGUAGE = "en"
USER_AGENT = "omi-wikipedia-app/1.0 (https://omi.me)"

# Persistent HTTP client reused across requests (see `lifespan`). Tools run
# inside the FastAPI app get connection pooling instead of a fresh client —
# and fresh TCP/TLS handshakes — on every call, which exhausts sockets under
# load. `None` means no managed client (scripts, direct tool invocation), and
# `_request_json` falls back to a short-lived client.
_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage one pooled httpx client for the process lifetime."""
    global _client
    _client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        yield
    finally:
        await _client.aclose()
        _client = None


app = FastAPI(
    title="Omi Wikipedia Integration",
    description="Search and read Wikipedia from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


def _safe_limit(limit: Any) -> int:
    if limit is None or limit == "":
        return 5
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return 5
    return max(1, min(limit, MAX_LIMIT))


def _safe_language(language: Optional[str]) -> str:
    lang = (language or DEFAULT_LANGUAGE).strip().lower()
    if not lang.replace("-", "").isalpha() or len(lang) > 12:
        return DEFAULT_LANGUAGE
    return lang


def _payload_dict(value: Any) -> dict[str, Any]:
    """Return `value` when it is a dict, else an empty dict.

    Wikipedia (or an intermediate proxy) can answer with a non-dict body —
    `null`, a JSON list, or an HTML error page parsed as a string — and every
    caller only needs safe `.get` chaining from that point on.
    """
    return value if isinstance(value, dict) else {}


async def _request_json(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if _client is not None:
        response = await _client.get(url, params=params)
    else:
        # No managed client (lifespan not running): fall back to a one-off
        # client so direct/scripted tool calls still work.
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
            response = await client.get(url, params=params)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        # A 200 body that is not JSON (HTML error page, Cloudflare
        # challenge, empty body) must degrade to "no data", not crash the
        # tool with an unhandled JSONDecodeError.
        return {}
    return _payload_dict(payload)


def _article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def _clean_snippet(value: Optional[str]) -> str:
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: dict[str, Any], language: str) -> str:
    data = _payload_dict(data)
    title = data.get("title") or "Untitled"
    extract = data.get("extract") or "No summary was returned for this article."
    description = data.get("description")
    content_urls = _payload_dict(data.get("content_urls"))
    desktop = _payload_dict(content_urls.get("desktop"))
    page_url = desktop.get("page") or _article_url(language, title)

    lines = [title]
    if description:
        lines.append(description)
    lines.extend(["", extract, "", page_url])
    return "\n".join(lines)


@app.get("/")
async def root():
    return HTMLResponse(
        """
        <html>
        <head><title>Wikipedia x Omi</title></head>
        <body style="font-family: sans-serif; max-width: 640px; margin: 48px auto; line-height: 1.5;">
            <h1>Wikipedia x Omi</h1>
            <p>Search Wikipedia, fetch article summaries, and discover random articles from Omi.</p>
            <p>No sign-in is required.</p>
        </body>
        </html>
        """
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "search_articles",
                "description": "Search Wikipedia articles by keyword. Use this when the user asks about a topic, person, place, event, concept, or wants matching encyclopedia articles.",
                "endpoint": "/tools/search_articles",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query, such as a topic, person, place, event, or concept.",
                        },
                        "language": {
                            "type": "string",
                            "description": "Wikipedia language code. Defaults to en.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return. Defaults to 5, maximum 10.",
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching Wikipedia...",
            },
            {
                "name": "get_article_summary",
                "description": "Get a concise Wikipedia summary for an exact article title. Use this when the user asks for an overview, definition, background, or key facts about a known topic.",
                "endpoint": "/tools/get_article_summary",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Exact or near-exact Wikipedia article title.",
                        },
                        "language": {
                            "type": "string",
                            "description": "Wikipedia language code. Defaults to en.",
                        },
                    },
                    "required": ["title"],
                },
                "auth_required": False,
                "status_message": "Fetching Wikipedia article...",
            },
            {
                "name": "get_random_article",
                "description": "Get a random Wikipedia article summary. Use this when the user wants to learn something random, discover a topic, or start an exploratory conversation.",
                "endpoint": "/tools/get_random_article",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "language": {
                            "type": "string",
                            "description": "Wikipedia language code. Defaults to en.",
                        }
                    },
                    "required": [],
                },
                "auth_required": False,
                "status_message": "Finding a random Wikipedia article...",
            },
        ]
    }


@app.post("/tools/search_articles", tags=["chat_tools"], response_model=ChatToolResponse)
async def search_articles(payload: dict[str, Any]):
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return ChatToolResponse(error="Missing required field: query")
    query = query.strip()

    language = _safe_language(payload.get("language"))
    limit = _safe_limit(payload.get("limit"))
    url = f"https://{language}.wikipedia.org/w/api.php"

    try:
        data = await _request_json(
            url,
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "format": "json",
                "utf8": "1",
            },
        )
        query_payload = _payload_dict(data.get("query"))
        search_list = query_payload.get("search")
        if not isinstance(search_list, list):
            search_list = []
        results = [item for item in search_list if isinstance(item, dict)][:limit]
        if not results:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        lines = [f"Wikipedia search results for '{query}':"]
        for index, item in enumerate(results, start=1):
            title = item.get("title") or "Untitled"
            snippet = _clean_snippet(item.get("snippet"))
            lines.append(f"\n{index}. {title}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append(f"   {_article_url(language, title)}")

        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia search failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia search failed: {exc}")


@app.post("/tools/get_article_summary", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_article_summary(payload: dict[str, Any]):
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return ChatToolResponse(error="Missing required field: title")
    title = title.strip()

    language = _safe_language(payload.get("language"))
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"

    try:
        data = await _request_json(url)
        if data.get("type") == "disambiguation":
            return ChatToolResponse(
                result=_format_summary(data, language)
                + "\n\nThis is a disambiguation page. Use search_articles for more specific matches."
            )
        return ChatToolResponse(result=_format_summary(data, language))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(error=f"No Wikipedia article found for '{title}'. Try search_articles first.")
        return ChatToolResponse(error=f"Wikipedia article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia article request failed: {exc}")


@app.post("/tools/get_random_article", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_random_article(payload: dict[str, Any]):
    language = _safe_language(payload.get("language"))
    url = f"https://{language}.wikipedia.org/w/api.php"

    try:
        data = await _request_json(
            url,
            {
                "action": "query",
                "list": "random",
                "rnnamespace": "0",
                "rnlimit": "1",
                "format": "json",
                "utf8": "1",
            },
        )
        query_payload = _payload_dict(data.get("query"))
        random_items = query_payload.get("random")
        if not isinstance(random_items, list):
            random_items = []
        if not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        first = random_items[0]
        title = first.get("title") if isinstance(first, dict) else None
        if not title:
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        summary = await _request_json(summary_url)
        return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
