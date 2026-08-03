"""UnifiedPush endpoint persistence (ADR-0011) — storage-port roundtrip + REST keying.

Mirrors the FCM token model in the ``unifiedpush_endpoints`` subcollection: save keyed by
device, list, and collection-group bulk cleanup of dead endpoints (HTTP 404/410). Exercised
against the in-memory FakeDocumentStore (same contract both real adapters honour).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402

import database.notifications as notification_db  # noqa: E402
from models.other import SaveUnifiedPushEndpointRequest  # noqa: E402
from routers import notifications as notif_router  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(notification_db, 'get_document_store', lambda: store)
    return store


def test_save_then_get_endpoints_roundtrip(fake_store):
    notification_db.save_endpoint(
        'user-1', {'endpoint': 'http://ntfy/topicA?up=1', 'time_zone': 'Europe/Rome', 'device_key': 'android_a'}
    )
    assert notification_db.get_all_endpoints('user-1') == ['http://ntfy/topicA?up=1']
    # time_zone mirrored onto the user doc (parity with save_token, for daily-summary tz queries).
    assert fake_store.get('users/user-1').to_dict().get('time_zone') == 'Europe/Rome'


def test_multiple_devices_are_kept_and_replace_per_device(fake_store):
    notification_db.save_endpoint(
        'u', {'endpoint': 'http://ntfy/a?up=1', 'time_zone': 'UTC', 'device_key': 'android_a'}
    )
    notification_db.save_endpoint('u', {'endpoint': 'http://ntfy/b?up=1', 'time_zone': 'UTC', 'device_key': 'ios_b'})
    assert sorted(notification_db.get_all_endpoints('u')) == ['http://ntfy/a?up=1', 'http://ntfy/b?up=1']

    # Re-registering the same device replaces its endpoint rather than accumulating a row.
    notification_db.save_endpoint(
        'u', {'endpoint': 'http://ntfy/a2?up=1', 'time_zone': 'UTC', 'device_key': 'android_a'}
    )
    assert sorted(notification_db.get_all_endpoints('u')) == ['http://ntfy/a2?up=1', 'http://ntfy/b?up=1']


def test_remove_bulk_endpoints_spans_users(fake_store):
    notification_db.save_endpoint('u1', {'endpoint': 'http://ntfy/dead?up=1', 'device_key': 'android_a'})
    notification_db.save_endpoint('u2', {'endpoint': 'http://ntfy/dead?up=1', 'device_key': 'android_b'})
    notification_db.save_endpoint('u2', {'endpoint': 'http://ntfy/live?up=1', 'device_key': 'ios_c'})

    notification_db.remove_bulk_endpoints(['http://ntfy/dead?up=1'])

    assert notification_db.get_all_endpoints('u1') == []
    assert notification_db.get_all_endpoints('u2') == ['http://ntfy/live?up=1']


def test_remove_bulk_endpoints_noop_on_empty(fake_store):
    notification_db.remove_bulk_endpoints([])  # must not raise or query


def test_router_composes_device_key_and_saves(monkeypatch):
    saved = {}
    monkeypatch.setattr(notif_router.notification_db, 'save_endpoint', lambda uid, data: saved.update(uid=uid, **data))

    resp = notif_router.save_unifiedpush_endpoint(
        data=SaveUnifiedPushEndpointRequest(endpoint='http://ntfy/t?up=1', time_zone='Europe/Rome'),
        uid='user-9',
        x_app_platform='android',
        x_device_id_hash='abc123',
    )

    assert resp.status == 'Ok'
    assert saved['uid'] == 'user-9'
    assert saved['device_key'] == 'android_abc123'
    assert saved['endpoint'] == 'http://ntfy/t?up=1'
    assert saved['time_zone'] == 'Europe/Rome'
