import html
from typing import Any

import httpx
from fastapi import FastAPI, Query

from models import ChatToolResponse

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


@app.post("/tools/search_crossref_works", response_model=ChatToolResponse)
async def search_crossref_works(
    query: str = Query(..., min_length=2),
    max_results: int = Query(5, ge=1, le=10),
):
    limited = clamp_max_results(max_results)
    try:
        payload = await crossref_get(
            "/works",
            {"query": query, "rows": limited, "sort": "relevance", "order": "desc"},
        )
    except Exception as exc:
        return ChatToolResponse(message=f"Crossref request failed: {exc}")
    items = payload.get("message", {}).get("items", [])
    if not items:
        return ChatToolResponse(message=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items)} Crossref results for '{query}':"]
    for idx, item in enumerate(items, 1):
        title = clean((item.get("title") or ["Untitled"])[0])
        doi = clean(item.get("DOI"))
        year = clean(((item.get("published-print") or item.get("published-online") or {}).get("date-parts", [[""]]))[0][0])
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(message="\n".join(lines))


@app.post("/tools/get_crossref_work", response_model=ChatToolResponse)
async def get_crossref_work(doi: str = Query(..., min_length=3)):
    normalized = doi.strip()
    if "/" not in normalized:
        return ChatToolResponse(message="Invalid DOI format. Example: 10.1038/nphys1170")

    try:
        payload = await crossref_get(f"/works/{normalized}", {})
    except Exception as exc:
        return ChatToolResponse(message=f"Crossref request failed: {exc}")
    item = payload.get("message", {})
    title = clean((item.get("title") or ["Untitled"])[0])
    publisher = clean(item.get("publisher"))
    doi_out = clean(item.get("DOI"))
    url = clean(item.get("URL"))
    abstract = clean(item.get("abstract"))
    year = clean(((item.get("published-print") or item.get("published-online") or {}).get("date-parts", [[""]]))[0][0])

    parts = [
        f"Title: {title}",
        f"DOI: {doi_out}",
        f"Year: {year}",
        f"Publisher: {publisher}",
        f"URL: {url}",
    ]
    if abstract:
        parts.append(f"Abstract: {abstract[:1200]}")
    return ChatToolResponse(message="\n".join(parts))


@app.post("/tools/get_crossref_works_by_author", response_model=ChatToolResponse)
async def get_crossref_works_by_author(
    author: str = Query(..., min_length=2),
    max_results: int = Query(5, ge=1, le=10),
):
    limited = clamp_max_results(max_results)
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
        return ChatToolResponse(message=f"Crossref request failed: {exc}")
    items = payload.get("message", {}).get("items", [])
    if not items:
        return ChatToolResponse(message=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items, 1):
        title = clean((item.get("title") or ["Untitled"])[0])
        doi = clean(item.get("DOI"))
        year = clean(((item.get("published-print") or item.get("published-online") or {}).get("date-parts", [[""]]))[0][0])
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(message="\n".join(lines))
