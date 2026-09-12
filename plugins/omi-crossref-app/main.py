import html
import re
from html.parser import HTMLParser
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
    version="1.0.1",
)


def clamp_max_results(value: int) -> int:
    return max(1, min(10, value))


_JATS_TAG = re.compile(r"</?jats:[^>]+>")
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
    value = _CLOSE_TAG.sub("", value)
    value = _OPEN_TAG.sub("", value)
    return value.strip()


class AbstractTextParser(HTMLParser):
    """Read JATS/HTML character data without interpreting escaped literal tags."""

    BLOCKS = {"p", "title", "sec", "div", "br", "break", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        # HTMLParser accepts punctuation in tag names (e.g. b, in a<b,).
        # XML/JATS attributes also require values, unlike HTML boolean attrs.
        # Retain comparison tokens such as <b and c> as literal text.
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]*", tag) or any(value is None for _, value in attrs):
            self.parts.append(self.get_starttag_text())
            return
        if tag.rsplit(":", 1)[-1] in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.rsplit(":", 1)[-1] in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def unknown_decl(self, data):
        # CDATA is literal XML text; neither tags nor entities are interpreted.
        if data.startswith("CDATA["):
            self.parts.append(data[len("CDATA["):])


def clean_abstract(text: Any) -> str:
    if text is None:
        return ""
    parser = AbstractTextParser()
    # Parse before decoding entities: &lt;sample&gt; is text, not a tag.
    parser.feed(str(text))
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


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
    abstract = clean_abstract(item.get("abstract"))
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
