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


# Wikipedia language subdomains are ASCII-only BCP-47-style codes such as "en",
# "simple", "zh-min-nan" and "be-tarask".  The pattern is deliberately strict:
# the value is interpolated into the request hostname, so anything outside this
# alphabet must fall back to the default rather than steer the request.
_LANGUAGE_RE = re.compile(r"^[a-z]{2,10}(?:-[a-z0-9]{2,8})*$")
MAX_LANGUAGE_LENGTH = 12
MAX_TITLE_LENGTH = 255


def _coerce_text(value: Any) -> str:
    """Return stripped text for string input and "" for every other type.

    The Omi backend forwards tool arguments as a flat JSON object, so a caller
    can send a number, list or object where a string is expected.  Returning ""
    lets the endpoint answer with its own validation error instead of raising
    AttributeError and surfacing HTTP 500.
    """
    if isinstance(value, str):
        return value.strip()
    return ""


def _safe_limit(limit: Any) -> int:
    if limit is None or limit == "":
        return 5
    if isinstance(limit, bool):
        return 5
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return 5
    return max(1, min(limit, MAX_LIMIT))


def _safe_language(language: Any) -> str:
    """Validate a Wikipedia language code before it becomes a hostname label.

    ``str.isalpha()`` accepts any Unicode letter, so the previous check let
    values through that IDNA-encode into a different host: "ss" for "ß",
    or the punycode label "xn--l1ae" for Cyrillic look-alikes.  Only lowercase
    ASCII codes matching a real Wikipedia subdomain are accepted now.

    The ASCII test precedes casefolding on purpose: ``str.lower()`` folds a
    few non-ASCII letters into ASCII, so U+212A KELVIN SIGN would otherwise
    reach the pattern as "k" and let a non-ASCII value name a language code.
    """
    raw = _coerce_text(language)
    if not raw.isascii():
        return DEFAULT_LANGUAGE
    lang = raw.lower()
    if not lang:
        return DEFAULT_LANGUAGE
    if len(lang) > MAX_LANGUAGE_LENGTH or not _LANGUAGE_RE.fullmatch(lang):
        return DEFAULT_LANGUAGE
    return lang


def _encode_title(title: str) -> str:
    """Percent-encode an article title as exactly one URL path segment.

    ``quote`` defaults to ``safe="/"``, which left separators intact and allowed
    a title such as "../../../../w/api.php" to walk out of the summary path and
    address a different Wikipedia endpoint.  Encoding with ``safe=""`` keeps the
    title inside its own segment.
    """
    return quote(title.replace(" ", "_"), safe="")


async def _request_json(url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _article_url(language: str, title: str) -> str:
    return f"https://{language}.wikipedia.org/wiki/{_encode_title(title)}"


def _clean_snippet(value: Optional[str]) -> str:
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _format_summary(data: dict[str, Any], language: str) -> str:
    title = data.get("title") or "Untitled"
    extract = data.get("extract") or "No summary was returned for this article."
    description = data.get("description")
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page") or _article_url(language, title)

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
    query = _coerce_text(payload.get("query"))
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
        results = data.get("query", {}).get("search", [])[:limit]
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
    except Exception:
        return ChatToolResponse(error="Wikipedia search failed.")


@app.post("/tools/get_article_summary", tags=["chat_tools"], response_model=ChatToolResponse)
async def get_article_summary(payload: dict[str, Any]):
    title = _coerce_text(payload.get("title"))
    if not title:
        return ChatToolResponse(error="Missing required field: title")
    if len(title) > MAX_TITLE_LENGTH:
        return ChatToolResponse(error="Article title is too long.")

    language = _safe_language(payload.get("language"))
    url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{_encode_title(title)}"

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
    except Exception:
        return ChatToolResponse(error="Wikipedia article request failed.")


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
        random_items = data.get("query", {}).get("random", [])
        if not random_items:
            return ChatToolResponse(result="No random Wikipedia article was returned.")

        title = random_items[0].get("title")
        if not title:
            return ChatToolResponse(result="Wikipedia returned a random article without a title.")

        summary_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{_encode_title(title)}"
        summary = await _request_json(summary_url)
        return ChatToolResponse(result="Random Wikipedia article:\n\n" + _format_summary(summary, language))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Wikipedia random article request failed with status {exc.response.status_code}.")
    except Exception:
        return ChatToolResponse(error="Wikipedia random article request failed.")
