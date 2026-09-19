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

_wikipedia_client: Optional[httpx.AsyncClient] = None


def _new_wikipedia_client() -> httpx.AsyncClient:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers)


async def _get_wikipedia_client() -> httpx.AsyncClient:
    global _wikipedia_client
    if _wikipedia_client is None or getattr(_wikipedia_client, "is_closed", False):
        _wikipedia_client = _new_wikipedia_client()
    return _wikipedia_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _wikipedia_client
    _wikipedia_client = _new_wikipedia_client()
    try:
        yield
    finally:
        if _wikipedia_client is not None:
            await _wikipedia_client.aclose()


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


async def _request_json(url: str, params: Optional[dict[str, Any]] = None) -> Any:
    client = await _get_wikipedia_client()
    response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def _clean_snippet(value: Any) -> str:
    if not value or not isinstance(value, str):
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: Any, language: str) -> str:
    if not isinstance(data, dict):
        return "No summary was returned for this article."

    title = data.get("title") if isinstance(data.get("title"), str) and data.get("title") else "Untitled"
    extract = (
        data.get("extract")
        if isinstance(data.get("extract"), str) and data.get("extract")
        else "No summary was returned for this article."
    )
    description = data.get("description") if isinstance(data.get("description"), str) else None

    content_urls = data.get("content_urls") if isinstance(data.get("content_urls"), dict) else {}
    desktop = content_urls.get("desktop") if isinstance(content_urls.get("desktop"), dict) else {}
    page_url = desktop.get("page") if isinstance(desktop.get("page"), str) else None
    if not page_url:
        page_url = _article_url(language, title)

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
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Missing required field: query")

    query = (payload.get("query") or "").strip() if isinstance(payload.get("query"), str) else ""
    if not query:
        return ChatToolResponse(error="Missing required field: query")

    language = _safe_language(payload.get("language") if isinstance(payload.get("language"), str) else None)
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
        if not isinstance(data, dict):
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        query_data = data.get("query")
        search_items = query_data.get("search") if isinstance(query_data, dict) else None
        if not isinstance(search_items, list) or not search_items:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        results = search_items[:limit]
        lines = [f"Wikipedia search results for '{query}':"]
        count = 0
        for item in results:
            if not isinstance(item, dict):
                continue
            count += 1
            title = item.get("title") or "Untitled"
            snippet = _clean_snippet(item.get("snippet"))
            lines.append(f"\n{count}. {title}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append(f"   {_article_url(language, title)}")

        if count == 0:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia search failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia search failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Wikipedia search failed: {exc}")


@app.post("/tools/get_article_summary", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_article_summary(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Missing required field: title")

    title = (payload.get("title") or "").strip() if isinstance(payload.get("title"), str) else ""
    if not title:
        return ChatToolResponse(error="Missing required field: title")

    language = _safe_language(payload.get("language") if isinstance(payload.get("language"), str) else None)
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"

    try:
        data = await _request_json(url)
        if not isinstance(data, dict):
            return ChatToolResponse(error=f"No Wikipedia article found for '{title}'. Try search_articles first.")
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
    except Exception as exc:
        return ChatToolResponse(error=f"Wikipedia article request failed: {exc}")


@app.post("/tools/get_random_article", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_random_article(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        payload = {}
    language = _safe_language(payload.get("language") if isinstance(payload.get("language"), str) else None)
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
        if not isinstance(data, dict):
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        query_data = data.get("query")
        random_items = query_data.get("random") if isinstance(query_data, dict) else None
        if not isinstance(random_items, list) or not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        first_item = random_items[0]
        if not isinstance(first_item, dict):
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        title = first_item.get("title")
        if not title or not isinstance(title, str):
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        summary = await _request_json(summary_url)
        return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
