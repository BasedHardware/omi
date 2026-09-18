"""
Wikipedia Integration App for Omi.

Provides chat tools for searching Wikipedia, reading concise article summaries,
and finding a random article for exploration.
"""

from html import unescape
import math
import re
from typing import Any, Optional
from urllib.parse import quote, unquote, urlsplit

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


def _safe_limit(limit: Any, default: int = 5, max_limit: int = MAX_LIMIT) -> int:
    """Safely coerces limit to an integer clamped between 1 and max_limit."""
    if limit is None or isinstance(limit, bool):
        return default
    try:
        if isinstance(limit, (int, float)):
            if not math.isfinite(limit):
                return default
            val = int(limit)
        elif isinstance(limit, str):
            cleaned = limit.strip()
            if not cleaned:
                return default
            val = int(float(cleaned)) if "." in cleaned else int(cleaned)
        else:
            return default
    except (ValueError, TypeError, OverflowError):
        return default
    return max(1, min(val, max_limit))


def _safe_language(language: Any) -> str:
    """Validates Wikipedia language subdomain string."""
    if not isinstance(language, str):
        return DEFAULT_LANGUAGE
    lang = language.strip().lower()
    if not lang:
        return DEFAULT_LANGUAGE
    cleaned = lang.replace("-", "")
    if not cleaned.isalpha() or len(lang) > 12:
        return DEFAULT_LANGUAGE
    return lang


def _clean_title(title: Any) -> str:
    """Normalizes Wikipedia title inputs, handling URLs, anchors, and escapes."""
    if not isinstance(title, str):
        return ""
    cleaned = title.strip()
    if not cleaned:
        return ""

    if "wikipedia.org/wiki/" in cleaned:
        try:
            parsed = urlsplit(cleaned)
            path = parsed.path
            if "/wiki/" in path:
                cleaned = path.split("/wiki/", 1)[1]
        except Exception:
            pass
    elif cleaned.startswith("/wiki/"):
        cleaned = cleaned.removeprefix("/wiki/")

    if "#" in cleaned:
        cleaned = cleaned.split("#", 1)[0]

    try:
        cleaned = unquote(cleaned)
    except Exception:
        pass

    cleaned = cleaned.replace("_", " ").strip()
    return cleaned


def _article_url(language: str, title: str) -> str:
    """Constructs a canonical Wikipedia article URL."""
    clean_title = (title or "Untitled").strip().replace(" ", "_")
    return f"https://{language}.wikipedia.org/wiki/{quote(clean_title, safe='()_:,.-')}"


def _clean_snippet(value: Any) -> str:
    """Strips HTML tags, invisible characters, and collapses whitespace."""
    if not isinstance(value, str) or not value.strip():
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: Any, language: str) -> str:
    """Formats a Wikipedia REST summary response with defensive NoneType guards."""
    if not isinstance(data, dict):
        return "No summary information available."

    title = str(data.get("title") or "").strip() or "Untitled"
    extract = str(data.get("extract") or "").strip() or "No summary was returned for this article."
    description = str(data.get("description") or "").strip()

    page_url = ""
    content_urls = data.get("content_urls")
    if isinstance(content_urls, dict):
        desktop = content_urls.get("desktop")
        if isinstance(desktop, dict):
            page_url = str(desktop.get("page") or "").strip()
    if not page_url:
        page_url = _article_url(language, title)

    lines = [title]
    if description:
        lines.append(description)
    lines.extend(["", extract, "", page_url])
    return "\n".join(lines)


async def _request_json(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Issues an HTTP GET request and returns the parsed JSON response."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        return {}
    return result


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
        return ChatToolResponse(error="Invalid request payload")

    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return ChatToolResponse(error="Missing required field: query")

    clean_q = query.strip()
    language = _safe_language(payload.get("language"))
    limit = _safe_limit(payload.get("limit"))
    url = f"https://{language}.wikipedia.org/w/api.php"

    try:
        data = await _request_json(
            url,
            {
                "action": "query",
                "list": "search",
                "srsearch": clean_q,
                "srlimit": limit,
                "format": "json",
                "utf8": "1",
            },
        )
        if not isinstance(data, dict):
            return ChatToolResponse(error="Invalid response received from Wikipedia API.")

        query_block = data.get("query")
        if not isinstance(query_block, dict):
            return ChatToolResponse(result=f"No Wikipedia articles found for '{clean_q}'.")

        raw_search = query_block.get("search")
        if not isinstance(raw_search, list):
            return ChatToolResponse(result=f"No Wikipedia articles found for '{clean_q}'.")

        valid_items = [item for item in raw_search if isinstance(item, dict)][:limit]
        if not valid_items:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{clean_q}'.")

        lines = [f"Wikipedia search results for '{clean_q}':"]
        for index, item in enumerate(valid_items, start=1):
            title = str(item.get("title") or "Untitled").strip()
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
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload")

    raw_title = payload.get("title")
    title = _clean_title(raw_title)
    if not title:
        return ChatToolResponse(error="Missing required field: title")

    language = _safe_language(payload.get("language"))
    encoded_title = quote(title.replace(" ", "_"), safe="")
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"

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
async def get_random_article(payload: Optional[dict[str, Any]] = None):
    if not isinstance(payload, dict):
        payload = {}

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
        query_block = data.get("query") if isinstance(data, dict) else None
        random_items = query_block.get("random") if isinstance(query_block, dict) else None
        if not isinstance(random_items, list) or not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        first_item = random_items[0] if isinstance(random_items[0], dict) else {}
        title = str(first_item.get("title") or "").strip()
        if not title:
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        encoded_title = quote(title.replace(" ", "_"), safe="")
        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        try:
            summary = await _request_json(summary_url)
            return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return ChatToolResponse(
                    result=f"Random Wikipedia article:\n\n{title}\n\n{_article_url(language, title)}"
                )
            raise
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
