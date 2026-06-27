import html
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = 20.0

app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.0",
)


def clamp_max_results(value: int) -> int:
    return max(1, min(10, value))


def clean(text: Any) -> str:
    if text is None:
        return ""
    return html.unescape(str(text)).strip()


def extract_year(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued"):
        date_parts = (item.get(key) or {}).get("date-parts", [])
        if date_parts and date_parts[0]:
            return clean(date_parts[0][0])
    return ""


async def crossref_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
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
        payload = await crossref_get(
            "/works",
            {"query": query, "rows": limited, "sort": "relevance", "order": "desc"},
        )
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    items = payload.get("message", {}).get("items", [])
    if not items:
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items)} Crossref results for '{query}':"]
    for idx, item in enumerate(items, 1):
        title = clean((item.get("title") or ["Untitled"])[0])
        doi = clean(item.get("DOI"))
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
        payload = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    item = payload.get("message", {})
    title = clean((item.get("title") or ["Untitled"])[0])
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
    items = payload.get("message", {}).get("items", [])
    if not items:
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items, 1):
        title = clean((item.get("title") or ["Untitled"])[0])
        doi = clean(item.get("DOI"))
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))
