"""Gmail rides the Google Calendar OAuth grant, so its connection state is a scope question.

Gmail has no grant of its own: `get_gmail_messages_tool` calls the Gmail API with the
access token stored under `google_calendar`. A grant minted before the Gmail scope was
requested still says `connected: True`, and using it against Gmail fails with an opaque
403. Connection status, OAuth initiation, disconnect and the tool itself must therefore
all resolve through the source grant and its *granted* scopes.
"""

from typing import Any, Dict, Optional
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

import routers.integrations as integrations_router
from utils.retrieval.tools import gmail_tools
from utils.retrieval.tools.google_utils import (
    GMAIL_READONLY_SCOPE,
    GOOGLE_OAUTH_SCOPES,
    google_integration_has_scope,
)

CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'

GRANT_WITH_GMAIL = {
    'connected': True,
    'access_token': 'token',
    'granted_scopes': [CALENDAR_SCOPE, GMAIL_READONLY_SCOPE],
}
# Pre-Gmail grant: connected, but the token carries no Gmail scope.
LEGACY_GRANT = {'connected': True, 'access_token': 'token'}


@pytest.fixture
def stored_grants(monkeypatch):
    """Back `users_db.get_integration` with an in-memory grant store."""
    grants: Dict[str, Dict[str, Any]] = {}

    def fake_get_integration(uid: str, app_key: str) -> Optional[Dict[str, Any]]:
        return grants.get(app_key)

    monkeypatch.setattr(integrations_router.users_db, 'get_integration', fake_get_integration)
    return grants


def test_granted_scope_check_ignores_merely_requested_scopes():
    assert google_integration_has_scope(GRANT_WITH_GMAIL, GMAIL_READONLY_SCOPE) is True
    assert google_integration_has_scope(LEGACY_GRANT, GMAIL_READONLY_SCOPE) is False
    assert google_integration_has_scope(None, GMAIL_READONLY_SCOPE) is False


def test_connecting_google_requests_the_gmail_scope():
    assert GMAIL_READONLY_SCOPE in GOOGLE_OAUTH_SCOPES
    assert GMAIL_READONLY_SCOPE in integrations_router.AUTH_PROVIDERS['google_calendar']['query']['scope']


def test_gmail_is_disconnected_without_a_google_grant(stored_grants):
    assert integrations_router.get_integration('gmail', uid='u1').connected is False


def test_gmail_is_disconnected_when_the_google_grant_predates_the_gmail_scope(stored_grants):
    stored_grants['google_calendar'] = LEGACY_GRANT

    assert integrations_router.get_integration('google_calendar', uid='u1').connected is True
    # Calendar keeps working; only Gmail needs the user to re-consent.
    assert integrations_router.get_integration('gmail', uid='u1').connected is False


def test_gmail_is_connected_once_the_gmail_scope_is_granted(stored_grants):
    stored_grants['google_calendar'] = GRANT_WITH_GMAIL

    response = integrations_router.get_integration('gmail', uid='u1')
    assert response.connected is True
    assert response.app_key == 'gmail'


def test_disconnecting_gmail_deletes_the_google_grant(monkeypatch):
    deleted = []

    def fake_delete(uid: str, app_key: str) -> bool:
        deleted.append(app_key)
        return True

    monkeypatch.setattr(integrations_router.users_db, 'delete_integration', fake_delete)

    integrations_router.delete_integration('gmail', uid='u1')

    assert deleted == ['google_calendar']


def test_gmail_oauth_url_runs_the_google_flow(monkeypatch):
    stored_state: Dict[str, str] = {}

    class FakeRedis:
        def setex(self, key: str, ttl: int, value: str) -> None:
            stored_state[key] = value

    monkeypatch.setattr(integrations_router.redis_db, 'r', FakeRedis())
    monkeypatch.setenv('BASE_API_URL', 'https://api.example.com')
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'client-id')

    auth_url = integrations_router.get_oauth_url('gmail', uid='u1').auth_url

    params = parse_qs(urlparse(auth_url).query)
    assert GMAIL_READONLY_SCOPE in params['scope'][0]
    assert params['redirect_uri'] == ['https://api.example.com/v2/integrations/google-calendar/callback']
    # The callback validates state against the source key, so state must carry it.
    assert '"app_key": "google_calendar"' in next(iter(stored_state.values()))


async def test_gmail_tool_asks_for_reconnect_when_the_scope_is_missing():
    with patch.object(gmail_tools, 'prepare_access', return_value=('u1', LEGACY_GRANT, 'token', None)):
        result = await gmail_tools.get_gmail_messages_tool.ainvoke({})

    assert 'reconnect' in result.lower()


async def test_gmail_tool_queries_gmail_once_the_scope_is_granted():
    async def fake_retry_on_auth_async(*args, **kwargs):
        return [], None

    with (
        patch.object(gmail_tools, 'prepare_access', return_value=('u1', GRANT_WITH_GMAIL, 'token', None)),
        patch.object(gmail_tools, 'retry_on_auth_async', fake_retry_on_auth_async),
    ):
        result = await gmail_tools.get_gmail_messages_tool.ainvoke({})

    assert result == 'No emails found.'
