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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetArticleSummaryRequest,
    GetRandomArticleRequest,
    SearchArticlesRequest,
    normalize_language,
    normalize_limit,
)


REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "omi-wikipedia-app/1.0 (https://omi.me)"


def _build_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pool one upstream HTTP client on app.state for the app's lifetime."""
    app.state.http_client = _build_http_client()
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(
    title="Omi Wikipedia Integration",
    description="Search and read Wikipedia from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Return a structured ChatToolResponse instead of a bare 422."""
    message = "Invalid request payload."
    errors = exc.errors()
    if errors:
        location = errors[0].get("loc") or ()
        field = str(location[-1]) if location else "payload"
        if errors[0].get("type") == "missing":
            message = f"Missing required field: {field}"
        else:
            message = f"Invalid field: {field}"
    return JSONResponse(content=ChatToolResponse(error=message).model_dump())


def _dict_value(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


async def _request_json(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    client = getattr(app.state, "http_client", None)
    if client is None or getattr(client, "is_closed", False):
        client = _build_http_client()
        app.state.http_client = client
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def _clean_snippet(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: dict[str, Any], language: str) -> str:
    if not isinstance(data, dict):
        data = {}
    title = _text(data.get("title")) or "Untitled"
    extract = _text(data.get("extract")) or "No summary was returned for this article."
    description = _text(data.get("description"))
    desktop = _dict_value(_dict_value(data.get("content_urls")).get("desktop"))
    page_url = _text(desktop.get("page")) or _article_url(language, title)

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
async def search_articles(payload: SearchArticlesRequest):
    query = _text(payload.query).strip()
    if not query:
        return ChatToolResponse(error="Missing required field: query")

    language = normalize_language(payload.language)
    limit = normalize_limit(payload.limit)
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
        search = _list_value(_dict_value(data.get("query")).get("search"))
        results = [item for item in search if isinstance(item, dict)][:limit]
        if not results:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        lines = [f"Wikipedia search results for '{query}':"]
        for index, item in enumerate(results, start=1):
            title = _text(item.get("title")) or "Untitled"
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
async def get_article_summary(payload: GetArticleSummaryRequest):
    title = _text(payload.title).strip()
    if not title:
        return ChatToolResponse(error="Missing required field: title")

    language = normalize_language(payload.language)
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
async def get_random_article(payload: GetRandomArticleRequest):
    language = normalize_language(payload.language)
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
        random_items = [
            item
            for item in _list_value(_dict_value(data.get("query")).get("random"))
            if isinstance(item, dict)
        ]
        if not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        title = _text(random_items[0].get("title"))
        if not title:
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        summary = await _request_json(summary_url)
        return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
