"""Semantic Scholar no-auth chat tools app for Omi."""
from __future__ import annotations

from typing import Any, Dict, List
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


def format_authors(authors: List[Dict[str, Any]]) -> str:
    names = [a.get("name", "Unknown") for a in authors if a.get("name")]
    return ", ".join(names[:6]) if names else "Unknown"


def format_year(year: Any) -> str:
    if isinstance(year, int):
        return str(year)
    return "Unknown"


def normalize_identifier(raw: str) -> str:
    value = raw.strip()
    if value.lower().startswith("doi:"):
        # Preserve DOI namespace expected by Semantic Scholar.
        value = "DOI:" + value[4:].strip()
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
        papers = data.get("data", [])
        if not papers:
            return ChatToolResponse(result="No papers found.")

        lines = []
        for i, paper in enumerate(papers, start=1):
            title = paper.get("title") or "Untitled"
            year = format_year(paper.get("year"))
            authors = format_authors(paper.get("authors", []))
            venue = paper.get("venue") or "Unknown venue"
            cites = paper.get("citationCount", 0)
            url = paper.get("url") or ""
            lines.append(
                f"{i}. {title}\n   Authors: {authors}\n   Year: {year} | Venue: {venue} | Citations: {cites}"
                + (f"\n   URL: {url}" if url else "")
            )
        return ChatToolResponse(result="\n\n".join(lines))
    except httpx.HTTPStatusError as exc:
        return ChatToolResponse(error=f"Semantic Scholar API error: {exc.response.status_code}")
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

        title = data.get("title") or "Untitled"
        year = format_year(data.get("year"))
        authors = format_authors(data.get("authors", []))
        venue = data.get("venue") or "Unknown venue"
        citations = data.get("citationCount", 0)
        references = data.get("referenceCount", 0)
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

        author_name = data.get("name") or req.author_id
        papers = data.get("papers", [])
        if not papers:
            return ChatToolResponse(result=f"No papers found for author {author_name}.")

        papers_sorted = sorted(
            papers,
            key=lambda p: ((p.get("year") or 0), (p.get("citationCount") or 0)),
            reverse=True,
        )[: req.max_results]

        lines = [f"Recent papers by {author_name}:"]
        for i, paper in enumerate(papers_sorted, start=1):
            title = paper.get("title") or "Untitled"
            year = format_year(paper.get("year"))
            cites = paper.get("citationCount", 0)
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
    except Exception as exc:
        return ChatToolResponse(error=f"Unexpected error: {exc}")


@app.get("/")
async def root() -> Dict[str, str]:
    return {"message": "Semantic Scholar Omi integration is running."}
