"""
Hacker News Integration App for Omi.

Provides chat tools for reading the Hacker News front page, searching stories,
and fetching an item with top-level comments.
"""

from html import unescape
import re
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


ALGOLIA_BASE_URL = "https://hn.algolia.com/api/v1"
REQUEST_TIMEOUT_SECONDS = 10
MAX_LIMIT = 20


app = FastAPI(
    title="Omi Hacker News Integration",
    description="Read and search Hacker News from Omi chat tools",
    version="1.0.0",
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


def _clean_text(value: Optional[str]) -> str:
    """Clean basic HTML entities/tags commonly returned by the HN API."""
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"</?(p|pre|blockquote|ul|ol|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<code[^>]*>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"</code>", "`", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_limit(limit: Any) -> int:
    if limit is None or limit == "":
        return 10
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return 10
    return max(1, min(limit, MAX_LIMIT))


async def _request_json(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{ALGOLIA_BASE_URL}{path}", params=params)
    response.raise_for_status()
    return response.json()


def _format_story(hit: dict[str, Any], index: int) -> str:
    title = hit.get("title") or hit.get("story_title") or "(untitled)"
    author = hit.get("author") or "unknown"
    points = hit.get("points") or 0
    comments = hit.get("num_comments") or 0
    object_id = hit.get("objectID") or hit.get("story_id")
    url = hit.get("url") or hit.get("story_url") or f"https://news.ycombinator.com/item?id={object_id}"

    return (
        f"{index}. {title}\n"
        f"   by {author} | {points} points | {comments} comments\n"
        f"   {url}\n"
        f"   HN: https://news.ycombinator.com/item?id={object_id}"
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
async def get_front_page(payload: dict[str, Any]):
    try:
        limit = _safe_limit(payload.get("limit"))
        data = await _request_json("/search", {"tags": "front_page", "hitsPerPage": limit})
        hits = data.get("hits", [])[:limit]

        if not hits:
            return ChatToolResponse(result="No Hacker News front page stories were returned.")

        stories = [_format_story(hit, index) for index, hit in enumerate(hits, start=1)]
        return ChatToolResponse(result="Current Hacker News front page:\n\n" + "\n\n".join(stories))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Hacker News request failed: {exc}")


@app.post("/tools/search_stories", tags=["chat_tools"], response_model=ChatToolResponse)
async def search_stories(payload: dict[str, Any]):
    query = (payload.get("query") or "").strip()
    if not query:
        return ChatToolResponse(error="Missing required field: query")

    try:
        limit = _safe_limit(payload.get("limit"))
        sort_by = payload.get("sort_by") or "relevance"
        endpoint = "/search_by_date" if sort_by == "date" else "/search"
        data = await _request_json(endpoint, {"query": query, "tags": "story", "hitsPerPage": limit})
        hits = data.get("hits", [])[:limit]

        if not hits:
            return ChatToolResponse(result=f"No Hacker News stories found for '{query}'.")

        stories = [_format_story(hit, index) for index, hit in enumerate(hits, start=1)]
        return ChatToolResponse(result=f"Hacker News stories for '{query}':\n\n" + "\n\n".join(stories))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Hacker News search failed: {exc}")


@app.post("/tools/get_discussion", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_discussion(payload: dict[str, Any]):
    item_id = payload.get("item_id")
    if item_id is None:
        return ChatToolResponse(error="Missing required field: item_id")

    try:
        comment_limit = _safe_limit(payload.get("comment_limit"))
        item = await _request_json(f"/items/{int(item_id)}")

        title = item.get("title") or "(untitled)"
        author = item.get("author") or "unknown"
        points = item.get("points") or 0
        url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
        comments = item.get("children", [])[:comment_limit]

        lines = [
            f"{title}",
            f"by {author} | {points} points",
            url,
            f"HN: https://news.ycombinator.com/item?id={item_id}",
        ]

        text = _clean_text(item.get("text"))
        if text:
            lines.extend(["", "Post text:", text])

        if comments:
            lines.append("")
            lines.append(f"Top {len(comments)} comments:")
            for index, comment in enumerate(comments, start=1):
                comment_author = comment.get("author") or "unknown"
                comment_text = _clean_text(comment.get("text"))
                if comment_text:
                    lines.append(f"\n{index}. {comment_author}: {comment_text[:1200]}")
        else:
            lines.extend(["", "No top-level comments returned."])

        return ChatToolResponse(result="\n".join(lines))
    except (ValueError, TypeError):
        return ChatToolResponse(error="item_id must be an integer")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Hacker News discussion request failed: {exc}")
