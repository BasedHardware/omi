"""
Shared utilities for Google OAuth integrations (Calendar, Gmail, etc.).
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx
from google.cloud import firestore

import database.users as users_db
from utils.executors import db_executor, run_blocking
from utils.http_client import get_auth_client
from utils.integration_telemetry import (
    GOOGLE_CALENDAR,
    IntegrationTelemetryContext,
    emit_auth_refresh_attempted,
    emit_auth_refresh_failed,
    emit_auth_refresh_succeeded,
)
from utils.integrations_registry import (
    GMAIL_READ_SCOPE,
    INTEGRATION_PROVIDERS,
    oauth_scopes,
)
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Google Calendar and Gmail share a single OAuth grant stored under this key.
GOOGLE_INTEGRATION_KEY = 'google_calendar'

GMAIL_READONLY_SCOPE = GMAIL_READ_SCOPE

# Scopes requested when the user connects their Google account. Derived from the
# registry that builds the consent request, so the scopes we ask for and the ones
# `google_integration_has_scope` verifies a stored grant against cannot drift: a
# scope requested but never verified is unenforced, and one required but never
# requested reads as ungranted forever and loops the user through reconnect.
GOOGLE_OAUTH_SCOPES = oauth_scopes(INTEGRATION_PROVIDERS[GOOGLE_INTEGRATION_KEY])


def google_integration_has_scope(integration: Optional[Dict[str, Any]], scope: str) -> bool:
    """Whether a stored Google integration was granted `scope`.

    Grants created before a scope was requested have no `granted_scopes` field, so
    they read as not granted and the user is asked to reconnect.
    """
    if not integration:
        return False
    return scope in (integration.get('granted_scopes') or [])


from utils.retrieval.google_transport import GoogleAPIError as GoogleAPIError
from utils.retrieval.google_transport import google_api_request as google_api_request


async def _mark_google_integration_reauth_required(
    uid: str, integration: dict[str, Any], integration_key: str, reason: str
) -> None:
    updated = dict(integration)
    updated['connected'] = False
    updated['reauth_required'] = True
    updated['reauth_reason'] = reason
    updated['access_token'] = firestore.DELETE_FIELD
    await run_blocking(db_executor, users_db.set_integration, uid, integration_key, updated)


async def refresh_google_token(
    uid: str,
    integration: dict[str, Any],
    *,
    integration_name: str = GOOGLE_CALENDAR,
    integration_key: str = 'google_calendar',
) -> Optional[str]:
    """
    Refresh Google access token using refresh token.
    Works for both Calendar and Gmail since they use the same OAuth.

    Args:
        uid: User ID
        integration: Integration dict containing refresh_token
        integration_name: Product-visible provider name for telemetry.
        integration_key: Stored integration key to update after refresh.

    Returns:
        New access token or None if refresh failed
    """
    refresh_token = integration.get('refresh_token')
    telemetry_context = IntegrationTelemetryContext(
        integration_name=integration_name,
        operation='refresh_token',
        uid=uid,
    )
    emit_auth_refresh_attempted(telemetry_context)
    if not refresh_token:
        logger.warning(f"🔄 No refresh_token stored for uid={uid}, cannot refresh")
        emit_auth_refresh_failed(telemetry_context, 'missing_token')
        await _mark_google_integration_reauth_required(uid, integration, integration_key, 'missing_refresh_token')
        return None

    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        logger.error("🔄 Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET env vars")
        emit_auth_refresh_failed(telemetry_context, 'missing_oauth_config')
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
                # Update stored token — offload the sync Firestore write to the
                # DB executor so it does not block the event loop during
                # concurrent chat/tool streaming.
                integration['access_token'] = new_access_token
                await run_blocking(db_executor, users_db.set_integration, uid, integration_key, integration)
                logger.info(f"🔄 Successfully refreshed Google token for uid={uid}")
                emit_auth_refresh_succeeded(telemetry_context)
                return new_access_token

        # Detect token revocation (invalid_grant) — user revoked access in Google settings
        error_body = sanitize(response.text[:200]) if response.text else "No error body"
        if response.status_code == 400 and 'invalid_grant' in (response.text or '').lower():
            logger.error(
                f"🔄 Google refresh token revoked for uid={uid} (invalid_grant). "
                f"User needs to reconnect. Response: {error_body}"
            )
            await _mark_google_integration_reauth_required(uid, integration, integration_key, 'invalid_grant')
        else:
            logger.error(
                f"🔄 Google token refresh failed for uid={uid}: " f"status={response.status_code}, body={error_body}"
            )
        emit_auth_refresh_failed(
            telemetry_context, response.text or 'token_refresh_failed', provider_status_code=response.status_code
        )
    except httpx.TimeoutException:
        logger.error(f"🔄 Timeout refreshing Google token for uid={uid}")
        emit_auth_refresh_failed(telemetry_context, 'timeout')
    except httpx.ConnectError:
        logger.error(f"🔄 Network error refreshing Google token for uid={uid}")
        emit_auth_refresh_failed(telemetry_context, 'connect_error')
    except Exception as e:
        logger.error(f"🔄 Unexpected error refreshing Google token for uid={uid}: {e}")
        emit_auth_refresh_failed(telemetry_context, e)

    return None
