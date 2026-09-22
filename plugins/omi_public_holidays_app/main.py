import logging
from typing import Any, Optional

import httpx

from .chat_tool_response import ChatToolResponse

# Configure a module‑level logger
logger = logging.getLogger(__name__)

# Generic, user‑safe error message
_SANITIZED_ERROR_MSG = (
    "An error occurred while processing your request. "
    "Please try again later."
)


def _handle_http_error(e: Exception, context: str) -> ChatToolResponse:
    """
    Log the exception with full traceback and return a sanitized error response.
    """
    logger.error(f"{context} failed: {e}", exc_info=True)
    return ChatToolResponse(error=_SANITIZED_ERROR_MSG)


def get_public_holidays(country: str, year: int) -> ChatToolResponse:
    """
    Fetch public holidays for a given country and year.
    """
    url = f"https://api.example.com/holidays?country={country}&year={year}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as e:
        return _handle_http_error(e, "get_public_holidays")


def get_next_public_holidays(country: str, count: int = 5) -> ChatToolResponse:
    """
    Fetch the next `count` public holidays for a given country.
    """
    url = f"https://api.example.com/holidays/next?country={country}&count={count}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as e:
        return _handle_http_error(e, "get_next_public_holidays")


def get_long_weekends(country: str, year: int) -> ChatToolResponse:
    """
    Fetch long weekend data for a given country and year.
    """
    url = f"https://api.example.com/holidays/long_weekends?country={country}&year={year}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as e:
        return _handle_http_error(e, "get_long_weekends")


def list_supported_countries() -> ChatToolResponse:
    """
    Retrieve a list of supported countries.
    """
    url = "https://api.example.com/holidays/countries"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as e:
        return _handle_http_error(e, "list_supported_countries")
