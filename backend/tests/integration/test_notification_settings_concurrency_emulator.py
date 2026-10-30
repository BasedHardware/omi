"""Manual loopback proof; never uses production auth, records, or push tokens.

FIRESTORE_EMULATOR_HOST=127.0.0.1:10281 PYTHONPATH=backend \
  backend/.venv/bin/pytest -q backend/tests/integration/test_notification_settings_concurrency_emulator.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, get_ident
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import Aborted
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import _client, notifications
from routers import notifications as notification_routes, users as user_routes


@pytest.fixture
def settings(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('This proof requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-notification-settings', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', client)
    uid = uuid4().hex
    user = client.collection('users').document(uid)
    user.set({'synthetic_control': 'keep'})
    yield uid, client, user
    client.close()


def interleave_user_choice(monkeypatch, user, patch):
    """Commit the competing choice after an unsafe read, or before a transactional read.

    Firestore transactions protect their reads until commit. The transaction case
    therefore places the competing write before the first read, without fabricating
    stale transaction snapshots or deadlocking an emulator pessimistic lock.
    """
    original_get = DocumentReference.get
    fired = []

    def get(reference, *args, **kwargs):
        if reference.path != user.path or fired:
            return original_get(reference, *args, **kwargs)
        fired.append(True)
        if kwargs.get('transaction') is not None:
            user.update(patch)
            return original_get(reference, *args, **kwargs)
        snapshot = original_get(reference, *args, **kwargs)
        user.update(patch)
        return snapshot

    monkeypatch.setattr(DocumentReference, 'get', get)
    return fired


@pytest.mark.parametrize('writer', ['timezone', 'timezone_seed', 'token', 'hour'])
def test_default_writers_preserve_a_concurrent_opt_out(settings, monkeypatch, writer):
    uid, _, user = settings
    fired = interleave_user_choice(monkeypatch, user, {'daily_summary_enabled': False})
    if writer == 'timezone':
        notifications.set_user_time_zone(uid, 'Asia/Kolkata')
    elif writer == 'timezone_seed':
        notifications.set_user_time_zone_if_missing(uid, 'Asia/Kolkata')
    elif writer == 'token':
        notifications.save_token(uid, {'device_key': 'synthetic-device', 'fcm_token': 'not-a-real-token'})
    else:
        notifications.set_daily_summary_hour_local(uid, 0)
    assert fired
    stored = user.get().to_dict()
    assert stored['daily_summary_enabled'] is False
    assert stored['synthetic_control'] == 'keep'


@pytest.mark.parametrize('writer', ['timezone', 'token', 'enabled'])
def test_default_writers_preserve_a_concurrent_midnight_choice(settings, monkeypatch, writer):
    uid, _, user = settings
    fired = interleave_user_choice(monkeypatch, user, {'daily_summary_hour_local': 0})
    if writer == 'timezone':
        notifications.set_user_time_zone(uid, 'Asia/Kolkata')
    elif writer == 'token':
        notifications.save_token(uid, {'device_key': 'synthetic-device', 'fcm_token': 'not-a-real-token'})
    else:
        notifications.set_daily_summary_enabled(uid, False)
    assert fired
    assert user.get().to_dict()['daily_summary_hour_local'] == 0


def test_desktop_timezone_seed_preserves_a_concurrent_client_zone(settings, monkeypatch):
    uid, _, user = settings
    fired = interleave_user_choice(monkeypatch, user, {'time_zone': 'Asia/Tokyo'})
    written = notifications.set_user_time_zone_if_missing(uid, 'America/New_York')
    assert fired
    assert written is False
    assert user.get().to_dict()['time_zone'] == 'Asia/Tokyo'


@pytest.mark.parametrize('writer', ['timezone', 'timezone_seed', 'token', 'enabled', 'hour'])
def test_missing_user_retains_default_materialization(settings, writer):
    uid, _, user = settings
    user.delete()
    if writer == 'timezone':
        notifications.set_user_time_zone(uid, 'Asia/Kolkata')
    elif writer == 'timezone_seed':
        assert notifications.set_user_time_zone_if_missing(uid, 'Asia/Kolkata') is True
    elif writer == 'token':
        notifications.save_token(uid, {'device_key': 'synthetic-device', 'fcm_token': 'not-a-real-token'})
    elif writer == 'enabled':
        assert notifications.set_daily_summary_enabled(uid, False) is True
    else:
        assert notifications.set_daily_summary_hour_local(uid, 0) is True
    stored = user.get().to_dict()
    assert stored['daily_summary_enabled'] is (writer != 'enabled')
    assert stored['daily_summary_hour_local'] == (0 if writer == 'hour' else 22)


@pytest.mark.parametrize('exists', [False, True])
def test_simultaneous_first_preference_writes_preserve_both_explicit_choices(settings, monkeypatch, exists):
    uid, _, user = settings
    if not exists:
        user.delete()
    barrier = Barrier(2)
    seen = set()
    original_get = DocumentReference.get

    def get(reference, *args, **kwargs):
        if reference.path == user.path and get_ident() not in seen:
            seen.add(get_ident())
            barrier.wait(timeout=10)
        return original_get(reference, *args, **kwargs)

    with monkeypatch.context() as fault:
        fault.setattr(DocumentReference, 'get', get)
        with ThreadPoolExecutor(max_workers=2) as pool:
            enabled = pool.submit(notifications.set_daily_summary_enabled, uid, False)
            hour = pool.submit(notifications.set_daily_summary_hour_local, uid, 0)
            assert enabled.result(timeout=60) is True
            assert hour.result(timeout=60) is True
    stored = user.get().to_dict()
    assert stored['daily_summary_enabled'] is False
    assert stored['daily_summary_hour_local'] == 0


def test_read_time_abort_retries_on_fresh_transaction_and_current_preferences(settings, monkeypatch):
    uid, _, user = settings
    original_get = DocumentReference.get
    transactions = []

    def get(reference, *args, **kwargs):
        transaction = kwargs.get('transaction')
        if reference.path == user.path and transaction is not None:
            transactions.append(transaction)
            if len(transactions) == 1:
                user.update({'daily_summary_enabled': False, 'daily_summary_hour_local': 0})
                raise Aborted('synthetic read-time contention')
        return original_get(reference, *args, **kwargs)

    monkeypatch.setattr(DocumentReference, 'get', get)
    notifications.set_user_time_zone(uid, 'Asia/Kolkata')
    assert len(transactions) == 2 and transactions[0] is not transactions[1]
    stored = user.get().to_dict()
    assert stored['daily_summary_enabled'] is False
    assert stored['daily_summary_hour_local'] == 0


def test_write_rejection_leaves_settings_unchanged_and_propagates(settings, monkeypatch):
    uid, _, user = settings

    def reject(*args, **kwargs):
        raise RuntimeError('synthetic write rejection')

    monkeypatch.setattr(Transaction, 'update', reject)
    with pytest.raises(RuntimeError, match='synthetic write rejection'):
        notifications.set_user_time_zone(uid, 'Asia/Kolkata')
    assert user.get().to_dict() == {'synthetic_control': 'keep'}


@pytest.mark.parametrize(
    ('method', 'path', 'payload', 'choice'),
    [
        ('put', '/v1/users/time-zone', {'time_zone': 'Asia/Kolkata'}, {'daily_summary_enabled': False}),
        (
            'post',
            '/v1/users/fcm-token',
            {'fcm_token': 'not-a-real-token', 'time_zone': 'Asia/Kolkata'},
            {'daily_summary_enabled': False},
        ),
        ('patch', '/v1/users/daily-summary-settings', {'hour': 0}, {'daily_summary_enabled': False}),
        ('patch', '/v1/users/daily-summary-settings', {'enabled': False}, {'daily_summary_hour_local': 0}),
    ],
)
def test_actual_http_routes_preserve_the_competing_choice(settings, monkeypatch, method, path, payload, choice):
    uid, _, user = settings
    monkeypatch.setattr(notification_routes, 'emit_posthog_event', lambda *args, **kwargs: None)
    fired = interleave_user_choice(monkeypatch, user, choice)
    app = FastAPI()
    app.include_router(notification_routes.router)
    app.include_router(user_routes.router)
    app.dependency_overrides[user_routes.auth.get_current_user_uid] = lambda: uid
    with TestClient(app) as client:
        response = getattr(client, method)(path, json=payload)
        assert response.status_code == 200, response.text
        saved = client.get('/v1/users/daily-summary-settings').json()
    assert fired
    assert saved['enabled'] is False
    assert saved['hour'] == (22 if method in {'put', 'post'} else 0)
