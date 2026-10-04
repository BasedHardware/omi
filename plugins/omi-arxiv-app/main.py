<content>
import re
from typing import Any, Union

from omi.plugins.base import BasePlugin

# arXiv API constants
MAX_ARXIV_RESULTS = 300


class ArxivPlugin(BasePlugin):
    """ArXiv plugin for Omi."""

    name = "arxiv"

    def _clean_text(self, value: Any) -> str:
        """Clean text input for use in arXiv queries."""
        if value is None or isinstance(value, bool):
            return ""
        return str(value).strip()

    def _safe_limit(self, limit: Any, default: int = 5) -> int:
        """Ensure limit is a valid integer between 1 and MAX_ARXIV_RESULTS."""
        if isinstance(limit, bool):
            return default

        try:
            limit = int(limit)
        except (ValueError, TypeError):
            return default

        return max(1, min(limit, MAX_ARXIV_RESULTS))

    def _safe_paper_id(self, value: Any) -> str:
        """Clean and validate arXiv paper ID."""
        cleaned = self._clean_text(value)
        if not cleaned:
            return ""
        # Basic validation for arXiv ID format (e.g., 1234.56789 or 1234.56789v1)
        if not re.match(r"^\d+\.\d+(v\d+)?$", cleaned):
            return ""
        return cleaned

    def _tools(self):
        return [
            {
                "name": "search_author",
                "description": "Search for papers by a specific author on arXiv.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "author": {
                            "type": "string",
                            "description": "The name of the author to search for. Required.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": f"Maximum number of results to return (1-{MAX_ARXIV_RESULTS}). Defaults to 5.",
                        },
                    },
                    "required": ["author"],
                },
            },
            {
                "name": "search_papers",
                "description": "Search for papers on arXiv by keywords, title, or abstract.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string. Required.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": f"Maximum number of results to return (1-{MAX_ARXIV_RESULTS}). Defaults to 5.",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_paper",
                "description": "Retrieve details for a specific arXiv paper ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "The arXiv paper ID (e.g., 1234.56789). Required.",
                        },
                    },
                    "required": ["id"],
                },
            },
        ]

    def _handle_search_author(self, author: str, limit: int = 5) -> str:
        """Handle search for papers by author."""
        if not author:
            return "Missing required field: author"
        # Implementation would go here
        return f"Searching for papers by author: {author} with limit: {limit}"

    def _handle_search_papers(self, query: str, limit: int = 5) -> str:
        """Handle search for papers by query."""
        if not query:
            return "Missing required field: query"
        # Implementation would go here
        return f"Searching for papers with query: {query} with limit: {limit}"

    def _handle_get_paper(self, id: str) -> str:
        """Handle retrieval of a specific paper."""
        if not id:
            return "Missing required field: id"
        # Implementation would go here
        return f"Retrieving paper with ID: {id}"

    def execute_action(self, action: str, params: dict) -> str:
        """Execute an action with the given parameters."""
        if action == "search_author":
            author = self._clean_text(params.get("author"))
            limit = self._safe_limit(params.get("limit"))
            return self._handle_search_author(author, limit)
        elif action == "search_papers":
            query = self._clean_text(params.get("query"))
            limit = self._safe_limit(params.get("limit"))
            return self._handle_search_papers(query, limit)
        elif action == "get_paper":
            id = self._safe_paper_id(params.get("id"))
            return self._handle_get_paper(id)
        else:
            return f"Unknown action: {action}"
</content>