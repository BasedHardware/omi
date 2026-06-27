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
from typing import Any, Optional
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


ARXIV_API_URL = "https://export.arxiv.org/api/query"
REQUEST_TIMEOUT_SECONDS = 12
MAX_LIMIT = 10
MIN_REQUEST_INTERVAL_SECONDS = 0.35
USER_AGENT = "omi-arxiv-app/1.0 (https://omi.me)"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_arxiv_client: Optional[httpx.AsyncClient] = None
_arxiv_request_lock = asyncio.Lock()
_last_arxiv_request_at = 0.0


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


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
        if _arxiv_client is not None:
            await _arxiv_client.aclose()


app = FastAPI(
    title="Omi arXiv Integration",
    description="Search arXiv papers and inspect metadata from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


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
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, MAX_LIMIT))


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
    except ValueError:
        return text[:10]


def _entry_text(entry: ET.Element, path: str) -> str:
    node = entry.find(path, ATOM_NS)
    return _clean_text(node.text if node is not None else "")


def _entry_authors(entry: ET.Element) -> list[str]:
    authors = []
    for author in entry.findall("atom:author", ATOM_NS):
        name = author.find("atom:name", ATOM_NS)
        text = _clean_text(name.text if name is not None else "")
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
    return link.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")


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
        response = await client.get(ARXIV_API_URL, params=params)
        _last_arxiv_request_at = time.monotonic()
    response.raise_for_status()
    return response.text


def _build_search_query(payload: dict[str, Any]) -> Optional[str]:
    query = _clean_text(payload.get("query"))
    title = _clean_text(payload.get("title"))
    author = _clean_text(payload.get("author"))
    category = _safe_category(payload.get("category"))
    parts = []
    if query:
        parts.append(f"all:{quote_plus(query)}")
    if title:
        parts.append(f"ti:{quote_plus(title)}")
    if author:
        parts.append(f"au:{quote_plus(author)}")
    if category:
        parts.append(f"cat:{category}")
    return "+AND+".join(parts) if parts else None


@app.get("/")
async def root():
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
async def health():
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
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
async def search_papers(payload: dict[str, Any]):
    search_query = _build_search_query(payload)
    if not search_query:
        return ChatToolResponse(error="Provide query, title, author, or category.")

    limit = _safe_limit(payload.get("limit"))
    sort_by = _safe_sort(payload.get("sort_by"))
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": limit,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }

    try:
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
async def get_paper_details(payload: dict[str, Any]):
    paper_id = _safe_paper_id(payload.get("paper_id"))
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
async def search_author(payload: dict[str, Any]):
    author = _clean_text(payload.get("author"))
    if not author:
        return ChatToolResponse(error="Missing required field: author")

    limit = _safe_limit(payload.get("limit"))
    try:
        entries = _parse_entries(
            await _request_arxiv(
                {
                    "search_query": f"au:{quote_plus(author)}",
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
