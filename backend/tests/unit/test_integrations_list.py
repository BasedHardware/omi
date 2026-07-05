"""Unit tests for GET /v1/integrations (list the user's integration connections).

Verifies the router endpoint's mapping and secret-stripping, and the db helper's
stream-into-dict behavior, using the sanctioned seams (import the modules normally
and patch.object on the singletons, no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import database.users as users_db
from routers import integrations as integrations_router


# ---------------------------------------------------------------------------
# Endpoint: mapping + secret stripping
# ---------------------------------------------------------------------------
def test_endpoint_maps_and_strips_secrets():
    raw = {
        'google_calendar': {'connected': True, 'access_token': 'SECRET', 'refresh_token': 'SECRET2'},
        'apple_health': {'connected': True, 'last_synced': '2026-07-04T00:00:00+00:00'},
        'whoop': {'connected': False, 'access_token': 'x'},
    }
    with patch.object(users_db, 'get_integrations', return_value=raw):
        resp = integrations_router.list_integrations(uid='u1')
    by_key = {s.app_key: s for s in resp.integrations}
    assert by_key['google_calendar'].connected is True
    assert by_key['google_calendar'].last_synced is None  # no last_synced recorded
    assert by_key['apple_health'].last_synced == '2026-07-04T00:00:00+00:00'
    assert by_key['whoop'].connected is False
    # Secrets never leave the endpoint: the summary model has no token fields at all.
    dumped = str(resp.model_dump())
    assert 'access_token' not in dumped
    assert 'refresh_token' not in dumped
    assert 'SECRET' not in dumped


def test_endpoint_empty_when_no_integrations():
    with patch.object(users_db, 'get_integrations', return_value={}):
        resp = integrations_router.list_integrations(uid='u1')
    assert resp.integrations == []


def test_endpoint_coerces_non_str_last_synced():
    raw = {'apple_health': {'connected': True, 'last_synced': datetime(2026, 7, 4, tzinfo=timezone.utc)}}
    with patch.object(users_db, 'get_integrations', return_value=raw):
        resp = integrations_router.list_integrations(uid='u1')
    assert resp.integrations[0].last_synced == '2026-07-04T00:00:00+00:00'


def test_endpoint_tolerates_none_doc():
    with patch.object(users_db, 'get_integrations', return_value={'weird': None}):
        resp = integrations_router.list_integrations(uid='u1')
    assert resp.integrations[0].app_key == 'weird'
    assert resp.integrations[0].connected is False


def test_endpoint_connected_coerces_strings_strictly():
    # A stored string 'false' must not be reported as connected (bool('false') is True).
    raw = {
        'a': {'connected': 'false'},
        'b': {'connected': 'true'},
        'c': {'connected': True},
        'd': {'connected': False},
        'e': {'connected': None},
    }
    with patch.object(users_db, 'get_integrations', return_value=raw):
        resp = integrations_router.list_integrations(uid='u1')
    assert {s.app_key: s.connected for s in resp.integrations} == {
        'a': False,
        'b': True,
        'c': True,
        'd': False,
        'e': False,
    }


# ---------------------------------------------------------------------------
# DB helper: stream into an app_key-keyed dict
# ---------------------------------------------------------------------------
def test_db_get_integrations_streams_into_dict():
    doc1 = MagicMock()
    doc1.id = 'google_calendar'
    doc1.to_dict.return_value = {'connected': True}
    doc2 = MagicMock()
    doc2.id = 'whoop'
    doc2.to_dict.return_value = {'connected': False}
    col = MagicMock()
    col.stream.return_value = [doc1, doc2]
    user_ref = MagicMock()
    user_ref.collection.return_value = col
    # Pass an explicit mock: patch.object's default path introspects the lazy db
    # proxy (hasattr __func__), which would construct a real Firestore client.
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = user_ref
    with patch.object(users_db, 'db', fake_db):
        out = users_db.get_integrations('u1')
    assert out == {'google_calendar': {'connected': True}, 'whoop': {'connected': False}}
    user_ref.collection.assert_called_once_with('integrations')


def test_db_get_integrations_empty():
    col = MagicMock()
    col.stream.return_value = []
    user_ref = MagicMock()
    user_ref.collection.return_value = col
    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = user_ref
    with patch.object(users_db, 'db', fake_db):
        assert users_db.get_integrations('u1') == {}
