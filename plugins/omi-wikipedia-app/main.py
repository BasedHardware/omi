"""Wikipedia Integration App for Omi.

Provides chat tools for searching Wikipedia, reading concise article summaries,
and finding a random article for exploration.
"""

from contextlib import asynccontextmanager
from html import unescape
import re
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetArticleSummaryRequest,
    GetRandomArticleRequest,
    SearchArticlesRequest,
    normalize_language,
)

REQUEST_TIMEOUT_SECONDS = 10.0
MAX_LIMIT = 10
DEFAULT_LANGUAGE = "en"
USER_AGENT = "omi-wikipedia-app/1.0 (https://omi.me)"


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Omi Wikipedia Integration",
    description="Search and read Wikipedia from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


def _safe_limit(limit: Any) -> int:
    if limit is None or limit == "":
        return 5
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return 5
    return max(1, min(limit, MAX_LIMIT))


def _safe_language(language: Optional[str]) -> str:
    return normalize_language(language)


async def _request_json(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute asynchronous GET request with persistent client reuse and fallback."""
    client = getattr(app.state, "http_client", None)

    async def _do_get(cli: httpx.AsyncClient) -> Dict[str, Any]:
        response = await cli.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid response received from Wikipedia API.")
        return data

    if client is not None and getattr(client, "is_closed", False) is not True:
        return await _do_get(client)

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as fallback_client:
        return await _do_get(fallback_client)


def _article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"


def _clean_snippet(value: Optional[str]) -> str:
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: Any, language: str) -> str:
    if not isinstance(data, dict):
        return "No summary was returned for this article."
    title = data.get("title") or "Untitled"
    extract = data.get("extract") or "No summary was returned for this article."
    description = data.get("description")

    content_urls = data.get("content_urls")
    desktop_urls = content_urls.get("desktop") if isinstance(content_urls, dict) else None
    page_url = (desktop_urls.get("page") if isinstance(desktop_urls, dict) else None) or _article_url(language, title)

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
async def search_articles(req: SearchArticlesRequest) -> ChatToolResponse:
    query = req.query.strip()
    if not query:
        return ChatToolResponse(error="Missing required field: query")

    language = _safe_language(req.language)
    limit = req.limit
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
            return ChatToolResponse(error="Invalid response received from Wikipedia API.")

        query_dict = data.get("query")
        if not isinstance(query_dict, dict):
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        raw_results = query_dict.get("search", [])
        if not isinstance(raw_results, list) or not raw_results:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        valid_results = [item for item in raw_results if isinstance(item, dict)]
        if not valid_results:
            return ChatToolResponse(result=f"No Wikipedia articles found for '{query}'.")

        selected = valid_results[:limit]
        lines = [f"Wikipedia search results for '{query}':"]
        for index, item in enumerate(selected, start=1):
            title = item.get("title") or "Untitled"
            snippet = _clean_snippet(item.get("snippet"))
            lines.append(f"\n{index}. {title}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append(f"   {_article_url(language, title)}")

        return ChatToolResponse(result="\n".join(lines))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia search failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia search failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error searching Wikipedia: {exc}")


@app.post("/tools/get_article_summary", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_article_summary(req: GetArticleSummaryRequest) -> ChatToolResponse:
    title = req.title.strip()
    if not title:
        return ChatToolResponse(error="Missing required field: title")

    language = _safe_language(req.language)
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"

    try:
        data = await _request_json(url)
        if not isinstance(data, dict):
            return ChatToolResponse(error="Invalid summary data received from Wikipedia API.")

        if data.get("type") == "disambiguation":
            return ChatToolResponse(
                result=_format_summary(data, language)
                + "\n\nThis is a disambiguation page. Use search_articles for more specific matches."
            )
        return ChatToolResponse(result=_format_summary(data, language))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(error=f"No Wikipedia article found for '{title}'. Try search_articles first.")
        return ChatToolResponse(error=f"Wikipedia article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia article request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error fetching Wikipedia summary: {exc}")


@app.post("/tools/get_random_article", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_random_article(req: Optional[GetRandomArticleRequest] = None) -> ChatToolResponse:
    language = _safe_language(req.language if req else None)
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
            return ChatToolResponse(error="Invalid response received from Wikipedia API.")

        query_dict = data.get("query")
        if not isinstance(query_dict, dict):
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        random_items = query_dict.get("random", [])
        if not isinstance(random_items, list) or not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        first_item = random_items[0]
        if not isinstance(first_item, dict) or not first_item.get("title"):
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        title = first_item["title"]
        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
        summary = await _request_json(summary_url)
        if not isinstance(summary, dict):
            return ChatToolResponse(error="Invalid response received from Wikipedia API.")
        return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
    except ValueError as exc:
        return ChatToolResponse(error=str(exc))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error fetching random Wikipedia article: {exc}")
