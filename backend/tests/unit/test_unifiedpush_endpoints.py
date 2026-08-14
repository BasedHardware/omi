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
from tests.store_fakes import FakeDocumentStore, install_fake_db_client  # noqa: E402


@pytest.fixture
def fake_store(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(notification_db, 'get_document_store', lambda: store)
    return store


def _urls(endpoints):
    return [e.url for e in endpoints]


def test_save_then_get_endpoints_roundtrip(fake_store):
    notification_db.save_endpoint(
        'user-1', {'endpoint': 'http://ntfy/topicA?up=1', 'time_zone': 'Europe/Rome', 'device_key': 'android_a'}
    )
    assert _urls(notification_db.get_all_endpoints('user-1')) == ['http://ntfy/topicA?up=1']
    # time_zone mirrored onto the user doc (parity with save_token, for daily-summary tz queries).
    assert fake_store.get('users/user-1').to_dict().get('time_zone') == 'Europe/Rome'


def test_webpush_key_set_is_persisted_and_returned(fake_store):
    notification_db.save_endpoint(
        'user-k',
        {
            'endpoint': 'http://ntfy/enc?up=1',
            'time_zone': 'UTC',
            'device_key': 'android_a',
            'p256dh': 'BPk_publickey',
            'auth': 'YXV0aA',
        },
    )
    (endpoint,) = notification_db.get_all_endpoints('user-k')
    assert endpoint.url == 'http://ntfy/enc?up=1'
    assert endpoint.p256dh == 'BPk_publickey'
    assert endpoint.auth == 'YXV0aA'


def test_endpoint_without_keys_has_none_key_set(fake_store):
    notification_db.save_endpoint('u', {'endpoint': 'http://ntfy/plain?up=1', 'device_key': 'a'})
    (endpoint,) = notification_db.get_all_endpoints('u')
    assert endpoint.p256dh is None and endpoint.auth is None


def test_multiple_devices_are_kept_and_replace_per_device(fake_store):
    notification_db.save_endpoint(
        'u', {'endpoint': 'http://ntfy/a?up=1', 'time_zone': 'UTC', 'device_key': 'android_a'}
    )
    notification_db.save_endpoint('u', {'endpoint': 'http://ntfy/b?up=1', 'time_zone': 'UTC', 'device_key': 'ios_b'})
    assert sorted(_urls(notification_db.get_all_endpoints('u'))) == ['http://ntfy/a?up=1', 'http://ntfy/b?up=1']

    # Re-registering the same device replaces its endpoint rather than accumulating a row.
    notification_db.save_endpoint(
        'u', {'endpoint': 'http://ntfy/a2?up=1', 'time_zone': 'UTC', 'device_key': 'android_a'}
    )
    assert sorted(_urls(notification_db.get_all_endpoints('u'))) == ['http://ntfy/a2?up=1', 'http://ntfy/b?up=1']


def test_remove_bulk_endpoints_spans_users(fake_store):
    notification_db.save_endpoint('u1', {'endpoint': 'http://ntfy/dead?up=1', 'device_key': 'android_a'})
    notification_db.save_endpoint('u2', {'endpoint': 'http://ntfy/dead?up=1', 'device_key': 'android_b'})
    notification_db.save_endpoint('u2', {'endpoint': 'http://ntfy/live?up=1', 'device_key': 'ios_c'})

    notification_db.remove_bulk_endpoints(['http://ntfy/dead?up=1'])

    assert notification_db.get_all_endpoints('u1') == []
    assert _urls(notification_db.get_all_endpoints('u2')) == ['http://ntfy/live?up=1']


def test_remove_bulk_endpoints_noop_on_empty(fake_store):
    notification_db.remove_bulk_endpoints([])  # must not raise or query


def test_get_users_endpoints_in_timezones(fake_store):
    fake_store.set('users/u1', {'time_zone': 'Europe/Rome'})
    fake_store.set('users/u2', {'time_zone': 'Europe/Rome'})
    fake_store.set('users/u3', {'time_zone': 'America/New_York'})
    notification_db.save_endpoint('u1', {'endpoint': 'http://ntfy/1?up=1', 'device_key': 'a'})
    notification_db.save_endpoint('u2', {'endpoint': 'http://ntfy/2?up=1', 'device_key': 'b'})
    notification_db.save_endpoint('u3', {'endpoint': 'http://ntfy/3?up=1', 'device_key': 'c'})

    got = notification_db.get_users_endpoints_in_timezones(['Europe/Rome'])
    assert sorted(_urls(got)) == ['http://ntfy/1?up=1', 'http://ntfy/2?up=1']  # NY user excluded


def test_router_composes_device_key_and_saves(monkeypatch):
    saved = {}
    monkeypatch.setattr(notif_router.notification_db, 'save_endpoint', lambda uid, data: saved.update(uid=uid, **data))

    resp = notif_router.save_unifiedpush_endpoint(
        data=SaveUnifiedPushEndpointRequest(
            endpoint='http://ntfy/t?up=1', time_zone='Europe/Rome', p256dh='BPk_pub', auth='YXV0aA'
        ),
        uid='user-9',
        x_app_platform='android',
        x_device_id_hash='abc123',
    )

    assert resp.status == 'Ok'
    assert saved['uid'] == 'user-9'
    assert saved['device_key'] == 'android_abc123'
    assert saved['endpoint'] == 'http://ntfy/t?up=1'
    assert saved['time_zone'] == 'Europe/Rome'
    # WebPush keys flow through the router to storage so the send channel can encrypt.
    assert saved['p256dh'] == 'BPk_pub'
    assert saved['auth'] == 'YXV0aA'


def test_save_endpoint_rejects_device_key_with_slash(fake_store):
    # cubic PR 10887 B1: a device_key containing '/' builds an invalid logical path (Firestore rejects
    # the odd segment count; Mongo stores it outside the endpoints collection). Reject at the boundary.
    with pytest.raises(ValueError):
        notification_db.save_endpoint('u', {'endpoint': 'http://ntfy/x?up=1', 'device_key': 'android_a/b'})
    assert notification_db.get_all_endpoints('u') == []  # nothing was stored at a corrupt path


def test_endpoint_request_requires_both_or_neither_webpush_keys():
    # cubic PR 10887 B4: a half-set p256dh/auth silently downgrades to plaintext (the channel encrypts
    # only when both are present). Reject a malformed pair at registration.
    from pydantic import ValidationError

    SaveUnifiedPushEndpointRequest(endpoint='e', time_zone='UTC', p256dh='p', auth='a')  # both -> ok
    SaveUnifiedPushEndpointRequest(endpoint='e', time_zone='UTC')  # neither -> ok
    with pytest.raises(ValidationError):
        SaveUnifiedPushEndpointRequest(endpoint='e', time_zone='UTC', p256dh='p')  # only one -> rejected
    with pytest.raises(ValidationError):
        SaveUnifiedPushEndpointRequest(endpoint='e', time_zone='UTC', auth='a')


def test_get_users_endpoints_in_timezones_chunks_over_30(fake_store):
    # cubic PR 10887 B3: a Firestore 'in' filter rejects >30 values, so the timezone list must be
    # chunked; register endpoints across 35 distinct timezones and expect all resolved (no crash).
    tzs = [f"Zone/{i}" for i in range(35)]
    for i, tz in enumerate(tzs):
        notification_db.save_endpoint(
            f"u{i}", {"endpoint": f"http://ntfy/{i}?up=1", "device_key": f"android_{i}", "time_zone": tz}
        )
    eps = notification_db.get_users_endpoints_in_timezones(tzs)
    assert len(eps) == 35  # every timezone chunk was queried and its endpoints aggregated


def test_daily_summary_includes_unifiedpush_users_without_fcm_tokens(monkeypatch):
    # cubic PR 10887 B2: in a UnifiedPush deployment nobody has FCM tokens, so the "no tokens -> skip"
    # dropped EVERY user and sent zero daily summaries. With backend=unifiedpush the fan-out must
    # include a user who has endpoints (by uid; the per-user send resolves endpoints), and still skip
    # a user with none.
    store = FakeDocumentStore()
    monkeypatch.setattr(notification_db, 'get_document_store', lambda: store)
    install_fake_db_client(monkeypatch, store=store)
    monkeypatch.setenv('PUSH_NOTIFICATION_BACKEND', 'unifiedpush')

    notification_db.save_endpoint(
        'u-has', {'endpoint': 'http://ntfy/a?up=1', 'device_key': 'android_a', 'time_zone': 'UTC'}
    )
    store.set('users/u-none', {'time_zone': 'UTC'})  # same tz/hour, but no UnifiedPush endpoint

    users = notification_db.get_users_for_daily_summary(['UTC'], notification_db.DEFAULT_DAILY_SUMMARY_HOUR_LOCAL)
    uids = {u[0] for u in users}
    assert 'u-has' in uids  # UnifiedPush user is included (was skipped before this fix)
    assert 'u-none' not in uids  # a user with no deliverable recipient is still skipped
