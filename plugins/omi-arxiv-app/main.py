"""
arXiv Integration App for Omi.

Provides chat tools for searching arXiv papers, inspecting paper metadata, and
finding recent papers by author through the public arXiv API.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from html import unescape
import asyncio
import re
import time
from typing import Any, Optional, Union
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from models import (
    ChatToolResponse,
    GetPaperDetailsRequest,
    SearchAuthorRequest,
    SearchPapersRequest,
)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
REQUEST_TIMEOUT_SECONDS = 12.0
MAX_LIMIT = 10
# arXiv API Terms of Use require clients to wait at least three seconds between requests.
MIN_REQUEST_INTERVAL_SECONDS = 3.0
USER_AGENT = "omi-arxiv-app/1.0 (https://omi.me)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_arxiv_client: Optional[httpx.AsyncClient] = None
_arxiv_request_lock = asyncio.Lock()
_last_arxiv_request_at = 0.0


def _new_arxiv_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/xml"},
    )


async def _get_arxiv_client() -> httpx.AsyncClient:
    global _arxiv_client
    if _arxiv_client is None or _arxiv_client.is_closed:
        _arxiv_client = _new_arxiv_client()
    return _arxiv_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _arxiv_client
    _arxiv_client = _new_arxiv_client()
    try:
        yield
    finally:
        if _arxiv_client is not None and not _arxiv_client.is_closed:
            await _arxiv_client.aclose()


app = FastAPI(
    title="Omi arXiv Integration",
    description="Search arXiv papers and inspect metadata from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Ensure malformed JSON or invalid types return a standard 200 ChatToolResponse."""
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first_error.get("loc", []) if part != "body")
    message = first_error.get("msg", "invalid request payload")
    detail = f"{location}: {message}" if location else message
    response = ChatToolResponse(error=f"invalid tool request: {detail}")
    return JSONResponse(status_code=200, content=response.model_dump())


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = unescape(str(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _safe_limit(limit: Any, default: int = 5) -> int:
    if limit is None or limit == "":
        return default
    try:
        val = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(val, MAX_LIMIT))


def _safe_category(category: Any) -> str:
    value = _clean_text(category).lower()
    if not value:
        return ""
    if re.fullmatch(r"[a-z\-]+(\.[a-z]{2})?", value):
        return value[:32]
    return ""


def _safe_sort(sort_by: Any) -> str:
    value = _clean_text(sort_by)
    return value if value in {"relevance", "lastUpdatedDate", "submittedDate"} else "relevance"


def _safe_paper_id(value: Any) -> Optional[str]:
    candidate = _clean_text(value)
    if not candidate:
        return None
    candidate = candidate.removeprefix("https://arxiv.org/abs/")
    candidate = candidate.removeprefix("http://arxiv.org/abs/")
    candidate = candidate.removeprefix("arXiv:")
    versioned_new_id = re.match(r"^\d{4}\.\d{4,5}v\d+$", candidate)
    versioned_legacy_id = re.match(r"^[a-z\-]+(\.[A-Z]{2})?/\d{7}v\d+$", candidate)
    candidate = candidate.split("v", 1)[0] if versioned_new_id or versioned_legacy_id else candidate
    if re.fullmatch(r"\d{4}\.\d{4,5}", candidate) or re.fullmatch(r"[a-z\-]+(\.[A-Z]{2})?/\d{7}", candidate):
        return candidate
    return None


def _date_only(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return "unknown date"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except (ValueError, TypeError):
        return text[:10] if len(text) >= 10 else text


def _entry_text(entry: ET.Element, path: str) -> str:
    node = entry.find(path, ATOM_NS)
    return _clean_text(node.text if node is not None and node.text else "")


def _entry_authors(entry: ET.Element) -> list[str]:
    authors = []
    for author in entry.findall("atom:author", ATOM_NS):
        name = author.find("atom:name", ATOM_NS)
        text = _clean_text(name.text if name is not None and name.text else "")
        if text:
            authors.append(text)
    return authors


def _entry_categories(entry: ET.Element) -> list[str]:
    categories = []
    for category in entry.findall("atom:category", ATOM_NS):
        term = _clean_text(category.attrib.get("term"))
        if term:
            categories.append(term)
    return categories


def _entry_arxiv_id(entry: ET.Element) -> str:
    link = _entry_text(entry, "atom:id")
    raw_id = link.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")
    return raw_id or "unknown"


def _format_entry(entry: ET.Element, index: int) -> str:
    paper_id = _entry_arxiv_id(entry)
    title = _entry_text(entry, "atom:title") or "Untitled"
    all_authors = _entry_authors(entry)
    authors = ", ".join(all_authors[:5]) or "unknown authors"
    if len(all_authors) > 5:
        authors += ", et al."
    published = _date_only(_entry_text(entry, "atom:published"))
    updated = _date_only(_entry_text(entry, "atom:updated"))
    categories = ", ".join(_entry_categories(entry)[:4])
    summary = _entry_text(entry, "atom:summary")
    if len(summary) > 480:
        summary = summary[:480].rstrip() + "..."

    lines = [
        f"{index}. {title}",
        f"   arXiv: {paper_id} | Published: {published} | Updated: {updated}",
        f"   Authors: {authors}",
    ]
    if categories:
        lines.append(f"   Categories: {categories}")
    if summary:
        lines.append(f"   Summary: {summary}")
    lines.append(f"   URL: https://arxiv.org/abs/{paper_id}")
    return "\n".join(lines)


def _parse_entries(feed_xml: str) -> list[ET.Element]:
    if not feed_xml or not feed_xml.strip():
        return []
    root = ET.fromstring(feed_xml)
    return root.findall("atom:entry", ATOM_NS)


def _arxiv_http_error_message(exc: httpx.HTTPStatusError) -> str:
    if exc.response.status_code == 429:
        return "arXiv is rate limiting requests. Please try again in a moment."
    if exc.response.status_code == 503:
        return "arXiv is temporarily unavailable. Please try again shortly."
    return f"arXiv returned HTTP {exc.response.status_code}."


async def _request_arxiv(params: dict[str, Any]) -> str:
    global _last_arxiv_request_at
    client = await _get_arxiv_client()
    async with _arxiv_request_lock:
        elapsed = time.monotonic() - _last_arxiv_request_at
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        try:
            response = await client.get(ARXIV_API_URL, params=params)
        finally:
            _last_arxiv_request_at = time.monotonic()
    response.raise_for_status()
    return response.text


def _build_search_query(payload: Union[SearchPapersRequest, dict[str, Any], None]) -> Optional[str]:
    # httpx form-encodes request params itself, so this must return an
    # unencoded string. Pre-encoding here (e.g. with quote_plus) makes httpx
    # encode it a second time, turning "+" separators into a literal "%2B"
    # that arXiv does not treat as AND/space.
    if payload is None:
        data = {}
    elif isinstance(payload, SearchPapersRequest):
        data = payload.model_dump()
    elif isinstance(payload, dict):
        data = payload
    else:
        data = {}

    query = _clean_text(data.get("query"))
    title = _clean_text(data.get("title"))
    author = _clean_text(data.get("author"))
    category = _safe_category(data.get("category"))
    parts = []
    if query:
        parts.append(f"all:{query}")
    if title:
        parts.append(f"ti:{title}")
    if author:
        parts.append(f"au:{author}")
    if category:
        parts.append(f"cat:{category}")
    return " AND ".join(parts) if parts else None


@app.get("/")
async def root() -> HTMLResponse:
    return HTMLResponse(
        """
        <html>
        <head><title>arXiv x Omi</title></head>
        <body style="font-family: sans-serif; max-width: 640px; margin: 48px auto; line-height: 1.5;">
            <h1>arXiv x Omi</h1>
            <p>Search arXiv papers, fetch paper details, and find recent papers by author from Omi.</p>
            <p>No sign-in or API key is required.</p>
        </body>
        </html>
        """
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "search_papers",
                "description": "Search arXiv papers by topic, title, author, category, or a free-form research query.",
                "endpoint": "/tools/search_papers",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-form research topic or keyword query.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Optional title-specific search term.",
                        },
                        "author": {
                            "type": "string",
                            "description": "Optional author name filter.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Optional arXiv category such as cs.AI, cs.CL, stat.ML, or quant-ph.",
                        },
                        "sort_by": {
                            "type": "string",
                            "description": "Sort order: relevance, submittedDate, or lastUpdatedDate. Defaults to relevance.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum papers to return. Defaults to 5, maximum 10.",
                        },
                    },
                    "anyOf": [
                        {"required": ["query"]},
                        {"required": ["title"]},
                        {"required": ["author"]},
                        {"required": ["category"]},
                    ],
                },
                "auth_required": False,
                "status_message": "Searching arXiv...",
            },
            {
                "name": "get_paper_details",
                "description": "Get arXiv metadata and abstract for a specific paper ID.",
                "endpoint": "/tools/get_paper_details",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paper_id": {
                            "type": "string",
                            "description": "arXiv paper ID, such as 2401.01234 or cs/9901001. Accepts arxiv.org/abs URLs too.",
                        }
                    },
                    "required": ["paper_id"],
                },
                "auth_required": False,
                "status_message": "Fetching arXiv paper...",
            },
            {
                "name": "search_author",
                "description": "Find recent arXiv papers by a named author.",
                "endpoint": "/tools/search_author",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "author": {
                            "type": "string",
                            "description": "Author name to search for.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum papers to return. Defaults to 5, maximum 10.",
                        },
                    },
                    "required": ["author"],
                },
                "auth_required": False,
                "status_message": "Searching arXiv author...",
            },
        ]
    }


@app.post("/tools/search_papers", response_model=ChatToolResponse)
async def search_papers(payload: Union[SearchPapersRequest, dict[str, Any], None] = None) -> ChatToolResponse:
    if payload is None or isinstance(payload, dict):
        try:
            req = SearchPapersRequest(**(payload or {}))
        except Exception:
            req = None
    else:
        req = payload

    try:
        search_query = _build_search_query(req if req is not None else payload)
        if not search_query:
            return ChatToolResponse(error="Provide query, title, author, or category.")

        limit = _safe_limit(req.limit if req is not None else (payload.get("limit") if isinstance(payload, dict) else 5))
        sort_by = _safe_sort(req.sort_by if req is not None else (payload.get("sort_by") if isinstance(payload, dict) else "relevance"))
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": limit,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }

        entries = _parse_entries(await _request_arxiv(params))
        if not entries:
            return ChatToolResponse(result="No arXiv papers found.")
        return ChatToolResponse(
            result="arXiv paper results:\n\n"
            + "\n\n".join(_format_entry(entry, index + 1) for index, entry in enumerate(entries))
        )
    except ET.ParseError:
        return ChatToolResponse(error="arXiv returned an unreadable Atom feed.")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=_arxiv_http_error_message(exc))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"arXiv search failed: {exc}")


@app.post("/tools/get_paper_details", response_model=ChatToolResponse)
async def get_paper_details(payload: Union[GetPaperDetailsRequest, dict[str, Any], None] = None) -> ChatToolResponse:
    if payload is None:
        raw_paper_id = None
    elif isinstance(payload, GetPaperDetailsRequest):
        raw_paper_id = payload.paper_id
    elif isinstance(payload, dict):
        raw_paper_id = payload.get("paper_id")
    else:
        raw_paper_id = getattr(payload, "paper_id", None)

    paper_id = _safe_paper_id(raw_paper_id)
    if not paper_id:
        return ChatToolResponse(error="Provide a valid arXiv paper ID, such as 2401.01234.")

    try:
        entries = _parse_entries(await _request_arxiv({"id_list": paper_id, "max_results": 1}))
        if not entries:
            return ChatToolResponse(result=f"No arXiv paper found for {paper_id}.")
        return ChatToolResponse(result=_format_entry(entries[0], 1))
    except ET.ParseError:
        return ChatToolResponse(error="arXiv returned an unreadable Atom feed.")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=_arxiv_http_error_message(exc))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"arXiv details request failed: {exc}")


@app.post("/tools/search_author", response_model=ChatToolResponse)
async def search_author(payload: Union[SearchAuthorRequest, dict[str, Any], None] = None) -> ChatToolResponse:
    if payload is None:
        raw_author = None
        raw_limit = 5
    elif isinstance(payload, SearchAuthorRequest):
        raw_author = payload.author
        raw_limit = payload.limit
    elif isinstance(payload, dict):
        raw_author = payload.get("author")
        raw_limit = payload.get("limit")
    else:
        raw_author = getattr(payload, "author", None)
        raw_limit = getattr(payload, "limit", 5)

    author = _clean_text(raw_author)
    if not author:
        return ChatToolResponse(error="Missing required field: author")

    limit = _safe_limit(raw_limit)
    try:
        entries = _parse_entries(
            await _request_arxiv(
                {
                    "search_query": f"au:{author}",
                    "start": 0,
                    "max_results": limit,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
            )
        )
        if not entries:
            return ChatToolResponse(result=f"No arXiv papers found for author {author}.")
        return ChatToolResponse(
            result=f"Recent arXiv papers by {author}:\n\n"
            + "\n\n".join(_format_entry(entry, index + 1) for index, entry in enumerate(entries))
        )
    except ET.ParseError:
        return ChatToolResponse(error="arXiv returned an unreadable Atom feed.")
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=_arxiv_http_error_message(exc))
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"arXiv author search failed: {exc}")
