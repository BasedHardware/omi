from contextlib import asynccontextmanager
import html
import re
from typing import Any, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0
USER_AGENT = "OmiCrossrefApp/1.0 (https://github.com/BasedHardware/omi; mailto:support@omi.me)"

_crossref_client: Optional[httpx.AsyncClient] = None


def _new_crossref_client() -> httpx.AsyncClient:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    return httpx.AsyncClient(timeout=TIMEOUT, headers=headers)


async def _get_crossref_client() -> httpx.AsyncClient:
    global _crossref_client
    if _crossref_client is None or _crossref_client.is_closed:
        _crossref_client = _new_crossref_client()
    return _crossref_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _crossref_client
    _crossref_client = _new_crossref_client()
    try:
        yield
    finally:
        if _crossref_client is not None:
            await _crossref_client.aclose()


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.1",
    lifespan=lifespan,
)


def clamp_max_results(value: int) -> int:
    try:
        val = int(value)
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, val))


_JATS_TAG = re.compile(r"</?jats:[^>]+>")
# Closing tags are never inequalities; strip them unconditionally.
_CLOSE_TAG = re.compile(r"</[a-zA-Z][^>]*>")
# Open tags need a non-word char before "<" so inequalities like a<b survive.
_OPEN_TAG = re.compile(r"(?<![A-Za-z0-9_])<[a-zA-Z][^>]*>")


def clean(text: Any) -> str:
    if text is None:
        return ""
    value = html.unescape(str(text)).strip()
    # Crossref abstracts often carry JATS markup; chat tools want plain text.
    value = _JATS_TAG.sub("", value)
    value = _CLOSE_TAG.sub("", value)
    value = _OPEN_TAG.sub("", value)
    return value.strip()


def _extract_title(item: Any) -> str:
    if not isinstance(item, dict):
        return "Untitled"
    titles = item.get("title")
    if isinstance(titles, list) and titles:
        cleaned = clean(titles[0])
        if cleaned:
            return cleaned
    elif isinstance(titles, str):
        cleaned = clean(titles)
        if cleaned:
            return cleaned
    return "Untitled"


def extract_year(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("published-print", "published-online", "issued"):
        date_info = item.get(key)
        if isinstance(date_info, dict):
            date_parts = date_info.get("date-parts")
            if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
                cleaned = clean(date_parts[0][0])
                if cleaned:
                    return cleaned
    return ""


async def crossref_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    client = await _get_crossref_client()
    response = await client.get(f"{CROSSREF_BASE}{path}", params=params)
    response.raise_for_status()
    return response.json()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/tools")
async def tools():
    return {
        "tools": [
            {
                "name": "search_crossref_works",
                "description": "Search scholarly works by keyword via Crossref",
                "parameters": {
                    "query": {"type": "string", "description": "Search keyword(s)"},
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-10)",
                        "default": 5,
                    },
                },
            },
            {
                "name": "get_crossref_work",
                "description": "Get details for a specific work by DOI",
                "parameters": {
                    "doi": {
                        "type": "string",
                        "description": "DOI, e.g. 10.1038/nphys1170",
                    }
                },
            },
            {
                "name": "get_crossref_works_by_author",
                "description": "Find recent works for an author name",
                "parameters": {
                    "author": {"type": "string", "description": "Author name"},
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-10)",
                        "default": 5,
                    },
                },
            },
        ]
    }


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    return {
        "tools": [
            {
                "name": "search_crossref_works",
                "description": "Search scholarly works by keyword via Crossref",
                "endpoint": "/tools/search_crossref_works",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword(s)"},
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results (1-10)",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": False,
                "status_message": "Searching Crossref...",
            },
            {
                "name": "get_crossref_work",
                "description": "Get details for a specific work by DOI",
                "endpoint": "/tools/get_crossref_work",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "doi": {
                            "type": "string",
                            "description": "DOI, e.g. 10.1038/nphys1170",
                        }
                    },
                    "required": ["doi"],
                },
                "auth_required": False,
                "status_message": "Fetching Crossref work...",
            },
            {
                "name": "get_crossref_works_by_author",
                "description": "Find recent works for an author name",
                "endpoint": "/tools/get_crossref_works_by_author",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "author": {"type": "string", "description": "Author name"},
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results (1-10)",
                            "default": 5,
                        },
                    },
                    "required": ["author"],
                },
                "auth_required": False,
                "status_message": "Fetching author works...",
            },
        ]
    }


@app.post("/tools/search_crossref_works", response_model=ChatToolResponse)
async def search_crossref_works(payload: SearchWorksInput):
    query = payload.query.strip()
    if len(query) < 2:
        return ChatToolResponse(error="Query must be at least 2 characters.")
    limited = clamp_max_results(payload.max_results)
    try:
        data = await crossref_get(
            "/works",
            {"query": query, "rows": limited, "sort": "relevance", "order": "desc"},
        )
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    if not isinstance(data, dict):
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    message = data.get("message")
    if not isinstance(message, dict):
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    items = message.get("items")
    if not isinstance(items, list) or not items:
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items[:limited])} Crossref results for '{query}':"]
    for idx, item in enumerate(items[:limited], 1):
        title = _extract_title(item)
        doi = clean(item.get("DOI")) if isinstance(item, dict) else ""
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_crossref_work", response_model=ChatToolResponse)
async def get_crossref_work(payload: GetWorkInput):
    normalized = payload.doi.strip()
    if "/" not in normalized:
        return ChatToolResponse(error="Invalid DOI format. Example: 10.1038/nphys1170")
    if ".." in normalized:
        return ChatToolResponse(error="Invalid DOI value.")

    try:
        data = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    if not isinstance(data, dict):
        return ChatToolResponse(result=f"No Crossref details found for DOI {normalized}.")

    message = data.get("message")
    if not isinstance(message, dict) or not message:
        return ChatToolResponse(result=f"No Crossref details found for DOI {normalized}.")

    title = _extract_title(message)
    publisher = clean(message.get("publisher"))
    doi_out = clean(message.get("DOI")) or normalized
    url = clean(message.get("URL"))
    abstract = clean(message.get("abstract"))
    year = extract_year(message)

    parts = [
        f"Title: {title}",
        f"DOI: {doi_out}",
        f"Year: {year}",
        f"Publisher: {publisher}",
        f"URL: {url}",
    ]
    if abstract:
        parts.append(f"Abstract: {abstract[:1200]}")
    return ChatToolResponse(result="\n".join(parts))


@app.post("/tools/get_crossref_works_by_author", response_model=ChatToolResponse)
async def get_crossref_works_by_author(payload: AuthorWorksInput):
    author = payload.author.strip()
    if len(author) < 2:
        return ChatToolResponse(error="Author must be at least 2 characters.")
    limited = clamp_max_results(payload.max_results)
    try:
        data = await crossref_get(
            "/works",
            {
                "query.author": author,
                "rows": limited,
                "sort": "published",
                "order": "desc",
            },
        )
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    if not isinstance(data, dict):
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    message = data.get("message")
    if not isinstance(message, dict):
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    items = message.get("items")
    if not isinstance(items, list) or not items:
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items[:limited], 1):
        title = _extract_title(item)
        doi = clean(item.get("DOI")) if isinstance(item, dict) else ""
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))
