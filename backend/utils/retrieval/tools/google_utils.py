"""
Shared utilities for Google OAuth integrations (Calendar, Gmail, etc.).
"""

import asyncio
import os
from typing import Optional

import httpx

import database.users as users_db
from utils.http_client import get_auth_client
from utils.log_sanitizer import sanitize
import logging

logger = logging.getLogger(__name__)

# Transient HTTP status codes that should be retried
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Max retries for transient failures
_MAX_RETRIES = 3


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
    def is_retryable(self) -> bool:
        return self.status_code in _RETRYABLE_STATUS_CODES


async def refresh_google_token(uid: str, integration: dict) -> Optional[str]:
    """
    Refresh Google access token using refresh token.
    Works for both Calendar and Gmail since they use the same OAuth.

    Args:
        uid: User ID
        integration: Integration dict containing refresh_token

    Returns:
        New access token or None if refresh failed
    """
    refresh_token = integration.get('refresh_token')
    if not refresh_token:
        logger.warning(f"🔄 No refresh_token stored for uid={uid}, cannot refresh")
        return None

    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        logger.error("🔄 Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET env vars")
        return None

    try:
        client = get_auth_client()
        response = await client.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            },
        )

        if response.status_code == 200:
            token_data = response.json()
            new_access_token = token_data.get('access_token')

            if new_access_token:
                # Update stored token
                integration['access_token'] = new_access_token
                users_db.set_integration(uid, 'google_calendar', integration)
                logger.info(f"🔄 Successfully refreshed Google token for uid={uid}")
                return new_access_token

        # Detect token revocation (invalid_grant) — user revoked access in Google settings
        error_body = sanitize(response.text[:200]) if response.text else "No error body"
        if response.status_code == 400 and 'invalid_grant' in (response.text or '').lower():
            logger.error(
                f"🔄 Google refresh token revoked for uid={uid} (invalid_grant). "
                f"User needs to reconnect. Response: {error_body}"
            )
        else:
            logger.error(
                f"🔄 Google token refresh failed for uid={uid}: " f"status={response.status_code}, body={error_body}"
            )
    except httpx.TimeoutException:
        logger.error(f"🔄 Timeout refreshing Google token for uid={uid}")
    except httpx.ConnectError:
        logger.error(f"🔄 Network error refreshing Google token for uid={uid}")
    except Exception as e:
        logger.error(f"🔄 Unexpected error refreshing Google token for uid={uid}: {e}")

    return None


async def google_api_request(
    method: str,
    url: str,
    access_token: str,
    params: dict | None = None,
    body: dict | None = None,
    allow_204: bool = False,
):
    """
    Make a Google API request with automatic retry for transient failures.

    Retries on 429 (rate limit) and 5xx (server errors) with exponential backoff.
    Raises GoogleAPIError with status_code for structured error handling upstream.
    Raises httpx.TimeoutException / httpx.ConnectError for network failures.
    """
    logger.info(f"🌐 Google API {method.upper()} {url}")

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
            logger.warning(f"🌐 Timeout on attempt {attempt + 1}/{_MAX_RETRIES} for {method.upper()} {url}")
            last_error = httpx.TimeoutException(f"Timeout calling {url}")
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)
            continue
        except httpx.ConnectError as e:
            logger.warning(f"🌐 Network error on attempt {attempt + 1}/{_MAX_RETRIES} for {method.upper()} {url}: {e}")
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
                    f"�� Server error {r.status_code}, retrying in {delay}s (attempt {attempt + 1}/{_MAX_RETRIES})"
                )
            await asyncio.sleep(delay)
            continue

        # Non-retryable error — raise immediately
        raise GoogleAPIError(r.status_code, snippet)

    # All retries exhausted
    if last_error and isinstance(last_error, (httpx.TimeoutException, httpx.ConnectError)):
        raise last_error
    raise GoogleAPIError(r.status_code, sanitize(r.text[:200]) if r.text else "No error body")
