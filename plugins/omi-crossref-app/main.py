import html
import re
import unicodedata
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0
# Polite-pool identification so Crossref applies cooperative rate limits.
USER_AGENT = "omi-crossref-app/1.0.2 (https://github.com/BasedHardware/omi)"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pool one httpx.AsyncClient for the app's lifetime.

    If the pooled client cannot be created, requests fall back to a
    per-request client so the plugin still serves traffic (#13983).
    """
    try:
        app.state.http_client = httpx.AsyncClient(
            timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
    except Exception:
        app.state.http_client = None
    try:
        yield
    finally:
        client = getattr(app.state, "http_client", None)
        app.state.http_client = None
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.2",
    lifespan=lifespan,
)


def _format_validation_errors(exc: RequestValidationError) -> str:
    try:
        errors = exc.errors()
    except Exception:
        return "invalid request body"
    parts = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        location = ".".join(str(part) for part in error.get("loc", []))
        message = str(error.get("msg", "invalid value"))
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts) or "invalid request body"


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    # Omi chat-tool callers expect HTTP 200 with the {result, error} envelope;
    # FastAPI's default 422 response breaks that contract (#13983).
    return JSONResponse(
        status_code=200,
        content={
            "result": None,
            "error": f"Invalid request: {_format_validation_errors(exc)}",
        },
    )


def clamp_max_results(value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, number))


_DOI_PREFIX_RE = re.compile(r"^10\.[0-9]{4,9}(?:\.[0-9]+)*/")


def _is_valid_doi(value: str) -> bool:
    """Accept visible DOI characters; reject whitespace and non-graphic code points."""
    prefix = _DOI_PREFIX_RE.match(value)
    if prefix is None:
        return False
    suffix = value[prefix.end() :]
    return bool(suffix) and all(
        unicodedata.category(character)[0] in "LMNPS" for character in suffix
    )


def normalize_doi(value: Any) -> str | None:
    """Normalize a DOI identifier before using it as a Crossref path segment.

    Chat callers commonly paste resolver links instead of the bare DOI.  Only
    the two DOI resolver hosts are accepted; their query and fragment are
    discarded before decoding the path exactly once.  Any remaining percent
    escape is kept literal and safely re-encoded for the Crossref API request.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    if raw.lower().startswith("doi:"):
        raw = raw[4:].strip()
    elif "://" in raw or raw.lower().startswith(("http:", "https:")):
        try:
            parsed = urlsplit(raw)
            host = (parsed.hostname or "").lower().rstrip(".")
            if parsed.scheme.lower() not in {"http", "https"}:
                return None
            if host not in {"doi.org", "dx.doi.org"}:
                return None
            if parsed.username or parsed.password:
                return None
            # urlsplit().hostname strips the port; reject a non-default port
            # rather than accepting a look-alike resolver endpoint.
            if parsed.port not in (None, 80, 443):
                return None
        except ValueError:
            return None
        # Query and fragment are intentionally omitted; decode the path once.
        raw = unquote(parsed.path.lstrip("/"))

    if not _is_valid_doi(raw):
        return None
    return raw


_JATS_TAG = re.compile(r"</?jats:[^>]+>")
# Strip paired Crossref face-markup tags while preserving inner text (#14307).
_FACE_TAG_PAIR = re.compile(
    r"<(?P<tag>b|i|u|sub|sup|scp|tt|font|sc|strike)(?:\s+[^>]*)?>(.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
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
    prev = None
    while prev != value:
        prev = value
        value = _FACE_TAG_PAIR.sub(r"\2", value)
    value = _CLOSE_TAG.sub("", value)
    value = _OPEN_TAG.sub("", value)
    return value.strip()


def _clean_field(value: Any) -> str:
    """Clean a scalar field, or the first non-empty entry of a list field."""
    if isinstance(value, (list, tuple)):
        for entry in value:
            text = clean(entry)
            if text:
                return text
        return ""
    return clean(value)


def _extract_title(item: Any) -> str:
    if not isinstance(item, dict):
        return "Untitled"
    return _clean_field(item.get("title")) or "Untitled"


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
        if not isinstance(first, (list, tuple)) or not first:
            continue
        year = clean(first[0])
        if year:
            return year
    return ""


def _message_dict(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    message = payload.get("message")
    return message if isinstance(message, dict) else {}


def _work_items(payload: Any) -> list[dict[str, Any]]:
    items = _message_dict(payload).get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


async def _crossref_request(
    client: httpx.AsyncClient, path: str, params: dict[str, Any]
) -> dict[str, Any]:
    response = await client.get(f"{CROSSREF_BASE}{path}", params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Crossref returned a non-object JSON payload")
    return payload


async def crossref_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    pooled = getattr(app.state, "http_client", None)
    if pooled is not None:
        return await _crossref_request(pooled, path, params)
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
    ) as client:
        return await _crossref_request(client, path, params)


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
    items = _work_items(payload)
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


@app.post("/tools/get_crossref_work", response_model=ChatToolResponse)
async def get_crossref_work(payload: GetWorkInput):
    normalized = normalize_doi(payload.doi)
    if normalized is None:
        return ChatToolResponse(error="Invalid DOI format. Example: 10.1038/nphys1170")

    try:
        payload = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    item = _message_dict(payload)
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
    items = _work_items(payload)
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
