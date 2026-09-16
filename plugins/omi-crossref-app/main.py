"""Crossref Integration App for Omi.

Provides chat tools for searching scholarly works, retrieving publication metadata
by DOI, and finding recent publications by author via Crossref public APIs.
"""

from contextlib import asynccontextmanager
import html
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0
USER_AGENT = "omi-crossref-app/1.0.1 (https://omi.me; mailto:dev@omi.me)"


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manage pooled persistent HTTP client lifecycle."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
        app_instance.state.http_client = client
        yield


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.1",
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


def clamp_max_results(value: Any, default: int = 5) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, parsed))


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
    """Safely extract paper title whether stored as list of strings, single string, or missing."""
    if not isinstance(item, dict):
        return "Untitled"
    raw_title = item.get("title")
    if isinstance(raw_title, list):
        if raw_title and raw_title[0]:
            return clean(raw_title[0]) or "Untitled"
        return "Untitled"
    elif isinstance(raw_title, str) and raw_title.strip():
        return clean(raw_title.strip()) or "Untitled"
    return "Untitled"


def extract_year(item: Any) -> str:
    """Safely extract publication year from date-parts structures."""
    if not isinstance(item, dict):
        return ""
    for key in ("published-print", "published-online", "issued"):
        val = item.get(key)
        if isinstance(val, dict):
            date_parts = val.get("date-parts")
            if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], (list, tuple)) and date_parts[0]:
                return clean(date_parts[0][0])
    return ""


async def crossref_get(path: str, params: dict[str, Any], client: Optional[httpx.AsyncClient] = None) -> dict[str, Any]:
    """Execute GET request against Crossref API with client reuse and fallback."""
    cli = client or getattr(app.state, "http_client", None)
    if cli is not None and getattr(cli, "is_closed", False) is not True:
        response = await cli.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Crossref API returned invalid response format: expected JSON object, got {type(data).__name__}")
        return data

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as fallback_client:
        response = await fallback_client.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Crossref API returned invalid response format: expected JSON object, got {type(data).__name__}")
        return data


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
        if not isinstance(data, dict):
            return ChatToolResponse(error="Crossref request failed: invalid response structure")

        message = data.get("message")
        if not isinstance(message, dict):
            return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

        raw_items = message.get("items", [])
        if not isinstance(raw_items, list) or not raw_items:
            return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

        items = [x for x in raw_items if isinstance(x, dict)]
        if not items:
            return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

        lines = [f"Top {len(items)} Crossref results for '{query}':"]
        for idx, item in enumerate(items, 1):
            title = _extract_title(item)
            doi = clean(item.get("DOI"))
            year = extract_year(item)
            lines.append(f"{idx}. {title} ({year})")
            lines.append(f"   DOI: {doi}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Crossref request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    except ValueError as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")


@app.post("/tools/get_crossref_work", response_model=ChatToolResponse)
async def get_crossref_work(payload: GetWorkInput):
    normalized = payload.doi.strip()
    if "/" not in normalized:
        return ChatToolResponse(error="Invalid DOI format. Example: 10.1038/nphys1170")
    if ".." in normalized:
        return ChatToolResponse(error="Invalid DOI value.")

    try:
        data = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
        if not isinstance(data, dict):
            return ChatToolResponse(error="Crossref request failed: invalid response structure")

        item = data.get("message")
        if not isinstance(item, dict):
            return ChatToolResponse(error=f"No Crossref record found for DOI '{normalized}'.")

        title = _extract_title(item)
        publisher = clean(item.get("publisher"))
        doi_out = clean(item.get("DOI")) or normalized
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
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(error=f"No Crossref record found for DOI '{normalized}'.")
        return ChatToolResponse(error=f"Crossref request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    except ValueError as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")


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
        if not isinstance(data, dict):
            return ChatToolResponse(error="Crossref request failed: invalid response structure")

        message = data.get("message")
        if not isinstance(message, dict):
            return ChatToolResponse(result=f"No recent works found for author '{author}'.")

        raw_items = message.get("items", [])
        if not isinstance(raw_items, list) or not raw_items:
            return ChatToolResponse(result=f"No recent works found for author '{author}'.")

        items = [x for x in raw_items if isinstance(x, dict)]
        if not items:
            return ChatToolResponse(result=f"No recent works found for author '{author}'.")

        lines = [f"Recent works for '{author}':"]
        for idx, item in enumerate(items, 1):
            title = _extract_title(item)
            doi = clean(item.get("DOI"))
            year = extract_year(item)
            lines.append(f"{idx}. {title} ({year})")
            lines.append(f"   DOI: {doi}")
        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Crossref request failed with status {exc.response.status_code}.")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    except ValueError as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
