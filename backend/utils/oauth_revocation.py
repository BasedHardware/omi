"""Best-effort upstream OAuth revocation for user integrations.

Deleting the local integration document only removes Omi's copy of the
credential — the grant stays live at the provider until the user revokes it in
the provider's own account settings. Every disconnect path and account deletion
must therefore also tell the provider to invalidate the token.

Every function here is best-effort: a provider outage, an expired token, or an
unconfigured client must never block a disconnect or an account deletion. All
failures are logged and swallowed; the return value only reports whether the
provider confirmed the revocation.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any, Iterable, Mapping, Optional

import httpx

from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

GOOGLE_REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
X_REVOKE_URL = 'https://api.x.com/2/oauth2/revoke'
ASANA_REVOKE_URL = 'https://app.asana.com/-/oauth_revoke'

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)

# Integrations stored under users/{uid}/integrations that hold a revocable grant.
REVOCABLE_INTEGRATION_KEYS = ('google_calendar', 'x')

# Integrations stored under users/{uid}/task_integrations that hold a revocable
# grant. 'todoist' and 'clickup' are intentionally absent: neither provider
# publishes an OAuth revocation endpoint, so there is nothing to call.
REVOCABLE_TASK_INTEGRATION_KEYS = ('google_tasks', 'asana')

_PROVIDER_BY_APP_KEY = {
    'google_calendar': 'google',
    'google_tasks': 'google',
    'x': 'x',
    'asana': 'asana',
}


def _credential(integration: Mapping[str, Any], *names: str) -> Optional[str]:
    for name in names:
        value = integration.get(name)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _revoke_google(integration: Mapping[str, Any]) -> bool:
    """Revoke a Google grant.

    Revoking the refresh token invalidates every access token derived from it,
    so prefer it; fall back to the access token when the grant was issued
    without offline access.
    """
    token = _credential(integration, 'refresh_token', 'access_token')
    if not token:
        return False
    response = httpx.post(
        GOOGLE_REVOKE_URL,
        data={'token': token},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=_TIMEOUT,
    )
    # Google answers 400 with error=invalid_token for an already-dead grant,
    # which is the desired end state, not a failure to retry.
    return response.status_code < 400 or response.status_code == 400


def _revoke_x(integration: Mapping[str, Any]) -> bool:
    client_id = os.getenv('X_OAUTH_CLIENT_ID')
    client_secret = os.getenv('X_OAUTH_CLIENT_SECRET')
    if not client_id or not client_secret:
        logger.info('oauth_revocation: X client is not configured; skipping upstream revoke')
        return False
    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    revoked = False
    for field, hint in (('refresh_token', 'refresh_token'), ('access_token', 'access_token')):
        token = _credential(integration, field)
        if not token:
            continue
        response = httpx.post(
            X_REVOKE_URL,
            data={'token': token, 'token_type_hint': hint, 'client_id': client_id},
            headers={
                'Authorization': f'Basic {basic}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            timeout=_TIMEOUT,
        )
        revoked = revoked or response.status_code < 400
    return revoked


def _revoke_asana(integration: Mapping[str, Any]) -> bool:
    client_id = os.getenv('ASANA_CLIENT_ID')
    client_secret = os.getenv('ASANA_CLIENT_SECRET')
    if not client_id or not client_secret:
        logger.info('oauth_revocation: Asana client is not configured; skipping upstream revoke')
        return False
    token = _credential(integration, 'refresh_token', 'access_token')
    if not token:
        return False
    response = httpx.post(
        ASANA_REVOKE_URL,
        data={'client_id': client_id, 'client_secret': client_secret, 'token': token},
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        timeout=_TIMEOUT,
    )
    return response.status_code < 400


_REVOKERS = {
    'google': _revoke_google,
    'x': _revoke_x,
    'asana': _revoke_asana,
}


def revoke_upstream(app_key: str, integration: Optional[Mapping[str, Any]]) -> bool:
    """Ask the provider to invalidate the stored grant for ``app_key``.

    Returns True only when the provider confirmed the revocation. Never raises:
    a failed upstream revoke must not block the local disconnect or deletion.
    """
    if not integration:
        return False
    provider = _PROVIDER_BY_APP_KEY.get(app_key)
    if provider is None:
        return False
    revoker = _REVOKERS[provider]
    try:
        revoked = revoker(integration)
    except Exception as e:
        logger.warning('oauth_revocation: upstream revoke failed for %s: %s', app_key, sanitize(str(e)))
        return False
    if not revoked:
        logger.warning('oauth_revocation: upstream revoke not confirmed for %s', app_key)
    return revoked


def revoke_integration_upstream(uid: str, app_key: str) -> bool:
    """Read the stored grant for ``app_key`` and revoke it at the provider.

    Reads and revokes inside one best-effort boundary so neither a Firestore
    read failure nor a provider outage can block the disconnect that follows.
    """
    import database.users as users_db

    try:
        integration = users_db.get_integration(uid, app_key)
    except Exception as e:
        logger.warning('oauth_revocation: could not read integration %s: %s', app_key, sanitize(str(e)))
        return False
    return revoke_upstream(app_key, integration)


def revoke_task_integration_upstream(uid: str, app_key: str) -> bool:
    """``revoke_integration_upstream`` for the task_integrations collection."""
    import database.users as users_db

    try:
        integration = users_db.get_task_integration(uid, app_key)
    except Exception as e:
        logger.warning('oauth_revocation: could not read task integration %s: %s', app_key, sanitize(str(e)))
        return False
    return revoke_upstream(app_key, integration)


def revoke_user_integrations(
    uid: str,
    *,
    integration_keys: Iterable[str] = REVOCABLE_INTEGRATION_KEYS,
    task_integration_keys: Iterable[str] = REVOCABLE_TASK_INTEGRATION_KEYS,
) -> int:
    """Revoke every upstream grant this user still holds.

    Called before the stored tokens are wiped — once the documents are gone
    there is no credential left to revoke with. Best-effort per provider so one
    dead provider cannot strand the rest.
    """
    revoked = 0
    for app_key in integration_keys:
        if revoke_integration_upstream(uid, app_key):
            revoked += 1
    for app_key in task_integration_keys:
        if revoke_task_integration_upstream(uid, app_key):
            revoked += 1
    return revoked
