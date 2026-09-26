"""
Project Gutenberg Classic Literature and E-Books Integration Plugin for Omi.

Provides chat tools for searching 70,000+ free classic books, authors, literary genres,
subjects, reading links, and digital formats from Project Gutenberg via the Gutendex API.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

GUTENDEX_API_URL = "https://gutendex.com/books"
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESULTS_LIMIT = 20
DEFAULT_RESULTS_LIMIT = 5

_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _http_client
    _http_client = httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "OmiGutendexApp/1.0 (https://omi.me)"},
    )
    yield
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


app = FastAPI(
    title="Omi Project Gutenberg Classic Books App",
    description="Search free classic books, authors, genres, and reading links from Omi chat tools",
    version="1.0.0",
    lifespan=lifespan,
)


def get_http_client() -> httpx.AsyncClient:
    """Return the global client or instantiate a fallback."""
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchBooksRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Book title, author, or search phrase (e.g. 'Pride and Prejudice', 'Dostoevsky', 'Frankenstein')",
    )
    topic: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional genre or subject filter (e.g. 'Philosophy', 'Science Fiction', 'Poetry')",
    )
    language: Optional[str] = Field(
        None,
        max_length=10,
        description="Optional two-letter language code (e.g. 'en', 'fr', 'de', 'es')",
    )
    limit: int = Field(
        default=DEFAULT_RESULTS_LIMIT,
        ge=1,
        le=MAX_RESULTS_LIMIT,
        description="Maximum number of books to return (1-20)",
    )


class BooksByTopicRequest(BaseModel):
    topic: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Literary topic, genre, or category (e.g. 'Gothic', 'Philosophy', 'Adventure', 'Mythology')",
    )
    limit: int = Field(
        default=DEFAULT_RESULTS_LIMIT,
        ge=1,
        le=MAX_RESULTS_LIMIT,
        description="Maximum number of books to return (1-20)",
    )


class BookDetailsRequest(BaseModel):
    book_id_or_title: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Project Gutenberg book ID (e.g. '1342') or book title",
    )


def format_book_summary(book: Dict[str, Any]) -> str:
    """Format a single book record into structured text."""
    book_id = book.get("id")
    title = book.get("title") or "Untitled Classic"
    authors_data = book.get("authors") or []
    author_names = []
    for a in authors_data:
        name = a.get("name")
        if name:
            author_names.append(name)
    authors_str = ", ".join(author_names) if author_names else "Unknown Author"

    subjects = book.get("subjects") or []
    formats = book.get("formats") or {}
    read_url = formats.get("text/html") or formats.get("text/plain; charset=utf-8") or f"https://www.gutenberg.org/ebooks/{book_id}"
    downloads = book.get("download_count") or 0

    lines = [
        f"📖 **{title}** (ID: #{book_id})",
        f"✍️ Author(s): {authors_str}",
    ]
    if subjects:
        top_subjects = [s.split(" -- ")[0] for s in subjects[:3]]
        lines.append(f"🏷️ Subjects: {', '.join(top_subjects)}")
    lines.append(f"📥 Downloads: {downloads:,}")
    lines.append(f"🔗 Read / Download: {read_url}")
    return "\n".join(lines)


async def fetch_books_from_api(
    search: Optional[str] = None,
    topic: Optional[str] = None,
    languages: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict[str, Any]]:
    """Query the Gutendex API for books."""
    params: Dict[str, str] = {}
    if search:
        params["search"] = search.strip()
    if topic:
        params["topic"] = topic.strip()
    if languages:
        params["languages"] = languages.strip().lower()

    http_client = client or get_http_client()
    try:
        response = await http_client.get(GUTENDEX_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
            return data["results"]
        return []
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Gutendex API error: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Failed to connect to Gutendex API: {exc}") from exc


@app.post("/tools/search_books", response_model=ChatToolResponse)
async def tool_search_books(request: SearchBooksRequest) -> ChatToolResponse:
    """Search classic literature and free ebooks in Project Gutenberg."""
    query = request.query.strip()
    if not query:
        return ChatToolResponse(error="Search query cannot be empty.")

    try:
        results = await fetch_books_from_api(
            search=query,
            topic=request.topic,
            languages=request.language,
        )
        if not results:
            return ChatToolResponse(result=f"No classic books found in Project Gutenberg matching '{query}'.")

        limited = results[: request.limit]
        cards = [format_book_summary(b) for b in limited]
        total_found = len(results)
        showing_str = f"Showing top {len(limited)} of {total_found}" if total_found > len(limited) else f"Found {total_found}"

        header = f"📚 Project Gutenberg Classic Books: '{query}' ({showing_str})\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/books_by_topic", response_model=ChatToolResponse)
async def tool_books_by_topic(request: BooksByTopicRequest) -> ChatToolResponse:
    """Explore classic books and literature by genre, topic, or subject."""
    topic = request.topic.strip()
    if not topic:
        return ChatToolResponse(error="Topic cannot be empty.")

    try:
        results = await fetch_books_from_api(topic=topic)
        if not results:
            return ChatToolResponse(result=f"No classic books found for topic '{topic}'.")

        limited = results[: request.limit]
        cards = [format_book_summary(b) for b in limited]
        total_found = len(results)
        showing_str = f"Showing top {len(limited)} of {total_found}" if total_found > len(limited) else f"Found {total_found}"

        header = f"🏛️ Classic Literature in Topic: '{topic}' ({showing_str})\n"
        body = "\n\n".join(cards)
        return ChatToolResponse(result=f"{header}\n{body}")
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.post("/tools/book_details", response_model=ChatToolResponse)
async def tool_book_details(request: BookDetailsRequest) -> ChatToolResponse:
    """Get full details, author lifespans, subjects, and reading formats for a specific book."""
    target = request.book_id_or_title.strip()
    if not target:
        return ChatToolResponse(error="Book ID or title cannot be empty.")

    try:
        # If numeric ID, search directly
        results = await fetch_books_from_api(search=target)
        if not results:
            return ChatToolResponse(result=f"Could not find details for book '{target}'.")

        best_book = results[0]
        # Exact ID match check
        if target.isdigit():
            for b in results:
                if str(b.get("id")) == target:
                    best_book = b
                    break

        book_id = best_book.get("id")
        title = best_book.get("title") or "Untitled"
        authors = best_book.get("authors") or []
        authors_desc = []
        for a in authors:
            name = a.get("name", "Unknown")
            by = a.get("birth_year")
            dy = a.get("death_year")
            dates = f" ({by}–{dy})" if by and dy else ""
            authors_desc.append(f"{name}{dates}")

        subjects = best_book.get("subjects") or []
        bookshelves = best_book.get("bookshelves") or []
        languages = best_book.get("languages") or ["en"]
        downloads = best_book.get("download_count") or 0
        formats = best_book.get("formats") or {}

        details = [
            f"📚 Book: {title} (ID: #{book_id})",
            f"✍️ Author(s): {', '.join(authors_desc) if authors_desc else 'Unknown'}",
            f"🌐 Language(s): {', '.join(languages)}",
            f"🏷️ Subjects: {', '.join(subjects[:5]) if subjects else 'None listed'}",
        ]
        if bookshelves:
            details.append(f"📦 Collections: {', '.join(bookshelves[:3])}")
        details.append(f"📥 Total Downloads: {downloads:,}")

        # Format reading links
        links = []
        if "text/html" in formats:
            links.append(f"• Read Online (HTML): {formats['text/html']}")
        if "application/epub+zip" in formats:
            links.append(f"• EPUB E-Book: {formats['application/epub+zip']}")
        if "text/plain; charset=utf-8" in formats:
            links.append(f"• Plain Text: {formats['text/plain; charset=utf-8']}")
        links.append(f"• Project Gutenberg Page: https://www.gutenberg.org/ebooks/{book_id}")

        details.append("\n📖 Reading & Download Formats:\n" + "\n".join(links))
        return ChatToolResponse(result="\n".join(details))
    except Exception as exc:
        return ChatToolResponse(error=str(exc))


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve an interactive status and documentation dashboard."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Omi Project Gutenberg Classic Books App</title>
        <style>
            :root {
                --bg: #0d0e15;
                --surface: #151722;
                --border: #26293b;
                --text: #ffffff;
                --text-muted: #9499ad;
                --accent: #f59e0b;
                --accent-rgb: 245, 158, 11;
                --radius: 12px;
            }
            body {
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg);
                color: var(--text);
                padding: 2.5rem 1.5rem;
                display: flex;
                justify-content: center;
            }
            .container {
                max-width: 760px;
                width: 100%;
            }
            .header {
                display: flex;
                align-items: center;
                gap: 1rem;
                margin-bottom: 2rem;
            }
            .icon {
                font-size: 2.5rem;
                background: var(--surface);
                padding: 0.75rem;
                border-radius: var(--radius);
                border: 1px solid var(--border);
            }
            h1 {
                margin: 0 0 0.25rem 0;
                font-size: 1.75rem;
            }
            p.sub {
                margin: 0;
                color: var(--text-muted);
                font-size: 0.95rem;
            }
            .card {
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: var(--radius);
                padding: 1.5rem;
                margin-bottom: 1.5rem;
            }
            h2 {
                margin-top: 0;
                font-size: 1.2rem;
                color: var(--accent);
            }
            .endpoint-list {
                display: flex;
                flex-direction: column;
                gap: 0.75rem;
            }
            .endpoint {
                background: var(--bg);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: 0.75rem 1rem;
                font-family: monospace;
                font-size: 0.9rem;
            }
            .badge {
                background: rgba(var(--accent-rgb), 0.15);
                color: var(--accent);
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: bold;
                margin-right: 0.5rem;
            }
            .footer {
                text-align: center;
                color: var(--text-muted);
                font-size: 0.85rem;
                margin-top: 2rem;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="icon">📚</div>
                <div>
                    <h1>Omi Project Gutenberg App</h1>
                    <p class="sub">Classic literature, free ebooks, authors & reading formats for Omi assistants.</p>
                </div>
            </div>

            <div class="card">
                <h2>⚡ Available Chat Tools</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">POST</span>/tools/search_books</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/books_by_topic</div>
                    <div class="endpoint"><span class="badge">POST</span>/tools/book_details</div>
                </div>
            </div>

            <div class="card">
                <h2>🔍 Manifests & Endpoints</h2>
                <div class="endpoint-list">
                    <div class="endpoint"><span class="badge">GET</span><a href="/manifest.json" style="color:var(--accent);">/manifest.json</a> — Omi Plugin Manifest</div>
                    <div class="endpoint"><span class="badge">GET</span><a href="/.well-known/ai-plugin.json" style="color:var(--accent);">/.well-known/ai-plugin.json</a> — AI Plugin Manifest</div>
                    <div class="endpoint"><span class="badge">GET</span><a href="/health" style="color:var(--accent);">/health</a> — Health Status</div>
                </div>
            </div>

            <div class="footer">
                Built for the Omi Open Source Ecosystem • 70,000+ Public Domain E-Books
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/manifest.json")
async def manifest() -> JSONResponse:
    """Return the Omi plugin manifest."""
    return JSONResponse(
        {
            "schema_version": "v1",
            "name_for_human": "Project Gutenberg Books",
            "name_for_model": "gutenberg_books_app",
            "description_for_human": "Search 70,000+ free classic books, authors, genres, and reading links from Project Gutenberg.",
            "description_for_model": "Search classic literature, authors, literary topics, and get free reading formats and EPUB download links.",
            "auth": {"type": "none"},
            "api": {
                "type": "openapi",
                "url": "/openapi.json",
                "is_user_authenticated": False,
            },
            "logo_url": "https://raw.githubusercontent.com/BasedHardware/omi/main/plugins/logos/books.png",
            "contact_email": "support@omi.me",
            "legal_info_url": "/privacy",
        }
    )


@app.get("/.well-known/ai-plugin.json")
async def ai_plugin_manifest() -> JSONResponse:
    """Return the OpenAI standard plugin manifest."""
    return await manifest()


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "app": "omi-gutendex-app"}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy() -> HTMLResponse:
    """Privacy policy declaration."""
    return HTMLResponse(
        """
        <html>
            <body>
                <h1>Privacy Policy</h1>
                <p>The Omi Project Gutenberg App does not collect or store personal user data. All search queries are sent directly to the public Gutendex API without storing identities.</p>
            </body>
        </html>
        """
    )
