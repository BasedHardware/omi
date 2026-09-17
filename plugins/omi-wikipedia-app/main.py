"""
Wikipedia Integration App for Omi.

Provides chat tools for searching Wikipedia, reading concise article summaries,
and finding a random article for exploration.
"""

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


app = FastAPI(
    title="Omi Wikipedia Integration",
    description="Search and read Wikipedia from Omi chat tools",
    version="1.0.0",
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


def _safe_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _safe_language(language: Any) -> str:
    lang = (_safe_text(language) or DEFAULT_LANGUAGE).strip().lower()
    if not lang.replace("-", "").isalpha() or len(lang) > 12:
        return DEFAULT_LANGUAGE
    return lang


async def _request_json(url: str, params: Optional[dict[str, Any]] = None) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise httpx.HTTPError("Wikipedia returned an invalid JSON response") from exc


def _article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _clean_snippet(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: Any, language: str) -> str:
    if not isinstance(data, dict):
        data = {}

    title = _safe_text(data.get("title")) or "Untitled"
    extract = _safe_text(data.get("extract")) or "No summary was returned for this article."
    description = _safe_text(data.get("description"))

    content_urls = data.get("content_urls")
    desktop = content_urls.get("desktop") if isinstance(content_urls, dict) else None
    page = desktop.get("page") if isinstance(desktop, dict) else None
    page_url = _safe_text(page) or _article_url(language, title)

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
    query = _safe_text(payload.get("query")).strip()
    if not query:
        return ChatToolResponse(error="Missing required field: query")

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
        if not isinstance(data, dict):
            return ChatToolResponse(error="Wikipedia search returned an unexpected response. Please try again.")

        query_data = data.get("query")
        if query_data is None:
            query_data = {}
        if not isinstance(query_data, dict):
            return ChatToolResponse(error="Wikipedia search returned an unexpected response. Please try again.")

        raw_results = query_data.get("search")
        if raw_results is None:
            raw_results = []
        if not isinstance(raw_results, list):
            return ChatToolResponse(error="Wikipedia search returned an unexpected response. Please try again.")

        results = _dict_items(raw_results)[:limit]
        if not results:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        lines = [f"Wikipedia search results for '{query}':"]
        for index, item in enumerate(results, start=1):
            title = _safe_text(item.get("title")) or "Untitled"
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
    title = _safe_text(payload.get("title")).strip()
    if not title:
        return ChatToolResponse(error="Missing required field: title")

    language = _safe_language(payload.get("language"))
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
        if not isinstance(data, dict):
            return ChatToolResponse(error="Wikipedia random article request returned an unexpected response.")

        query_data = data.get("query")
        if query_data is None:
            query_data = {}
        if not isinstance(query_data, dict):
            return ChatToolResponse(error="Wikipedia random article request returned an unexpected response.")

        raw_items = query_data.get("random")
        if raw_items is None:
            raw_items = []
        if not isinstance(raw_items, list):
            return ChatToolResponse(error="Wikipedia random article request returned an unexpected response.")

        random_items = _dict_items(raw_items)
        if not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        title = _safe_text(random_items[0].get("title"))
        if not title:
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        summary = await _request_json(summary_url)
        if not isinstance(summary, dict):
            return ChatToolResponse(error="Wikipedia random article request returned an unexpected response.")
        return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
