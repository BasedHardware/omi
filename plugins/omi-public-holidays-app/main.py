import logging
from typing import Any, Dict, List

import httpx

from .chat_tool_response import ChatToolResponse
from .config import API_BASE_URL, SUPPORTED_COUNTRIES

# Create a module‑level logger.  The existing code already uses a logger, but
# we make sure it is configured correctly for the sanitized error handling.
logger = logging.getLogger(__name__)

# Generic user‑friendly error message that is safe to expose.
_SANITIZED_ERROR_MESSAGE = (
    "An error occurred while fetching public holiday data. "
    "Please try again later."
)


def _handle_http_error(exc: httpx.HTTPError) -> ChatToolResponse:
    """
    Log the full exception details and return a sanitized error response.

    Parameters
    ----------
    exc : httpx.HTTPError
        The exception raised by the HTTP client.

    Returns
    -------
    ChatToolResponse
        A response containing a user‑safe error message.
    """
    # Log the detailed exception for debugging purposes.
    logger.error("HTTP error while calling public holidays API", exc_info=True)
    # Return a sanitized error message to the user.
    return ChatToolResponse(error=_SANITIZED_ERROR_MESSAGE)


def get_public_holidays(country: str, year: int) -> ChatToolResponse:
    """
    Retrieve public holidays for a given country and year.

    Parameters
    ----------
    country : str
        ISO 3166‑1 alpha‑2 country code.
    year : int
        The year for which to fetch holidays.

    Returns
    -------
    ChatToolResponse
        The API response or a sanitized error message.
    """
    url = f"{API_BASE_URL}/holidays/{country}/{year}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as exc:
        return _handle_http_error(exc)


def get_next_public_holidays(country: str, count: int = 5) -> ChatToolResponse:
    """
    Retrieve the next *count* public holidays for a given country.

    Parameters
    ----------
    country : str
        ISO 3166‑1 alpha‑2 country code.
    count : int, optional
        Number of upcoming holidays to return (default: 5).

    Returns
    -------
    ChatToolResponse
        The API response or a sanitized error message.
    """
    url = f"{API_BASE_URL}/holidays/{country}/next?count={count}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as exc:
        return _handle_http_error(exc)


def get_long_weekends(country: str, year: int) -> ChatToolResponse:
    """
    Retrieve long weekend information for a given country and year.

    Parameters
    ----------
    country : str
        ISO 3166‑1 alpha‑2 country code.
    year : int
        The year for which to fetch long weekend data.

    Returns
    -------
    ChatToolResponse
        The API response or a sanitized error message.
    """
    url = f"{API_BASE_URL}/long-weekends/{country}/{year}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        return ChatToolResponse(result=data)
    except httpx.HTTPError as exc:
        return _handle_http_error(exc)


def list_supported_countries() -> ChatToolResponse:
    """
    Return a list of supported country codes.

    Returns
    -------
    ChatToolResponse
        The list of supported countries.
    """
    try:
        # The list is static in the config; no HTTP call is required.
        return ChatToolResponse(result=SUPPORTED_COUNTRIES)
    except Exception as exc:  # pragma: no cover
        # This block should never be hit, but we keep it for safety.
        logger.error("Unexpected error while listing supported countries", exc_info=True)
        return ChatToolResponse(error=_SANITIZED_ERROR_MESSAGE)
