"""Semantic Scholar no-auth chat tools app for Omi."""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Any, Dict
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from models import (
    ChatToolResponse,
    GetAuthorPapersRequest,
    GetPaperRequest,
    SearchPapersRequest,
)

API_BASE = "https://api.semanticscholar.org/graph/v1"
TIMEOUT = 20


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        app.state.client = client
        yield


app = FastAPI(
    title="Semantic Scholar Omi Integration",
    description="No-auth Semantic Scholar chat tools for Omi",
    version="1.0.0",
    lifespan=lifespan,
)


_BARE_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")

# URL hosts that carry a paper identifier in their path.
_IDENTIFIER_URL_MARKERS = (
    ("doi.org/", "DOI"),
    ("arxiv.org/abs/", "ARXIV"),
    ("arxiv.org/pdf/", "ARXIV"),
)

# External identifier namespaces accepted by the Semantic Scholar Graph API,
# mapped to their canonical casing.
_NAMESPACE_CANONICAL = {
    "doi": "DOI",
    "arxiv": "ARXIV",
    "mag": "MAG",
    "acl": "ACL",
    "pmid": "PMID",
    "pmcid": "PMCID",
    "corpusid": "CorpusId",
    "dblp": "DBLP",
    "url": "URL",
}

_SEMANTIC_SCHOLAR_PAPER_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?semanticscholar\.org/paper/(?:[^/?#]+/)?([^/?#]+)",
    re.IGNORECASE,
)

_SEMANTIC_SCHOLAR_AUTHOR_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?semanticscholar\.org/author/(?:[^/?#]+/)?([^/?#]+)",
    re.IGNORECASE,
)


def _strip_quotes_and_brackets(text: str) -> str:
    cleaned = text.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or \
       (cleaned.startswith("'") and cleaned.endswith("'")) or \
       (cleaned.startswith("<") and cleaned.endswith(">")):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def normalize_identifier(raw: str) -> str:
    """Normalize a user/agent supplied identifier to the canonical form.

    Accepts:
    - Semantic Scholar paper URLs (e.g. https://www.semanticscholar.org/paper/.../<id>)
    - Raw DOIs (10.xxxx/...)
    - doi.org and arxiv.org URLs
    - Namespaced identifiers (doi:, arxiv:, pmid:, corpusid:, ...) in any casing
    - Bare Semantic Scholar 40-character hex SHA paper IDs
    Strips wrapping quotes, angle brackets, query parameters, and URL fragments.
    """
    if not isinstance(raw, str):
        return ""

    value = _strip_quotes_and_brackets(raw)
    if not value:
        return ""

    # Check for Semantic Scholar paper URL
    m_s2 = _SEMANTIC_SCHOLAR_PAPER_URL_RE.match(value)
    if m_s2:
        extracted = m_s2.group(1).strip()
        if extracted:
            if extracted.lower().startswith("corpusid:"):
                return f"CorpusId:{extracted[9:].strip()}"
            return extracted

    # Strip query parameters or fragments
    cleaned_url = re.split(r"[?#]", value)[0].strip()
    lower = cleaned_url.lower()

    for marker, namespace in _IDENTIFIER_URL_MARKERS:
        index = lower.find(marker)
        if index != -1:
            identifier = cleaned_url[index + len(marker):].strip().rstrip("/")
            if not identifier:
                return value
            if namespace == "ARXIV" and identifier.lower().endswith(".pdf"):
                identifier = identifier[:-4]
            return f"{namespace}:{identifier}"

    # Handle namespaced identifier like doi:10.xxx or CorpusId:123
    namespace, separator, rest = value.partition(":")
    if separator and rest.strip():
        ns_key = namespace.strip().lower()
        if ns_key in _NAMESPACE_CANONICAL:
            clean_rest = rest.strip()
            if ns_key == "url":
                return f"URL:{clean_rest}"
            clean_rest = re.split(r"[?#]", clean_rest)[0].strip()
            return f"{_NAMESPACE_CANONICAL[ns_key]}:{clean_rest}"

    # A bare DOI must be prefixed for the Graph API to resolve it.
    bare_clean = re.split(r"[?#]", value)[0].strip()
    if _BARE_DOI_RE.match(bare_clean):
        return f"DOI:{bare_clean}"

    return bare_clean


def normalize_author_id(raw: str) -> str:
    """Normalize a user/agent supplied author identifier.

    Accepts:
    - Semantic Scholar author URLs (e.g. https://www.semanticscholar.org/author/.../<id>)
    - Strings with author: prefix
    - Bare numeric/alphanumeric author IDs
    """
    if not isinstance(raw, str):
        return ""

    value = _strip_quotes_and_brackets(raw)
    if not value:
        return ""

    # Check for Semantic Scholar author URL
    m_author = _SEMANTIC_SCHOLAR_AUTHOR_URL_RE.match(value)
    if m_author:
        extracted = m_author.group(1).strip()
        if extracted:
            return extracted

    # Check for author: prefix
    if value.lower().startswith("author:"):
        value = value[7:].strip()

    # Strip query string or fragments
    return re.split(r"[?#]", value)[0].strip()


def _to_int(value: Any) -> int:
    """Coerce heterogeneous JSON numbers (int, float, numeric string) to int."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            try:
                return int(float(text))
            except ValueError:
                return 0
    return 0


def _paper_sort_key(paper: Any) -> tuple[int, int]:
    """Normalized (year, citationCount) sort key.

    Graph API payloads may carry years as strings, ints, or None; returning a
    uniform tuple[int, int] keeps sorted() stable across mixed types.
    """
    if not isinstance(paper, dict):
        return (0, 0)
    return (_to_int(paper.get("year")), _to_int(paper.get("citationCount")))


def format_authors(authors: Any) -> str:
    if not isinstance(authors, list):
        return "Unknown"
    names = [str(a.get("name")) for a in authors if isinstance(a, dict) and a.get("name")]
    return ", ".join(names[:6]) if names else "Unknown"


def format_year(year: Any) -> str:
    value = _to_int(year)
    return str(value) if value > 0 else "Unknown"


async def api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{API_BASE}{path}"
    client = getattr(getattr(app, "state", None), "client", None)
    if client is not None:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    async with httpx.AsyncClient(timeout=TIMEOUT) as fallback:
        resp = await fallback.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


@app.get("/.well-known/omi-tools.json")
async def manifest() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": "search_semantic_scholar_papers",
                "description": "Search Semantic Scholar papers by keyword.",
                "endpoint": "/tools/search_semantic_scholar_papers",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {
                            "type": "integer",
                            "description": "Max results (1-10, default 5)",
                        },
                        "min_year": {
                            "type": "integer",
                            "description": "Optional minimum publication year",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_semantic_scholar_paper",
                "description": "Get details for a paper by Semantic Scholar ID or DOI.",
                "endpoint": "/tools/get_semantic_scholar_paper",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paper_id_or_doi": {
                            "type": "string",
                            "description": "Semantic Scholar paper ID or DOI",
                        }
                    },
                    "required": ["paper_id_or_doi"],
                },
            },
            {
                "name": "get_semantic_scholar_author_papers",
                "description": "Get recent papers by Semantic Scholar author ID.",
                "endpoint": "/tools/get_semantic_scholar_author_papers",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "author_id": {
                            "type": "string",
                            "description": "Semantic Scholar author ID",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max results (1-10, default 5)",
                        },
                    },
                    "required": ["author_id"],
                },
            },
        ]
    }


@app.post("/tools/search_semantic_scholar_papers", response_model=ChatToolResponse)
async def search_papers(req: SearchPapersRequest) -> ChatToolResponse:
    limit = req.max_results or 5
    params: Dict[str, Any] = {
        "query": req.query.strip(),
        "limit": limit,
        "fields": "title,year,authors,citationCount,url,venue",
    }
    if req.min_year:
        params["year"] = f"{req.min_year}-"

    try:
        data = await api_get("/paper/search", params)
        payload = data if isinstance(data, dict) else {}
        papers = [p for p in (payload.get("data") or []) if isinstance(p, dict)]
        if not papers:
            return ChatToolResponse(result="No papers found.")

        lines = []
        for i, paper in enumerate(papers, start=1):
            title = paper.get("title") or "Untitled"
            year = format_year(paper.get("year"))
            authors = format_authors(paper.get("authors", []))
            venue = paper.get("venue") or "Unknown venue"
            cites = paper.get("citationCount") or 0
            url = paper.get("url") or ""
            lines.append(
                f"{i}. {title}\n   Authors: {authors}\n   Year: {year} | Venue: {venue} | Citations: {cites}"
                + (f"\n   URL: {url}" if url else "")
            )
        return ChatToolResponse(result="\n\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Semantic Scholar API error: {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Semantic Scholar request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.post("/tools/get_semantic_scholar_paper", response_model=ChatToolResponse)
async def get_paper(req: GetPaperRequest) -> ChatToolResponse:
    try:
        norm_id = normalize_identifier(req.paper_id_or_doi)
        if not norm_id:
            return ChatToolResponse(error="Paper ID or DOI is required.")
        identifier = quote(norm_id, safe=":")
        data = await api_get(
            f"/paper/{identifier}",
            {"fields": "title,abstract,year,authors,citationCount,referenceCount,url,venue"},
        )
        if not isinstance(data, dict):
            return ChatToolResponse(error="Paper not found.")

        title = data.get("title") or "Untitled"
        year = format_year(data.get("year"))
        authors = format_authors(data.get("authors", []))
        venue = data.get("venue") or "Unknown venue"
        citations = data.get("citationCount") or 0
        references = data.get("referenceCount") or 0
        abstract = data.get("abstract") or "No abstract available."
        url = data.get("url") or ""

        result = (
            f"Title: {title}\n"
            f"Authors: {authors}\n"
            f"Year: {year}\n"
            f"Venue: {venue}\n"
            f"Citations: {citations} | References: {references}\n"
            f"Abstract: {abstract}"
            + (f"\nURL: {url}" if url else "")
        )
        return ChatToolResponse(result=result)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            return ChatToolResponse(error="Paper not found.")
        return ChatToolResponse(error=f"Semantic Scholar API error: {code}")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Semantic Scholar request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.post("/tools/get_semantic_scholar_author_papers", response_model=ChatToolResponse)
async def get_author_papers(req: GetAuthorPapersRequest) -> ChatToolResponse:
    try:
        raw_author_id = normalize_author_id(req.author_id)
        if not raw_author_id:
            return ChatToolResponse(error="Author ID is required.")
        author_id = quote(raw_author_id, safe="")
        limit = req.max_results or 5
        data = await api_get(
            f"/author/{author_id}",
            {
                "fields": "name,papers.title,papers.year,papers.citationCount,papers.url",
            },
        )

        payload = data if isinstance(data, dict) else {}
        author_name = payload.get("name") or req.author_id
        papers = [p for p in (payload.get("papers") or []) if isinstance(p, dict)]
        if not papers:
            return ChatToolResponse(result=f"No papers found for author {author_name}.")

        papers_sorted = sorted(papers, key=_paper_sort_key, reverse=True)[:limit]

        lines = [f"Recent papers by {author_name}:"]
        for i, paper in enumerate(papers_sorted, start=1):
            title = paper.get("title") or "Untitled"
            year = format_year(paper.get("year"))
            cites = paper.get("citationCount") or 0
            url = paper.get("url") or ""
            lines.append(
                f"{i}. {title}\n   Year: {year} | Citations: {cites}" + (f"\n   URL: {url}" if url else "")
            )

        return ChatToolResponse(result="\n\n".join(lines))
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 404:
            return ChatToolResponse(error="Author not found.")
        return ChatToolResponse(error=f"Semantic Scholar API error: {code}")
    except httpx.HTTPError as exc:
        return ChatToolResponse(error=f"Semantic Scholar request failed: {exc}")
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Semantic Scholar Omi integration is running."}
