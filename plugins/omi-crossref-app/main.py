"""
Crossref Integration App for Omi

This app provides chat tools for searching scholarly works, looking up
work details by DOI, and finding works by author via the Crossref API.
"""
from contextlib import asynccontextmanager
import html
import re
import unicodedata
from typing import Any, Optional
from urllib.parse import quote, unquote, urlsplit

from fastapi import FastAPI
import httpx

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0
USER_AGENT = "OmiCrossrefIntegration/1.0 (mailto:dev@omi.me)"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage HTTP client lifecycle with connection pooling on app.state."""
    app.state.client = httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )
    yield
    client = getattr(app.state, "client", None)
    if client is not None:
        await client.aclose()
        app.state.client = None


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.2",
    lifespan=lifespan,
)

try:
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Any, exc: RequestValidationError):
        """Convert FastAPI/Pydantic validation errors into 200 ChatToolResponse error envelopes."""
        errors = exc.errors()
        msg = errors[0].get("msg", "Invalid input parameters") if errors else "Invalid input parameters"
        return JSONResponse(status_code=200, content={"result": None, "error": f"Invalid request: {msg}"})
except (ImportError, AttributeError):
    pass


def clamp_max_results(value: Any) -> int:
    """Safely clamp max_results to 1-10 with a default of 5."""
    if isinstance(value, bool) or value is None:
        return 5
    try:
        val = int(value)
        return max(1, min(10, val))
    except (TypeError, ValueError, OverflowError):
        return 5


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


def clean_doi(value: Any) -> str:
    """
    Sanitize and extract a clean DOI string from various user inputs:
    - Bare DOIs: '10.1038/nphys1170'
    - Prefixed: 'doi: 10.1038/nphys1170', 'DOI:10.1038/nphys1170'
    - Web links: 'https://doi.org/10.1038/nphys1170', 'http://dx.doi.org/10.1038/nphys1170'
    - API links: 'https://api.crossref.org/works/10.1038/nphys1170'
    - Markdown links: '[DOI](https://doi.org/10.1038/nphys1170)'
    - Strips surrounding quotes, angle brackets, and unbalanced trailing punctuation.
    """
    if value is None or isinstance(value, bool) or not isinstance(value, str):
        return ""

    raw = value.strip()
    if not raw:
        return ""

    # 1. URL-decode first to handle percent-encoded identifiers cleanly
    try:
        raw = unquote(raw).strip()
    except Exception:
        pass

    # 2. Extract standard DOI regex (10.xxxx/...) supporting characters including +, <, >
    doi_pattern = re.search(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9+<>]+)", raw)
    if doi_pattern:
        candidate = doi_pattern.group(1).rstrip(".,;:\"'")
        # If trailing paren/angle bracket is unbalanced, trim it
        if candidate.endswith(")") and candidate.count(")") > candidate.count("("):
            candidate = candidate.rstrip(")")
        if candidate.endswith(">") and candidate.count(">") > candidate.count("<"):
            candidate = candidate.rstrip(">")
        return candidate

    # 3. Extract from Markdown link syntax
    md_match = re.search(r"\[[^\]]*\]\(([^)]+)\)", raw)
    if md_match:
        target = md_match.group(1).strip()
        doi_in_url = re.search(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9+<>]+)", target)
        if doi_in_url:
            candidate = doi_in_url.group(1).rstrip(".,;:\"'")
            if candidate.endswith(")") and candidate.count(")") > candidate.count("("):
                candidate = candidate.rstrip(")")
            if candidate.endswith(">") and candidate.count(">") > candidate.count("<"):
                candidate = candidate.rstrip(">")
            return candidate

    # 4. Strip prefixes and hosts
    cleaned = raw.strip("\"'<>`()[]{}.,;: ")
    cleaned = re.sub(
        r"^(?:https?://)?(?:dx\.)?doi\.org/",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^https?://api\.crossref\.org/works/",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^doi:\s*", "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned.strip("\"'<>`[]{}.,;: ")


_JATS_TAG = re.compile(r"</?jats:[^>]+>")

# Strip paired Crossref face-markup tags while preserving inner text (#14307, #14318).
_FACE_TAG_PAIR = re.compile(
    r"<(?P<tag>b|i|u|sub|sup|scp|tt|font|sc|strike)(?:\s+[^>]*)?>(.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)

_CLOSE_TAG = re.compile(r"</[a-zA-Z][^>]*>")

# Opening tags must precede valid tag names to avoid eating inequalities like p < 0.05 or a<b
_OPEN_TAG = re.compile(r"(?<![A-Za-z0-9_])<[a-zA-Z][a-zA-Z0-9:-]*(?:\s+[^>]*)?>")


def clean(text: Any) -> str:
    """Clean string, strip JATS/HTML tags, decode HTML entities, preserving math/inequalities."""
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        return clean(text[0]) if text else ""
    value = html.unescape(str(text)).strip()
    # Crossref abstracts often carry JATS markup; chat tools want plain text
    value = _JATS_TAG.sub("", value)
    prev = None
    while prev != value:
        prev = value
        value = _FACE_TAG_PAIR.sub(r"\2", value)
    value = _CLOSE_TAG.sub("", value)
    value = _OPEN_TAG.sub("", value)
    return value.strip()


def extract_year(item: Any) -> str:
    """Extract publication year from print, online, or issued date parts."""
    if not isinstance(item, dict):
        return ""
    for key in ("published-print", "published-online", "issued"):
        date_obj = item.get(key)
        if isinstance(date_obj, dict):
            date_parts = date_obj.get("date-parts", [])
            if date_parts and isinstance(date_parts, list) and len(date_parts) > 0:
                first_part = date_parts[0]
                if first_part and isinstance(first_part, list) and len(first_part) > 0:
                    return clean(first_part[0])
    return ""


def _extract_title(item: Any) -> str:
    """Safely extract work title from Crossref item dict."""
    if not isinstance(item, dict):
        return "Untitled"
    title_val = item.get("title")
    if isinstance(title_val, list) and title_val:
        return clean(title_val[0]) or "Untitled"
    if isinstance(title_val, str) and title_val.strip():
        return clean(title_val)
    return "Untitled"


async def crossref_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Execute GET request against Crossref API using pooled client or fallback."""
    client = getattr(app.state, "client", None)
    if client is not None and not getattr(client, "is_closed", False):
        response = await client.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        return response.json()

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as fallback_client:
        response = await fallback_client.get(f"{CROSSREF_BASE}{path}", params=params)
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
    query = str(payload.query or "").strip()
    if len(query) < 2:
        return ChatToolResponse(error="Query must be at least 2 characters.")
    limited = clamp_max_results(payload.max_results)
    try:
        data = await crossref_get(
            "/works",
            {"query": query, "rows": limited, "sort": "relevance", "order": "desc"},
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        return ChatToolResponse(error=f"Crossref API error: HTTP {code}")
    except httpx.RequestError as exc:
        return ChatToolResponse(error=f"Crossref network error: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    message = data.get("message") if isinstance(data, dict) else {}
    items = (message or {}).get("items", []) if isinstance(message, dict) else []
    if not isinstance(items, list) or not items:
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items)} Crossref results for '{query}':"]
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        title = _extract_title(item)
        doi = clean_doi(item.get("DOI")) or clean(item.get("DOI"))
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_crossref_work", response_model=ChatToolResponse)
async def get_crossref_work(payload: GetWorkInput):
    doi_val = getattr(payload, "doi", None) if payload is not None else None
    normalized = normalize_doi(doi_val)
    if normalized is None:
        return ChatToolResponse(error="Invalid DOI format. Example: 10.1038/nphys1170")

    try:
        data = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        if code == 404:
            return ChatToolResponse(error=f"Work not found for DOI: {normalized}")
        return ChatToolResponse(error=f"Crossref API error: HTTP {code}")
    except httpx.RequestError as exc:
        return ChatToolResponse(error=f"Crossref network error: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    item = data.get("message", {}) if isinstance(data, dict) else {}
    if not isinstance(item, dict) or not item:
        return ChatToolResponse(error=f"Work not found for DOI: {normalized}")

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


@app.post("/tools/get_crossref_works_by_author", response_model=ChatToolResponse)
async def get_crossref_works_by_author(payload: AuthorWorksInput):
    author = str(payload.author or "").strip()
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
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        return ChatToolResponse(error=f"Crossref API error: HTTP {code}")
    except httpx.RequestError as exc:
        return ChatToolResponse(error=f"Crossref network error: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")

    message = data.get("message") if isinstance(data, dict) else {}
    items = (message or {}).get("items", []) if isinstance(message, dict) else []
    if not isinstance(items, list) or not items:
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        title = _extract_title(item)
        doi = clean_doi(item.get("DOI")) or clean(item.get("DOI"))
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))
