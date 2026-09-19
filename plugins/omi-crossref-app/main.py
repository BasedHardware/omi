import html
import re
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI

from models import AuthorWorksInput, ChatToolResponse, GetWorkInput, SearchWorksInput

CROSSREF_BASE = "https://api.crossref.org"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        app_instance.state.client = client
        yield


app = FastAPI(
    title="Crossref Omi Integration",
    description="No-auth Crossref chat tools for paper metadata search and lookup",
    version="1.0.1",
    lifespan=lifespan,
)


def clamp_max_results(value: int) -> int:
    return max(1, min(10, value))


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
    return " ".join(value.split())


def extract_year(item: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "issued"):
        container = item.get(key)
        if isinstance(container, dict):
            date_parts = container.get("date-parts")
            if isinstance(date_parts, (list, tuple)) and date_parts:
                first = date_parts[0]
                if isinstance(first, (list, tuple)) and first:
                    return clean(first[0])
    return ""


async def crossref_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    client = getattr(getattr(app, "state", None), "client", None)
    if client is not None and not client.is_closed:
        response = await client.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async with httpx.AsyncClient(timeout=TIMEOUT) as fallback_client:
        response = await fallback_client.get(f"{CROSSREF_BASE}{path}", params=params)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/tools/search_crossref_works", response_model=ChatToolResponse)
async def search_crossref_works(payload: SearchWorksInput):
    query = payload.query.strip()
    if not query:
        return ChatToolResponse(error="Search query cannot be empty.")
    limited = clamp_max_results(payload.max_results)
    try:
        data = await crossref_get("/works", {"query": query, "rows": limited})
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    # Defense-in-depth against non-dict payloads from custom/mocked seams
    if not isinstance(data, dict):
        return ChatToolResponse(error="Invalid response payload from Crossref.")
    message = data.get("message")
    items = message.get("items", []) if isinstance(message, dict) else []
    if not items:
        return ChatToolResponse(result=f"No Crossref results found for '{query}'.")

    lines = [f"Top {len(items)} Crossref results for '{query}':"]
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        title_list = item.get("title")
        title = clean(title_list[0]) if isinstance(title_list, (list, tuple)) and title_list else "Untitled"
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
        data = await crossref_get(f"/works/{quote(normalized, safe='')}", {})
    except Exception as exc:
        return ChatToolResponse(error=f"Crossref request failed: {exc}")
    # Defense-in-depth against non-dict payloads from custom/mocked seams
    if not isinstance(data, dict):
        return ChatToolResponse(error="Invalid response payload from Crossref.")
    item = data.get("message")
    if not isinstance(item, dict):
        return ChatToolResponse(error="No work details found in Crossref response.")
    title_list = item.get("title")
    title = clean(title_list[0]) if isinstance(title_list, (list, tuple)) and title_list else "Untitled"
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
        data = await crossref_get(
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
    # Defense-in-depth against non-dict payloads from custom/mocked seams
    if not isinstance(data, dict):
        return ChatToolResponse(error="Invalid response payload from Crossref.")
    message = data.get("message")
    items = message.get("items", []) if isinstance(message, dict) else []
    if not items:
        return ChatToolResponse(result=f"No recent works found for author '{author}'.")

    lines = [f"Recent works for '{author}':"]
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        title_list = item.get("title")
        title = clean(title_list[0]) if isinstance(title_list, (list, tuple)) and title_list else "Untitled"
        doi = clean(item.get("DOI"))
        year = extract_year(item)
        lines.append(f"{idx}. {title} ({year})")
        lines.append(f"   DOI: {doi}")
    return ChatToolResponse(result="\n".join(lines))
