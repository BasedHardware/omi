"""
Semantic Scholar plugin for OMI.

This module provides three chat‑tool handlers:
- `search_papers`
- `get_paper`
- `get_author_papers`

All handlers now **sanitize** any exception details that are returned to the
user. Detailed tracebacks are logged internally, while the user receives a
generic, safe error message. This prevents leaking internal network,
proxy information or Python stack traces.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

# Import the OMI chat‑tool response model. The exact import path may vary
# depending on the host application – adjust if necessary.
try:
    # Preferred import when running inside the OMI framework
    from omi.chat_tools import ChatToolResponse
except Exception:  # pragma: no cover
    # Fallback stub for isolated testing environments
    from dataclasses import dataclass

    @dataclass
    class ChatToolResponse:
        """Minimal stub used only for type‑checking and tests."""
        content: Optional[str] = None
        error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Logging configuration
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Attach a default handler only when the library is used standalone.
    # In the real OMI environment the host application will configure logging.
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# --------------------------------------------------------------------------- #
# Sanitized error messages (public constants for testability)
# --------------------------------------------------------------------------- #
SANITIZED_HTTP_ERROR = (
    "Semantic Scholar request failed. Please try again later."
)
SANITIZED_UNEXPECTED_ERROR = (
    "An unexpected error occurred. Please try again later."
)


# --------------------------------------------------------------------------- #
# Helper – shared HTTP client
# --------------------------------------------------------------------------- #
def _get_client() -> httpx.AsyncClient:
    """
    Return a reusable async HTTP client configured for the Semantic Scholar API.
    """
    return httpx.AsyncClient(
        base_url="https://api.semanticscholar.org/graph/v1",
        timeout=10.0,
        follow_redirects=True,
    )


# --------------------------------------------------------------------------- #
# Chat‑tool handlers
# --------------------------------------------------------------------------- #
async def search_papers(query: str, limit: int = 10) -> ChatToolResponse:
    """
    Search for papers matching ``query`` and return a formatted list.

    Errors are logged with full traceback but only a generic message is sent
    back to the user.
    """
    try:
        async with _get_client() as client:
            resp = await client.get(
                "/paper/search",
                params={"query": query, "limit": limit, "fields": "title,authors,year"},
            )
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            formatted = "\n".join(
                f"{i + 1}. {p['title']} ({p.get('year', 'n/a')})"
                for i, p in enumerate(papers)
            )
            return ChatToolResponse(content=formatted or "No papers found.")
    except httpx.HTTPError as exc:
        # Detailed log for developers / ops
        logger.error(
            "Semantic Scholar HTTP error while searching papers: %s", exc, exc_info=True
        )
        # Sanitized message for the end‑user
        return ChatToolResponse(error=SANITIZED_HTTP_ERROR)
    except Exception as exc:  # pragma: no cover
        logger.error(
            "Unexpected error in search_papers handler: %s", exc, exc_info=True
        )
        return ChatToolResponse(error=SANITIZED_UNEXPECTED_ERROR)


async def get_paper(paper_id: str) -> ChatToolResponse:
    """
    Retrieve a single paper by its Semantic Scholar ID.
    """
    try:
        async with _get_client() as client:
            resp = await client.get(
                f"/paper/{paper_id}",
                params={"fields": "title,abstract,authors,year,venue"},
            )
            resp.raise_for_status()
            paper = resp.json()
            content = (
                f"**{paper.get('title', 'Untitled')}**\n"
                f"*Year:* {paper.get('year', 'n/a')}\n"
                f"*Venue:* {paper.get('venue', 'n/a')}\n\n"
                f"{paper.get('abstract', 'No abstract available.')}"
            )
            return ChatToolResponse(content=content)
    except httpx.HTTPError as exc:
        logger.error(
            "Semantic Scholar HTTP error while fetching paper %s: %s",
            paper_id,
            exc,
            exc_info=True,
        )
        return ChatToolResponse(error=SANITIZED_HTTP_ERROR)
    except Exception as exc:  # pragma: no cover
        logger.error(
            "Unexpected error in get_paper handler for %s: %s",
            paper_id,
            exc,
            exc_info=True,
        )
        return ChatToolResponse(error=SANITIZED_UNEXPECTED_ERROR)


async def get_author_papers(author_id: str, limit: int = 10) -> ChatToolResponse:
    """
    List papers authored by a given Semantic Scholar author ID.
    """
    try:
        async with _get_client() as client:
            resp = await client.get(
                f"/author/{author_id}/papers",
                params={"limit": limit, "fields": "title,year"},
            )
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            formatted = "\n".join(
                f"{i + 1}. {p['title']} ({p.get('year', 'n/a')})"
                for i, p in enumerate(papers)
            )
            return ChatToolResponse(content=formatted or "No papers found for this author.")
    except httpx.HTTPError as exc:
        logger.error(
            "Semantic Scholar HTTP error while fetching author %s papers: %s",
            author_id,
            exc,
            exc_info=True,
        )
        return ChatToolResponse(error=SANITIZED_HTTP_ERROR)
    except Exception as exc:  # pragma: no cover
        logger.error(
            "Unexpected error in get_author_papers handler for %s: %s",
            author_id,
            exc,
            exc_info=True,
        )
        return ChatToolResponse(error=SANITIZED_UNEXPECTED_ERROR)


# --------------------------------------------------------------------------- #
# Exported symbols for the plugin system
# --------------------------------------------------------------------------- #
__all__: List[str] = [
    "search_papers",
    "get_paper",
    "get_author_papers",
    "SANITIZED_HTTP_ERROR",
    "SANITIZED_UNEXPECTED_ERROR",
]
