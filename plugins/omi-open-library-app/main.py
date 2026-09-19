"""
Open Library Integration App for Omi.

Provides chat tools for searching books, reading work metadata, and finding
recommended books by subject through the public Open Library APIs.
"""

from contextlib import asynccontextmanager
from html import unescape
import math
import re
from typing import Any, Optional
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


OPEN_LIBRARY_BASE_URL = "https://openlibrary.org"
REQUEST_TIMEOUT_SECONDS = 10
MAX_LIMIT = 10
USER_AGENT = "omi-open-library-app/1.0 (https://omi.me)"
_SUBJECT_CHARS_TO_DROP = frozenset(""";/?:@&=+$,<>#%"{}|\\^[]`\n\r""")

_open_library_client: Optional[httpx.AsyncClient] = None


def _new_open_library_client() -> httpx.AsyncClient:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers)


async def _get_open_library_client() -> httpx.AsyncClient:
    global _open_library_client
    if _open_library_client is None or _open_library_client.is_closed:
        _open_library_client = _new_open_library_client()
    return _open_library_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _open_library_client
    _open_library_client = _new_open_library_client()
    try:
        yield
    finally:
        if _open_library_client is not None:
            await _open_library_client.aclose()


app = FastAPI(
    title="Omi Open Library Integration",
    description="Search books and inspect Open Library metadata from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


def _safe_limit(limit: Any, default: int = 5) -> int:
    if limit is None or limit == "" or isinstance(limit, bool):
        return default
    try:
        f_val = float(str(limit).strip())
        if not math.isfinite(f_val):
            return default
        limit_val = int(f_val)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(1, min(limit_val, MAX_LIMIT))


def _clean_text(value: Any, preserve_newlines: bool = False) -> str:
    if value is None or isinstance(value, (bool, list, dict)):
        return ""
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060\ufeff]', ' ', text)
    if preserve_newlines:
        lines = [re.sub(r"[^\S\n\r]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _join_values(values: Any, limit: int = 5) -> str:
    if not values:
        return ""
    if not isinstance(values, list):
        values = [values]
    cleaned = []
    for item in values:
        if isinstance(item, dict):
            val_text = item.get("name") or item.get("value") or item.get("title")
            cleaned_text = _clean_text(val_text)
        else:
            cleaned_text = _clean_text(item)
        if cleaned_text:
            cleaned.append(cleaned_text)
        if len(cleaned) >= limit:
            break
    return ", ".join(cleaned)


def _description_text(description: Any) -> str:
    if isinstance(description, dict):
        description = description.get("value") or description.get("text") or ""
    elif isinstance(description, list):
        parts = [_clean_text(d.get("value") if isinstance(d, dict) else d, preserve_newlines=True) for d in description]
        description = "\n".join(p for p in parts if p)
    text = _clean_text(description, preserve_newlines=True)
    if len(text) > 900:
        text = text[:900].rstrip() + "..."
    return text


def _work_id(value: Any) -> Optional[str]:
    candidate = _clean_text(value)
    if not candidate:
        return None

    # Handle full or partial Open Library URLs
    if "openlibrary.org" in candidate or candidate.startswith(("http://", "https://")):
        try:
            path_part = urlsplit(candidate).path
            candidate = path_part
        except Exception:
            pass

    # Strip conversational prefixes
    candidate = candidate.strip("`'\"<>[]()")
    lower_cand = candidate.lower()
    for prefix in ("works/", "/works/", "work:", "#"):
        if lower_cand.startswith(prefix):
            candidate = candidate[len(prefix):].strip()
            lower_cand = candidate.lower()

    # Search for standard Open Library work ID token (OL + digits + W)
    match = re.search(r"\b(OL[0-9]+W)\b", candidate, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()

    # Fallback path segment extraction (e.g. OL45883W/slug or OL45883W.json)
    segments = [s.strip() for s in candidate.split("/") if s.strip()]
    for seg in segments:
        seg_clean = seg.removesuffix(".json")
        if re.fullmatch(r"OL[0-9]+W", seg_clean, flags=re.IGNORECASE):
            return seg_clean.upper()

    return None


def _safe_isbn(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (bool, list, dict)):
        return None
    raw = str(value).strip().strip("`'\"<>[]()")
    if not raw:
        return None

    lower_raw = raw.lower()
    for prefix in ("isbn-13:", "isbn-10:", "isbn13:", "isbn10:", "isbn:", "isbn/"):
        if lower_raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
            break

    candidate = re.sub(r"[\s\-\.]+", "", raw)
    if not re.fullmatch(r"[0-9]{9}[0-9Xx]|[0-9]{13}", candidate):
        return None

    return candidate.upper()


def _subject_slug(subject: Any) -> Optional[str]:
    text = _clean_text(subject).strip().lower()
    if not text:
        return None
    slug = "".join("_" if c == " " else c for c in text if c not in _SUBJECT_CHARS_TO_DROP)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or None


def _format_book(doc: Any, index: int) -> str:
    if not isinstance(doc, dict):
        return f"{index}. Untitled\n   Author: unknown author\n   First published: unknown year | Open Library work: unknown"
    title = _clean_text(doc.get("title")) or "Untitled"
    authors = _join_values(doc.get("author_name")) or "unknown author"
    year = doc.get("first_publish_year") or "unknown year"
    work_key = _clean_text(doc.get("key"))
    work = work_key.removeprefix("/works/") if work_key else "unknown"
    subjects = _join_values(doc.get("subject"), limit=4)

    lines = [
        f"{index}. {title}",
        f"   Author: {authors}",
        f"   First published: {year} | Open Library work: {work}",
    ]
    if subjects:
        lines.append(f"   Subjects: {subjects}")
    return "\n".join(lines)


def _format_subject_work(work: Any, index: int) -> str:
    if not isinstance(work, dict):
        return f"{index}. Untitled\n   Author: unknown author | First published: unknown year | Editions: 0 | Work: unknown"
    title = _clean_text(work.get("title")) or "Untitled"
    authors_list = work.get("authors")
    if isinstance(authors_list, list):
        authors = ", ".join(
            _clean_text(author.get("name"))
            for author in authors_list
            if isinstance(author, dict) and _clean_text(author.get("name"))
        )
    else:
        authors = ""
    authors = authors or "unknown author"
    year = work.get("first_publish_year") or "unknown year"
    key = _clean_text(work.get("key")).removeprefix("/works/") or "unknown"
    edition_count = work.get("edition_count") or 0
    return f"{index}. {title}\n   Author: {authors} | First published: {year} | Editions: {edition_count} | Work: {key}"


async def _request_json(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    client = await _get_open_library_client()
    try:
        response = await client.get(f"{OPEN_LIBRARY_BASE_URL}{path}", params=params)
        if response.status_code == 404:
            return {"not_found": True, "status_code": 404}
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"not_found": True, "status_code": 404}
        raise


@app.get("/")
async def root():
    return HTMLResponse(
        """
        <html>
        <head><title>Open Library x Omi</title></head>
        <body style="font-family: sans-serif; max-width: 640px; margin: 48px auto; line-height: 1.5;">
            <h1>Open Library x Omi</h1>
            <p>Search books, fetch work details, and discover subject recommendations from Omi.</p>
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
                "name": "search_books",
                "description": "Search Open Library for books by title, author, subject, or a free-form query.",
                "endpoint": "/tools/search_books",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Free-form book search query, such as a title, author, topic, or ISBN.",
                        },
                        "author": {
                            "type": "string",
                            "description": "Optional author name filter.",
                        },
                        "subject": {
                            "type": "string",
                            "description": "Optional subject filter, such as science fiction or product management.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum books to return. Defaults to 5, maximum 10.",
                        },
                    },
                    "anyOf": [
                        {"required": ["query"]},
                        {"required": ["author"]},
                        {"required": ["subject"]},
                    ],
                },
                "auth_required": False,
                "status_message": "Searching Open Library...",
            },
            {
                "name": "get_book_details",
                "description": "Get Open Library metadata for a specific work ID or ISBN.",
                "endpoint": "/tools/get_book_details",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "work_id": {
                            "type": "string",
                            "description": "Open Library work ID, such as OL45883W. Accepts /works/OL45883W too.",
                        },
                        "isbn": {
                            "type": "string",
                            "description": "Optional ISBN-10 or ISBN-13 if the work ID is unknown.",
                        },
                    },
                    "anyOf": [
                        {"required": ["work_id"]},
                        {"required": ["isbn"]},
                    ],
                },
                "auth_required": False,
                "status_message": "Fetching book details...",
            },
            {
                "name": "search_subject",
                "description": "Find notable books for an Open Library subject such as fantasy, economics, or machine learning.",
                "endpoint": "/tools/search_subject",
                "method": "POST",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subject": {
                            "type": "string",
                            "description": "Subject name to browse.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum books to return. Defaults to 5, maximum 10.",
                        },
                    },
                    "required": ["subject"],
                },
                "auth_required": False,
                "status_message": "Browsing Open Library subject...",
            },
        ]
    }


@app.post("/tools/search_books", response_model=ChatToolResponse)
async def search_books(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload.")
    query = _clean_text(payload.get("query"))
    author = _clean_text(payload.get("author"))
    subject = _clean_text(payload.get("subject"))
    limit = _safe_limit(payload.get("limit"))

    if not any([query, author, subject]):
        return ChatToolResponse(error="Provide query, author, or subject.")

    params: dict[str, Any] = {"limit": limit, "fields": "key,title,author_name,first_publish_year,subject"}
    if query:
        params["q"] = query
    if author:
        params["author"] = author
    if subject:
        params["subject"] = subject

    try:
        data = await _request_json("/search.json", params=params)
        if isinstance(data, dict) and data.get("not_found"):
            return ChatToolResponse(result="No matching books found.")
        if not isinstance(data, dict):
            return ChatToolResponse(error="Open Library returned an unexpected response structure.")
        docs = data.get("docs", [])
        if not isinstance(docs, list) or not docs:
            return ChatToolResponse(result="No matching books found.")
        docs = docs[:limit]

        heading_parts = []
        if query:
            heading_parts.append(f'"{query}"')
        if author:
            heading_parts.append(f"author {author}")
        if subject:
            heading_parts.append(f"subject {subject}")
        heading = "Books for " + ", ".join(heading_parts)
        return ChatToolResponse(result=heading + ":\n\n" + "\n\n".join(_format_book(doc, i + 1) for i, doc in enumerate(docs)))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(result="No matching books found.")
        return ChatToolResponse(error=f"Open Library search failed: {exc}")
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"Open Library search failed: {exc}")


@app.post("/tools/get_book_details", response_model=ChatToolResponse)
async def get_book_details(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload.")
    work_id = _work_id(payload.get("work_id"))
    isbn = _safe_isbn(payload.get("isbn"))

    try:
        if not work_id and isbn:
            data = await _request_json(
                "/api/books",
                params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            )
            if isinstance(data, dict) and data.get("not_found"):
                return ChatToolResponse(result=f"No Open Library details found for ISBN {isbn}.")
            if not isinstance(data, dict):
                return ChatToolResponse(error="Open Library returned an unexpected response structure.")
            book = data.get(f"ISBN:{isbn}")
            if not isinstance(book, dict) or not book:
                return ChatToolResponse(result=f"No Open Library details found for ISBN {isbn}.")

            title = _clean_text(book.get("title")) or "Untitled"
            authors_list = book.get("authors")
            if isinstance(authors_list, list):
                authors = ", ".join(
                    _clean_text(author.get("name"))
                    for author in authors_list
                    if isinstance(author, dict) and _clean_text(author.get("name"))
                )
            else:
                authors = ""
            authors = authors or "unknown author"

            publishers_list = book.get("publishers")
            if isinstance(publishers_list, list):
                publishers = ", ".join(
                    _clean_text(publisher.get("name"))
                    for publisher in publishers_list
                    if isinstance(publisher, dict) and _clean_text(publisher.get("name"))
                )
            else:
                publishers = ""

            publish_date = _clean_text(book.get("publish_date")) or "unknown date"

            subjects_list = book.get("subjects")
            if isinstance(subjects_list, list):
                subjects = ", ".join(
                    _clean_text(subject.get("name"))
                    for subject in subjects_list[:6]
                    if isinstance(subject, dict) and _clean_text(subject.get("name"))
                )
            else:
                subjects = ""

            details = [
                f"{title}",
                f"Author: {authors}",
                f"Published: {publish_date}",
                f"Open Library: {_clean_text(book.get('url'))}",
            ]
            if publishers:
                details.append(f"Publisher: {publishers}")
            if subjects:
                details.append(f"Subjects: {subjects}")
            return ChatToolResponse(result="\n".join(details))

        if not work_id:
            return ChatToolResponse(error="Provide a valid Open Library work_id like OL45883W or an ISBN.")

        data = await _request_json(f"/works/{work_id}.json")
        if isinstance(data, dict) and data.get("not_found"):
            return ChatToolResponse(result="No matching Open Library record found.")
        if not isinstance(data, dict):
            return ChatToolResponse(error="Open Library returned an unexpected response structure.")

        title = _clean_text(data.get("title")) or "Untitled"
        description = _description_text(data.get("description"))
        subjects = _join_values(data.get("subjects"), limit=8)
        created = data.get("created", {})
        created_date = _clean_text(created.get("value")) if isinstance(created, dict) else ""

        lines = [
            title,
            f"Open Library work: {work_id}",
            f"URL: https://openlibrary.org/works/{work_id}",
        ]
        if subjects:
            lines.append(f"Subjects: {subjects}")
        if created_date:
            lines.append(f"Record created: {created_date[:10]}")
        if description:
            lines.append(f"\nDescription: {description}")

        return ChatToolResponse(result="\n".join(lines))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(result="No matching Open Library record found.")
        return ChatToolResponse(error=f"Open Library details request failed: {exc}")
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"Open Library details request failed: {exc}")


@app.post("/tools/search_subject", response_model=ChatToolResponse)
async def search_subject(payload: dict[str, Any]):
    if not isinstance(payload, dict):
        return ChatToolResponse(error="Invalid request payload.")
    subject = _clean_text(payload.get("subject"))
    slug = _subject_slug(subject)
    limit = _safe_limit(payload.get("limit"))
    if not slug:
        return ChatToolResponse(error="Provide a subject to browse.")

    try:
        encoded_slug = quote(slug)
        data = await _request_json(f"/subjects/{encoded_slug}.json", params={"limit": limit})
        if isinstance(data, dict) and data.get("not_found"):
            return ChatToolResponse(result=f"No books found for subject {subject}.")
        if not isinstance(data, dict):
            return ChatToolResponse(error="Open Library returned an unexpected response structure.")
        works = data.get("works", [])
        if not isinstance(works, list) or not works:
            return ChatToolResponse(result=f"No books found for subject {subject}.")
        works = works[:limit]

        title = _clean_text(data.get("name")) or subject
        lines = [_format_subject_work(work, i + 1) for i, work in enumerate(works)]
        return ChatToolResponse(result=f"Open Library books for subject {title}:\n\n" + "\n\n".join(lines))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return ChatToolResponse(result=f"No Open Library subject found for {subject}.")
        return ChatToolResponse(error=f"Open Library subject search failed: {exc}")
    except (httpx.HTTPError, ValueError) as exc:
        return ChatToolResponse(error=f"Open Library subject search failed: {exc}")
