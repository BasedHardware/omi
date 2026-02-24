"""
Shared utilities for Google OAuth integrations (Calendar, Gmail, etc.).
"""

import os
from typing import Optional

import database.users as users_db
import requests
import logging

logger = logging.getLogger(__name__)


def refresh_google_token(uid: str, integration: dict) -> Optional[str]:
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
        return None

    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return None

    try:
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            },
            timeout=10.0,
        )

        if response.status_code == 200:
            token_data = response.json()
            new_access_token = token_data.get('access_token')

            if new_access_token:
                # Update stored token
                integration['access_token'] = new_access_token
                users_db.set_integration(uid, 'google_calendar', integration)
                return new_access_token
    except Exception as e:
        logger.error(f"Error refreshing Google token: {e}")

    return None


def google_api_request(
    method: str,
    url: str,
    access_token: str,
    params: dict | None = None,
    body: dict | None = None,
    allow_204: bool = False,
):
    logger.info(f"🌐 Google API {method.upper()} {url}")

    r = requests.request(
        method=method,
        url=url,
        headers={"Authorization": f"Bearer {access_token}"},
        json=body,
        params=params,
        timeout=10,
    )

    logger.info(f"🔎 Status {r.status_code}")

    if allow_204 and r.status_code == 204:
        return None

    if r.status_code != 200:
        snippet = r.text[:200] if r.text else "No error body"
        raise Exception(f"Google API error {r.status_code}: {snippet}")

    return r.json()
