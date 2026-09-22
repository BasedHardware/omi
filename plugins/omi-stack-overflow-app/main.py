"""omi-stack-overflow-app plugin entry point.

This module provides three chat‑tool handlers that query the Stack Overflow
API via ``httpx``:

* ``search_questions`` – search for questions matching a query string.
* ``get_question`` – retrieve a single question by its ID.
* ``get_top_answers`` – fetch the top‑voted answers for a given question.

All handlers return a :class:`ChatToolResponse`.  Previously, when an
``httpx.HTTPError`` was raised the raw exception message was propagated to the
user via ``ChatToolResponse(error=...)``.  This leaked internal networking
details and could expose proxy IPs or library internals.  The implementation
below sanitises error messages while still logging the full traceback for
operators.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

# Import the response model used by the chat‑tool framework.
# The actual import path may differ depending on the host application.
# Adjust if necessary.
try:
    from chat_tool import ChatToolResponse  # type: ignore
except Exception:  # pragma: no cover
    # Fallback stub for type‑checking / isolated test environments.
    from dataclasses import dataclass

    @dataclass
    class ChatToolResponse:
        content: Optional[str] = None
        error: Optional[str] = None

# Configure a module‑level logger.
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper utilities
# --------------------------------------------------------------------------- #

def _sanitize_error() -> str:
    """Return a user‑facing, generic error message.

    The message purposefully avoids leaking any internal details while still
    being helpful enough for end‑users.
    """
    return (
        "An error occurred while communicating with Stack Overflow. "
        "Please try again later."
    )

def _handle_http_error(func_name: str, exc: Exception) -> ChatToolResponse:
    """Log the exception with traceback and return a sanitized response."""
    logger.error(
        "HTTP error in %s: %s", func_name, exc, exc_info=True
    )
    return ChatToolResponse(error=_sanitize_error())

def _handle_unexpected_error(func_name: str, exc: Exception) -> ChatToolResponse:
    """Catch‑all for non‑httpx exceptions – log and sanitise."""
    logger.error(
        "Unexpected error in %s: %s", func_name, exc, exc_info=True
    )
    return ChatToolResponse(error=_sanitize_error())

# --------------------------------------------------------------------------- #
# Public chat‑tool handlers
# --------------------------------------------------------------------------- #

def search_questions(query: str, max_results: int = 5) -> ChatToolResponse:
    """Search Stack Overflow for questions matching *query*.

    Parameters
    ----------
    query:
        The search string supplied by the user.
    max_results:
        Upper bound on the number of questions to return.

    Returns
    -------
    ChatToolResponse
        ``content`` contains a markdown‑formatted list of questions on success,
        otherwise ``error`` contains a generic, user‑safe message.
    """
    url = "https://api.stackexchange.com/2.3/search/advanced"
    params: Dict[str, Any] = {
        "order": "desc",
        "sort": "relevance",
        "site": "stackoverflow",
        "q": query,
        "filter": "!9_bDDxJY5",  # lightweight filter – adjust as needed
        "pagesize": max_results,
    }

    try:
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return ChatToolResponse(content="No matching questions were found.")
        lines: List[str] = []
        for item in items:
            title = item.get("title", "Untitled")
            link = item.get("link", "#")
            lines.append(f"- [{title}]({link})")
        return ChatToolResponse(content="\n".join(lines))
    except httpx.HTTPError as exc:  # pragma: no cover – exercised via tests
        return _handle_http_error("search_questions", exc)
    except Exception as exc:  # pragma: no cover – defensive
        return _handle_unexpected_error("search_questions", exc)


def get_question(question_id: int) -> ChatToolResponse:
    """Retrieve a single Stack Overflow question by its *question_id*.

    Returns a markdown‑formatted representation of the question on success.
    """
    url = f"https://api.stackexchange.com/2.3/questions/{question_id}"
    params = {
        "order": "desc",
        "sort": "activity",
        "site": "stackoverflow",
        "filter": "!9_bDDxJY5",
    }

    try:
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return ChatToolResponse(content="Question not found.")
        q = items[0]
        title = q.get("title", "Untitled")
        body = q.get("body_markdown", "")
        link = q.get("link", "#")
        markdown = f"### [{title}]({link})\n\n{body}"
        return ChatToolResponse(content=markdown)
    except httpx.HTTPError as exc:  # pragma: no cover
        return _handle_http_error("get_question", exc)
    except Exception as exc:  # pragma: no cover
        return _handle_unexpected_error("get_question", exc)


def get_top_answers(question_id: int, max_answers: int = 3) -> ChatToolResponse:
    """Fetch the top‑voted answers for *question_id*.

    Returns a markdown list of answers on success.
    """
    url = f"https://api.stackexchange.com/2.3/questions/{question_id}/answers"
    params = {
        "order": "desc",
        "sort": "votes",
        "site": "stackoverflow",
        "filter": "!9_bDDxJY5",
        "pagesize": max_answers,
    }

    try:
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return ChatToolResponse(content="No answers were found for this question.")
        lines: List[str] = []
        for ans in items:
            body = ans.get("body_markdown", "")
            link = ans.get("link", "#")
            lines.append(f"- [{link}] {body[:200].replace('\\n', ' ')}...")
        return ChatToolResponse(content="\n".join(lines))
    except httpx.HTTPError as exc:  # pragma: no cover
        return _handle_http_error("get_top_answers", exc)
    except Exception as exc:  # pragma: no cover
        return _handle_unexpected_error("get_top_answers", exc)


# --------------------------------------------------------------------------- #
# Exported symbols for the plugin loader
# --------------------------------------------------------------------------- #

__all__ = [
    "search_questions",
    "get_question",
    "get_top_answers",
]
