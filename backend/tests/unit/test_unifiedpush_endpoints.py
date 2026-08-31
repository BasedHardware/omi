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
    # save_endpoint carries time_zone (the REST model requires it) and writes it onto the endpoint doc,
    # so the fan-out is a SINGLE collection-group query on the endpoints' time_zone — no per-user N+1.
    notification_db.save_endpoint(
        'u1', {'endpoint': 'http://ntfy/1?up=1', 'device_key': 'a', 'time_zone': 'Europe/Rome'}
    )
    notification_db.save_endpoint(
        'u2', {'endpoint': 'http://ntfy/2?up=1', 'device_key': 'b', 'time_zone': 'Europe/Rome'}
    )
    notification_db.save_endpoint(
        'u3', {'endpoint': 'http://ntfy/3?up=1', 'device_key': 'c', 'time_zone': 'America/New_York'}
    )

    got = notification_db.get_users_endpoints_in_timezones(['Europe/Rome'])
    assert sorted(_urls(got)) == ['http://ntfy/1?up=1', 'http://ntfy/2?up=1']  # NY user excluded


def test_timezone_chunk_failure_does_not_abort_other_chunks(fake_store, monkeypatch):
    # The user's timezone lands in the SECOND 30-chunk; the FIRST chunk's query raises. That chunk must
    # be logged and skipped, not abort the whole UnifiedPush morning fan-out (cubic review 4939247683).
    notification_db.save_endpoint('u9', {'endpoint': 'http://ntfy/9?up=1', 'device_key': 'z', 'time_zone': 'Zone/33'})

    real_query_group = fake_store.query_group
    seen = {'n': 0}

    def flaky_query_group(group, **kwargs):
        seen['n'] += 1
        if seen['n'] == 1:  # the first 30-timezone chunk's endpoint group query
            raise RuntimeError('chunk 1 store outage')
        return real_query_group(group, **kwargs)

    monkeypatch.setattr(fake_store, 'query_group', flaky_query_group)

    tzs = [f'Zone/{i}' for i in range(35)]  # 35 > 30 -> two chunks; 'Zone/33' is in the second
    got = notification_db.get_users_endpoints_in_timezones(tzs)
    assert _urls(got) == ['http://ntfy/9?up=1']  # second chunk delivered despite the first failing


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


def test_daily_summary_neutral_users_and_unifiedpush_endpoints_by_uid(monkeypatch):
    # cubic PR 10887 #427 (+B2): the DB helper is now backend-NEUTRAL — get_users_for_daily_summary returns
    # every eligible user (recipient filtering is the service's job), and the batched get_unifiedpush_
    # endpoints_by_uid keys endpoints by uid so the service composes the fan-out (a UnifiedPush user with an
    # endpoint is delivered to; one without is dropped at compose time, not by the user query).
    store = FakeDocumentStore()
    monkeypatch.setattr(notification_db, 'get_document_store', lambda: store)
    install_fake_db_client(monkeypatch, store=store)

    store.set('users/u-has', {'time_zone': 'UTC'})
    notification_db.save_endpoint(
        'u-has', {'endpoint': 'http://ntfy/a?up=1', 'device_key': 'android_a', 'time_zone': 'UTC'}
    )
    store.set('users/u-none', {'time_zone': 'UTC'})  # eligible user, no UnifiedPush endpoint

    # Neutral: BOTH eligible users come back (no recipient decision in the DB layer)
    users = notification_db.get_users_for_daily_summary(['UTC'], notification_db.DEFAULT_DAILY_SUMMARY_HOUR_LOCAL)
    assert {u[0] for u in users} == {'u-has', 'u-none'}
    assert all(isinstance(u[1], dict) for u in users)  # (uid, user_data, time_zone) shape

    # Batched endpoint reader keys by uid and includes only users who registered an endpoint
    by_uid = notification_db.get_unifiedpush_endpoints_by_uid(['UTC'])
    assert set(by_uid) == {'u-has'} and len(by_uid['u-has']) == 1  # u-none dropped at compose time


def test_get_fcm_tokens_for_users_reads_subcollection_and_legacy(monkeypatch):
    # cubic PR 10887 #427: the FCM recipient composition moved to a neutral batched DB read — subcollection
    # fcm_tokens + the legacy user.fcm_token, keyed by uid (deduped), for the service to compose the fan-out.
    store = FakeDocumentStore()
    monkeypatch.setattr(notification_db, 'get_document_store', lambda: store)
    install_fake_db_client(monkeypatch, store=store)
    store.set('users/u1', {'time_zone': 'UTC', 'fcm_token': 'legacy-1'})
    store.set('users/u1/fcm_tokens/d1', {'token': 't-a'})
    store.set('users/u2', {'time_zone': 'UTC'})  # eligible, no tokens

    users = [('u1', {'fcm_token': 'legacy-1'}, 'UTC'), ('u2', {}, 'UTC')]
    tokens = notification_db.get_fcm_tokens_for_users(users)
    assert set(tokens['u1']) == {'t-a', 'legacy-1'}  # subcollection + legacy, deduped
    assert tokens['u2'] == []  # no deliverable recipient -> dropped by the service's compose step
