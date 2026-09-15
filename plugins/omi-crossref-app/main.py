import html
import re
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.1",
    lifespan=lifespan,
)


def clamp_max_results(value: int) -> int:
    return max(1, min(10, value))


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


def extract_year(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    for key in ("published-print", "published-online", "issued"):
        container = item.get(key)
        if not isinstance(container, dict):
            continue
        date_parts = container.get("date-parts")
        if not isinstance(date_parts, (list, tuple)) or not date_parts:
            continue
        first = date_parts[0]
        if isinstance(first, (list, tuple)) and first:
            return clean(first[0])
    return ""


def _extract_title(item: Any) -> str:
    if not isinstance(item, dict):
        return "Untitled"
    title = item.get("title")
    if isinstance(title, str):
        return clean(title) or "Untitled"
    if isinstance(title, (list, tuple)) and title:
        return clean(title[0]) or "Untitled"
    return "Untitled"


def _extract_items(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    items = message.get("items")
    return items if isinstance(items, list) else []


async def _fetch_json(client: Any, path: str, params: dict[str, Any]) -> Any:
    response = await client.get(f"{CROSSREF_BASE}{path}", params=params)
    response.raise_for_status()
    return response.json()


async def crossref_get(path: str, params: dict[str, Any]) -> Any:
    client = getattr(getattr(app, "state", None), "http_client", None)
    if client is not None:
        return await _fetch_json(client, path, params)
    # Lifespan pool unavailable (e.g. direct invocation): fall back to a
    # per-request client rather than failing.
    async with httpx.AsyncClient(timeout=TIMEOUT) as fallback:
        return await _fetch_json(fallback, path, params)


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
        payload = await crossref_get(
            "/works",
            {"query": query, "rows": limited, "sort": "relevance", "order": "desc"},
        )
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    items = _extract_items(payload)
    if not items:
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items)} Crossref results for '{query}':"]
    for idx, item in enumerate(items, 1):
        record = item if isinstance(item, dict) else {}
        title = _extract_title(record)
        doi = clean(record.get("DOI"))
        year = extract_year(record)
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
        payload = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    item = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(item, dict) or not item:
        return ChatToolResponse(error=f"No Crossref work found for DOI '{normalized}'.")
    title = _extract_title(item)
    publisher = clean(item.get("publisher"))
    doi_out = clean(item.get("DOI"))
    url = clean(item.get("URL"))
    abstract = clean(item.get("abstract"))
    year = extract_year(item)

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
        payload = await crossref_get(
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
    items = _extract_items(payload)
    if not items:
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items, 1):
        record = item if isinstance(item, dict) else {}
        title = _extract_title(record)
        doi = clean(record.get("DOI"))
        year = extract_year(record)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))
