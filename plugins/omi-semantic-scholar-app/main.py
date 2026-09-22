import httpx
import logging
from typing import Any, Dict, Optional

# Configure a logger for this module
logger = logging.getLogger(__name__)

class ChatToolResponse:
    """
    Simple response wrapper used by the semantic scholar tool handlers.
    """
    def __init__(self, result: Optional[Any] = None, error: Optional[str] = None):
        self.result = result
        self.error = error

    def __repr__(self) -> str:
        return f"ChatToolResponse(result={self.result!r}, error={self.error!r})"

def _sanitize_error(message: str) -> str:
    """
    Return a user‑friendly error message that does not expose internal details.
    """
    return message

def search_papers(query: str) -> ChatToolResponse:
    """
    Search Semantic Scholar for papers matching the query.
    """
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {"query": query, "limit": 5}
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as exc:
        logger.error("Semantic Scholar request failed", exc_info=True)
        return ChatToolResponse(error=_sanitize_error(
            "Semantic Scholar request failed. Please try again later."
        ))
    except Exception as exc:
        logger.error("Unexpected error in search_papers", exc_info=True)
        return ChatToolResponse(error=_sanitize_error(
            "An unexpected error occurred. Please try again later."
        ))

def get_paper(paper_id: str) -> ChatToolResponse:
    """
    Retrieve detailed information for a specific paper by its Semantic Scholar ID.
    """
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
        params = {"fields": "title,abstract,authors,year,venue,referenceCount,citationCount"}
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as exc:
        logger.error("Semantic Scholar request failed", exc_info=True)
        return ChatToolResponse(error=_sanitize_error(
            "Semantic Scholar request failed. Please try again later."
        ))
    except Exception as exc:
        logger.error("Unexpected error in get_paper", exc_info=True)
        return ChatToolResponse(error=_sanitize_error(
            "An unexpected error occurred. Please try again later."
        ))

def get_author_papers(author_id: str) -> ChatToolResponse:
    """
    Retrieve a list of papers authored by the specified Semantic Scholar author ID.
    """
    try:
        url = f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
        params = {"fields": "title,year,venue", "limit": 10}
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as exc:
        logger.error("Semantic Scholar request failed", exc_info=True)
        return ChatToolResponse(error=_sanitize_error(
            "Semantic Scholar request failed. Please try again later."
        ))
    except Exception as exc:
        logger.error("Unexpected error in get_author_papers", exc_info=True)
        return ChatToolResponse(error=_sanitize_error(
            "An unexpected error occurred. Please try again later."
        ))
