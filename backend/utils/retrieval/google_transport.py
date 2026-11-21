"""Dependency-safe Google REST transport.

This module deliberately sits outside ``utils.retrieval.tools``: that package's
``__init__`` eagerly imports ``calendar_tools``, which imports the calendar
selection helpers. Keeping the transport here lets those helpers import it at
module scope instead of resolving it inside a function to dodge the cycle.

Callers keep importing ``google_api_request`` / ``GoogleAPIError`` from
``utils.retrieval.tools.google_utils``; that module re-exports these names.
"""

import asyncio
import logging
import re
from typing import Any, Dict, Optional

import httpx

from utils.http_client import get_auth_client
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Transient HTTP status codes that should be retried
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Max retries for transient failures
_MAX_RETRIES = 3

# Calendar ids are frequently the calendar owner's email address (personal
# calendars, shared calendars, Workspace groups). Percent encoding does not
# redact them, so mask the path segment before any URL reaches the logs.
_CALENDAR_PATH_RE = re.compile(r'/calendars/[^/]+')

# Google reports quota exhaustion as HTTP 403, not 429. Treating that as a lost
# grant would silently drop a calendar and report a partial read as success.
_QUOTA_REASONS = (
    'ratelimitexceeded',
    'userratelimitexceeded',
    'quotaexceeded',
    'dailylimitexceeded',
)


def redacted_url(url: str) -> str:
    """Return `url` with any calendar identifier masked."""
    return _CALENDAR_PATH_RE.sub('/calendars/<redacted>', url)


class GoogleAPIError(Exception):
    """Structured exception for Google API failures."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Google API error {status_code}: {message}")

    @property
    def is_auth_error(self) -> bool:
        return self.status_code == 401 or 'invalid_grant' in self.message.lower()

    @property
    def is_rate_limit(self) -> bool:
        return self.status_code == 429

    @property
    def is_permission_error(self) -> bool:
        return self.status_code == 403

    @property
    def is_quota_error(self) -> bool:
        """Whether this failure is provider quota, not a revoked permission."""
        if self.status_code == 429:
            return True
        if self.status_code != 403:
            return False
        message = self.message.lower()
        return any(reason in message for reason in _QUOTA_REASONS)

    @property
    def is_retryable(self) -> bool:
        return self.status_code in _RETRYABLE_STATUS_CODES


async def google_api_request(
    method: str,
    url: str,
    access_token: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    allow_204: bool = False,
) -> Any:
    """
    Make a Google API request with automatic retry for transient failures.

    Retries on 429 (rate limit) and 5xx (server errors) with exponential backoff.
    Raises GoogleAPIError with status_code for structured error handling upstream.
    Raises httpx.TimeoutException / httpx.ConnectError for network failures.
    """
    safe_url = redacted_url(url)
    logger.info(f"🌐 Google API {method.upper()} {safe_url}")

    client = get_auth_client()
    last_error = None

    for attempt in range(_MAX_RETRIES):
        try:
            r = await client.request(
                method=method,
                url=url,
                headers={"Authorization": f"Bearer {access_token}"},
                json=body,
                params=params,
            )
        except httpx.TimeoutException:
            logger.warning(f"🌐 Timeout on attempt {attempt + 1}/{_MAX_RETRIES} for {method.upper()} {safe_url}")
            last_error = httpx.TimeoutException(f"Timeout calling {safe_url}")
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
            continue
        except httpx.ConnectError as e:
            logger.warning(
                f"🌐 Network error on attempt {attempt + 1}/{_MAX_RETRIES} for {method.upper()} {safe_url}: {e}"
            )
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
            continue

        logger.info(f"🔎 Status {r.status_code}")

        if allow_204 and r.status_code == 204:
            return None

        if r.status_code == 200:
            return r.json()

        snippet = sanitize(r.text[:200]) if r.text else "No error body"

        # Retry on transient errors with exponential backoff
        if r.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
            delay = 2**attempt
            if r.status_code == 429:
                # Respect Retry-After header if present
                retry_after = r.headers.get('Retry-After')
                if retry_after and retry_after.isdigit():
                    delay = max(delay, int(retry_after))
                logger.warning(f"🌐 Rate limited (429), retrying in {delay}s (attempt {attempt + 1}/{_MAX_RETRIES})")
            else:
                logger.warning(
                    f"🌐 Server error {r.status_code}, retrying in {delay}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                )
            await asyncio.sleep(delay)
            continue

        # Non-retryable error — raise immediately
        raise GoogleAPIError(r.status_code, snippet)

    # All retries exhausted
    if last_error:
        raise last_error
    # Unreachable with _MAX_RETRIES >= 1, but kept as a safety net
    raise GoogleAPIError(0, "All retries exhausted with no response")
