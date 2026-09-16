"""
Hacker News Integration App for Omi.

Provides chat tools for reading the Hacker News front page, searching stories,
and fetching an item with top-level comments.
"""

from contextlib import asynccontextmanager
from html import unescape
import math
import re
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    DiscussionRequest,
    FrontPageRequest,
    SearchStoriesRequest,
)

ALGOLIA_BASE_URL = "https://hn.algolia.com/api/v1"
REQUEST_TIMEOUT_SECONDS = 10
MAX_LIMIT = 20


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        app.state.client = client
        yield


app = FastAPI(
    title="Omi Hacker News Integration",
    description="Read and search Hacker News from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request payload")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


def _clean_text(value: Optional[str]) -> str:
    """Clean basic HTML entities/tags commonly returned by the HN API."""
    if not value or not isinstance(value, str):
        return ""

    # Strip actual provider markup before decoding entities. Decoding first turns
    # escaped literal text such as &lt;vector&gt; into apparent tags and deletes it.
    text = re.sub(r"</?(p|pre|blockquote|ul|ol|li)[^>]*>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<code[^>]*>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"</code>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_limit(limit: Any, default: int = 10) -> int:
    if limit is None or limit == "":
        return default
    try:
        val = float(limit)
        if not math.isfinite(val):
            return default
        limit_val = int(val)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(1, min(limit_val, MAX_LIMIT))


async def _request_json(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    client = getattr(app.state, "client", None)
    if client is not None and getattr(client, "is_closed", False) is not True:
        response = await client.get(f"{ALGOLIA_BASE_URL}{path}", params=params)
    else:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as fallback_client:
            response = await fallback_client.get(f"{ALGOLIA_BASE_URL}{path}", params=params)
    response.raise_for_status()
    return response.json()


def _format_story(hit: Any, index: int) -> str:
    if not isinstance(hit, dict):
        return f"{index}. (untitled)\n   HN: https://news.ycombinator.com"
    title = hit.get("title") or hit.get("story_title") or "(untitled)"
    author = hit.get("author") or "unknown"
    points = hit.get("points") or 0
    comments = hit.get("num_comments") or 0
    object_id = hit.get("objectID") or hit.get("story_id")
    hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else "https://news.ycombinator.com"
    url = hit.get("url") or hit.get("story_url") or hn_url

    return (
        f"{index}. {title}\n"
        f"   by {author} | {points} points | {comments} comments\n"
        f"   {url}\n"
        f"   HN: {hn_url}"
    )


@app.get("/")
async def root():
    return HTMLResponse(
        """
        <html>
        <head><title>Hacker News x Omi</title></head>
        <body style="font-family: sans-serif; max-width: 640px; margin: 48px auto; line-height: 1.5;">
            <h1>Hacker News x Omi</h1>
            <p>Read the Hacker News front page, search stories, and fetch discussions from Omi.</p>
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
                "name": "get_front_page",
                "description": "Get current Hacker News front page stories. Use this when the user asks for top tech/startup/programming news or Hacker News headlines.",
                "endpoint": "/tools/get_front_page",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum stories to return. Defaults to 10, maximum 20.",
                        }
                    },
                    "required": [],
                },
                "auth_required": False,
                "status_message": "Fetching Hacker News front page...",
            },
            {
                "name": "search_stories",
                "description": "Search Hacker News stories and discussions by keyword. Use this when the user mentions a company, project, technology, product, person, or topic and wants relevant HN discussions.",
                "endpoint": "/tools/search_stories",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query, such as a project name, company, technology, or topic.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results to return. Defaults to 10, maximum 20.",
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["relevance", "date"],
                            "description": "Sort by relevance or date. Defaults to relevance.",
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching Hacker News...",
            },
            {
                "name": "get_discussion",
                "description": "Fetch a Hacker News item and its top-level comments. Use this when the user wants details, comments, or discussion for a specific HN item ID.",
                "endpoint": "/tools/get_discussion",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {
                            "type": "integer",
                            "description": "Hacker News item ID.",
                        },
                        "comment_limit": {
                            "type": "integer",
                            "description": "Maximum top-level comments to include. Defaults to 5, maximum 20.",
                        },
                    },
                    "required": ["item_id"],
                },
                "auth_required": False,
                "status_message": "Fetching Hacker News discussion...",
            },
        ]
    }


@app.post("/tools/get_front_page", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_front_page(payload: Optional[FrontPageRequest] = None):
    req = payload if payload is not None else FrontPageRequest()

    try:
        limit = _safe_limit(req.limit, default=10)
        data = await _request_json("/search", {"tags": "front_page", "hitsPerPage": limit})
        if not isinstance(data, dict):
            return ChatToolResponse(result="No Hacker News front page stories were returned.")
        raw_hits = data.get("hits")
        hits = (raw_hits if isinstance(raw_hits, list) else [])[:limit]
        valid_hits = [h for h in hits if isinstance(h, dict)]

        if not valid_hits:
            return ChatToolResponse(result="No Hacker News front page stories were returned.")

        stories = [_format_story(hit, index) for index, hit in enumerate(valid_hits, start=1)]
        return ChatToolResponse(result="Current Hacker News front page:\n\n" + "\n\n".join(stories))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Hacker News request failed: {exc}")


@app.post("/tools/search_stories", tags=["chat_tools"], response_model=ChatToolResponse)
async def search_stories(payload: SearchStoriesRequest):
    query = (payload.query or "").strip()
    if not query:
        return ChatToolResponse(error="Missing required field: query")

    try:
        limit = _safe_limit(payload.limit, default=10)
        sort_by = payload.sort_by or "relevance"
        endpoint = "/search_by_date" if sort_by == "date" else "/search"
        data = await _request_json(endpoint, {"query": query, "tags": "story", "hitsPerPage": limit})
        if not isinstance(data, dict):
            return ChatToolResponse(result=f"No Hacker News stories found for '{query}'.")
        raw_hits = data.get("hits")
        hits = (raw_hits if isinstance(raw_hits, list) else [])[:limit]
        valid_hits = [h for h in hits if isinstance(h, dict)]

        if not valid_hits:
            return ChatToolResponse(result=f"No Hacker News stories found for '{query}'.")

        stories = [_format_story(hit, index) for index, hit in enumerate(valid_hits, start=1)]
        return ChatToolResponse(result=f"Hacker News stories for '{query}':\n\n" + "\n\n".join(stories))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Hacker News search failed: {exc}")


@app.post("/tools/get_discussion", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_discussion(payload: DiscussionRequest):
    if payload.item_id is None:
        return ChatToolResponse(error="Missing required field: item_id")
    if payload.item_id <= 0:
        return ChatToolResponse(error="item_id must be a positive integer")

    try:
        comment_limit = _safe_limit(payload.comment_limit, default=5)
        item = await _request_json(f"/items/{payload.item_id}")
        if not isinstance(item, dict) or not item:
            return ChatToolResponse(result=f"No Hacker News discussion found for item {payload.item_id}.")

        title = item.get("title") or item.get("story_title") or "(untitled)"
        author = item.get("author") or "unknown"
        points = item.get("points") or 0
        url = item.get("url") or item.get("story_url") or f"https://news.ycombinator.com/item?id={payload.item_id}"

        raw_children = item.get("children")
        children = (raw_children if isinstance(raw_children, list) else [])
        valid_comments = [c for c in children if isinstance(c, dict)]
        top_comments = valid_comments[:comment_limit]

        lines = [
            f"{title}",
            f"by {author} | {points} points",
            url,
            f"HN: https://news.ycombinator.com/item?id={payload.item_id}",
        ]

        text = _clean_text(item.get("text"))
        if text:
            lines.extend(["", "Post text:", text])

        formatted_comments = []
        for index, comment in enumerate(top_comments, start=1):
            comment_author = comment.get("author") or "unknown"
            comment_text = _clean_text(comment.get("text"))
            if comment_text:
                formatted_comments.append(f"\n{index}. {comment_author}: {comment_text[:1200]}")

        if formatted_comments:
            lines.append("")
            lines.append(f"Top {len(formatted_comments)} comments:")
            lines.extend(formatted_comments)
        else:
            lines.extend(["", "No top-level comments returned."])

        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and getattr(exc.response, "status_code", None) == 404:
            return ChatToolResponse(error=f"Hacker News item {payload.item_id} not found.")
        return ChatToolResponse(error=f"Hacker News discussion request failed: {exc}")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Hacker News discussion request failed: {exc}")
