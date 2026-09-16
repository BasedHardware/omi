"""Semantic Scholar no-auth chat tools app for Omi."""
from __future__ import annotations

import re
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

app = FastAPI(
    title="Semantic Scholar Omi Integration",
    description="No-auth Semantic Scholar chat tools for Omi",
    version="1.0.0",
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


def normalize_identifier(raw: str) -> str:
    """Normalize a user/agent supplied identifier to the <NAMESPACE>:<id> form.

    Accepts raw DOIs (10.xxxx/...), doi.org and arxiv.org URLs, and namespaced
    identifiers (doi:, arxiv:, pmid:, corpusid:, ...) in any casing. Anything
    else, e.g. a bare Semantic Scholar paper ID, is returned unchanged.
    """
    value = raw.strip()
    lower = value.lower()

    for marker, namespace in _IDENTIFIER_URL_MARKERS:
        index = lower.find(marker)
        if index != -1:
            identifier = value[index + len(marker):].strip().rstrip("/")
            if not identifier:
                return value
            if namespace == "ARXIV" and identifier.lower().endswith(".pdf"):
                identifier = identifier[:-4]
            return f"{namespace}:{identifier}"

    namespace, separator, rest = value.partition(":")
    if separator and rest.strip() and namespace.lower() in _NAMESPACE_CANONICAL:
        return f"{_NAMESPACE_CANONICAL[namespace.lower()]}:{rest.strip()}"

    # A bare DOI must be prefixed for the Graph API to resolve it.
    if _BARE_DOI_RE.match(value):
        return f"DOI:{value}"

    return value


async def api_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params)
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
    params: Dict[str, Any] = {
        "query": req.query,
        "limit": req.max_results,
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
        identifier = quote(normalize_identifier(req.paper_id_or_doi), safe=":")
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
        author_id = quote(req.author_id.strip(), safe="")
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

        papers_sorted = sorted(papers, key=_paper_sort_key, reverse=True)[: req.max_results]

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
