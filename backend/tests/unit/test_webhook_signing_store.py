"""Signing-secret storage (#20939): rotation grace, atomic rotate, encryption at rest, caching, fail-open reporting."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import redis

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import redis_db  # noqa: E402
from database import webhook_signing as store  # noqa: E402
from database.webhook_signing import WebhookSigningSecrets  # noqa: E402
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore  # noqa: E402
from utils import encryption  # noqa: E402

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
APP_DOC = ('plugins_data', 'app-1', 'webhook_signing', 'current')


class _FakePipeline:
    """Enough of redis-py's WATCH/MULTI/EXEC to prove the rotate loop re-reads after a collision."""

    def __init__(self, fake):
        self.fake = fake
        self.watched = None
        self.queued = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def watch(self, key):
        self.watched = key
        self.fake.watch_calls += 1

    def get(self, key):
        return self.fake.data.get(key)

    def multi(self):
        self.queued = []

    def set(self, key, value, ex=None):
        self.queued.append((key, value))

    def execute(self):
        if self.fake.collide_once:
            self.fake.collide_once = False
            # Another writer got there first; redis-py raises and the caller must start over.
            self.fake.set(self.watched, self.fake.collision_value)
            raise redis.exceptions.WatchError('watched key changed')
        for key, value in self.queued:
            self.fake.set(key, value)


class _FakeRedis:
    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.watch_calls = 0
        self.collide_once = False
        self.collision_value = b''

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value.encode() if isinstance(value, str) else value

    def delete(self, key):
        self.data.pop(key, None)

    def pipeline(self):
        return _FakePipeline(self)


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, firestore, path):
        self.firestore = firestore
        self.path = path

    def get(self):
        self.firestore.reads.append(self.path)
        return _Snapshot(self.firestore.docs.get(self.path))

    def set(self, data):
        self.firestore.docs[self.path] = data

    def delete(self):
        self.firestore.docs.pop(self.path, None)

    def collection(self, name):
        return _Collection(self.firestore, f'{self.path}/{name}')


class _Collection:
    def __init__(self, firestore, path):
        self.firestore = firestore
        self.path = path

    def document(self, name):
        return _Document(self.firestore, f'{self.path}/{name}')


class _FakeFirestore:
    """Plain get/set/delete double; the transactional rotate uses StrictFirestore instead."""

    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.reads: list[str] = []

    def collection(self, name):
        return _Collection(self, name)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(store, 'r', fake)
    monkeypatch.setattr(redis_db, 'r', fake)
    return fake


@pytest.fixture
def firestore():
    return _FakeFirestore()


@pytest.fixture
def fallback(monkeypatch):
    recorded = MagicMock()
    monkeypatch.setattr(store, 'record_fallback', recorded)
    store._UNSIGNED_REPORTED.clear()
    return recorded


def test_first_issue_has_no_previous_secret():
    record = WebhookSigningSecrets.issue('whsec_new', now=NOW)
    assert record.current == 'whsec_new'
    assert record.created_at == NOW
    assert record.previous is None and record.previous_valid_until is None
    assert record.active(NOW) == ['whsec_new']


def test_rotation_keeps_the_old_secret_signing_for_the_grace_window():
    old = WebhookSigningSecrets.issue('whsec_old', now=NOW - timedelta(days=30))
    rotated = WebhookSigningSecrets.issue('whsec_new', previous=old, now=NOW)
    assert rotated.previous == 'whsec_old'
    assert rotated.previous_valid_until == NOW + store.ROTATION_GRACE
    assert rotated.active(NOW) == ['whsec_new', 'whsec_old']
    assert rotated.active(NOW + store.ROTATION_GRACE - timedelta(seconds=1)) == ['whsec_new', 'whsec_old']
    assert rotated.active(NOW + store.ROTATION_GRACE) == ['whsec_new']


def test_second_rotation_drops_the_oldest_secret():
    first = WebhookSigningSecrets.issue('whsec_1', now=NOW)
    second = WebhookSigningSecrets.issue('whsec_2', previous=first, now=NOW)
    third = WebhookSigningSecrets.issue('whsec_3', previous=second, now=NOW)
    assert third.active(NOW) == ['whsec_3', 'whsec_2']


def test_user_record_round_trips_and_is_encrypted_at_rest(fake_redis):
    record = WebhookSigningSecrets.issue(
        'whsec_new', previous=WebhookSigningSecrets.issue('whsec_old', now=NOW), now=NOW
    )
    store.set_user_webhook_signing_db('uid-1', record)

    stored = fake_redis.data['users:uid-1:developer:webhook_signing'].decode()
    assert 'whsec_new' not in stored and 'whsec_old' not in stored
    assert json.loads(stored)['created_at'] == NOW.isoformat()

    assert store.get_user_webhook_signing_db('uid-1') == record
    # Another user's key cannot read this record even with the same ciphertext.
    fake_redis.data['users:uid-2:developer:webhook_signing'] = fake_redis.data['users:uid-1:developer:webhook_signing']
    assert store.get_user_webhook_signing_db('uid-2') is None

    store.delete_user_webhook_signing_db('uid-1')
    assert store.get_user_webhook_signing_db('uid-1') is None


def test_user_rotate_is_a_compare_and_set_that_composes_against_the_winner(fake_redis):
    first = store.rotate_user_webhook_signing_db('uid-1', 'whsec_first')
    assert first.previous is None
    assert store.get_user_webhook_signing_db('uid-1') == first

    # A concurrent rotation lands between our read and write: redis raises WatchError, we re-read
    # and the record we end up writing keeps *their* secret as previous, not the stale one.
    other = WebhookSigningSecrets.issue('whsec_concurrent', previous=first, now=NOW)
    fake_redis.collide_once = True
    fake_redis.collision_value = json.dumps(store._encode(other, 'uid-1'))
    rotated = store.rotate_user_webhook_signing_db('uid-1', 'whsec_second')
    assert rotated.current == 'whsec_second'
    assert rotated.previous == 'whsec_concurrent'
    assert fake_redis.watch_calls == 3
    assert store.get_user_webhook_signing_db('uid-1') == rotated


def test_user_rotate_gives_up_after_bounded_collisions(fake_redis, monkeypatch):
    class _AlwaysCollides(_FakePipeline):
        def execute(self):
            raise redis.exceptions.WatchError('busy')

    monkeypatch.setattr(fake_redis, 'pipeline', lambda: _AlwaysCollides(fake_redis))
    with pytest.raises(RuntimeError):
        store.rotate_user_webhook_signing_db('uid-1', 'whsec_x')
    assert fake_redis.watch_calls == store._ROTATE_ATTEMPTS


def test_unreadable_user_record_means_unsigned_reported_once_per_window(fake_redis, fallback, caplog):
    fake_redis.data['users:uid-1:developer:webhook_signing'] = b'{"current": "not-ciphertext", "created_at": "bad"}'
    with caplog.at_level(logging.ERROR, logger=store.__name__):
        for _ in range(5):
            assert store.get_user_webhook_signing_db('uid-1') is None
    errors = [rec for rec in caplog.records if rec.levelno == logging.ERROR and 'delivering unsigned' in rec.message]
    assert len(errors) == 1
    assert 'uid-1' in errors[0].message and 'malformed_doc' in errors[0].message
    fallback.assert_called_once_with(
        component='webhook', from_mode='signed', to_mode='unsigned', reason='malformed_doc', outcome='degraded'
    )
    # A different owner is a different incident and reports on its own.
    fake_redis.data['users:uid-2:developer:webhook_signing'] = fake_redis.data['users:uid-1:developer:webhook_signing']
    assert store.get_user_webhook_signing_db('uid-2') is None
    assert fallback.call_count == 2


def test_signing_secrets_use_their_own_key_domain(fake_redis, fallback):
    store.set_user_webhook_signing_db('uid-1', WebhookSigningSecrets.issue('whsec_new', now=NOW))
    sealed = json.loads(fake_redis.data['users:uid-1:developer:webhook_signing'])['current']
    # The user-data key for the same uid cannot open a signing secret.
    assert encryption.decrypt(sealed, 'uid-1') == sealed

    # Nor does a secret sealed under the user-data key read as a signing secret: unreadable,
    # so the destination is delivered unsigned and the fallback is reported.
    fake_redis.data['users:uid-1:developer:webhook_signing'] = json.dumps(
        {'current': encryption.encrypt('whsec_new', 'uid-1'), 'created_at': NOW.isoformat()}
    ).encode()
    assert store.get_user_webhook_signing_db('uid-1') is None
    fallback.assert_called_once_with(
        component='webhook', from_mode='signed', to_mode='unsigned', reason='malformed_doc', outcome='degraded'
    )


def test_app_record_lives_in_a_subcollection_not_on_the_app_document(fake_redis, firestore):
    record = WebhookSigningSecrets.issue('whsec_app', now=NOW)
    store.set_app_webhook_signing_db('app-1', record, firestore_client=firestore)
    assert list(firestore.docs) == ['plugins_data/app-1/webhook_signing/current']
    assert 'whsec_app' not in json.dumps(firestore.docs)
    assert store.get_app_webhook_signing_db('app-1', firestore_client=firestore) == record


def test_app_lookup_is_cached_including_the_no_secret_answer(fake_redis, firestore):
    assert store.get_app_webhook_signing_db('app-1', firestore_client=firestore) is None
    assert store.get_app_webhook_signing_db('app-1', firestore_client=firestore) is None
    assert firestore.reads == ['plugins_data/app-1/webhook_signing/current']

    record = WebhookSigningSecrets.issue('whsec_app', now=NOW)
    store.set_app_webhook_signing_db('app-1', record, firestore_client=firestore)
    # The write invalidates the cached "no secret", so the next delivery signs immediately.
    assert store.get_app_webhook_signing_db('app-1', firestore_client=firestore) == record
    assert store.get_app_webhook_signing_db('app-1', firestore_client=firestore) == record
    assert len(firestore.reads) == 2
    assert 'whsec_app' not in ''.join(value.decode() for value in fake_redis.data.values())

    store.delete_app_webhook_signing_db('app-1', firestore_client=firestore)
    assert store.get_app_webhook_signing_db('app-1', firestore_client=firestore) is None
    assert firestore.docs == {}


def test_app_record_is_bound_to_its_app_id(fake_redis, firestore, fallback):
    record = WebhookSigningSecrets.issue('whsec_app', now=NOW)
    store.set_app_webhook_signing_db('app-1', record, firestore_client=firestore)
    firestore.docs['plugins_data/app-2/webhook_signing/current'] = firestore.docs[
        'plugins_data/app-1/webhook_signing/current'
    ]
    assert store.get_app_webhook_signing_db('app-2', firestore_client=firestore) is None
    fallback.assert_called_once()


def test_app_rotate_runs_in_one_firestore_transaction_and_invalidates_the_cache(fake_redis):
    strict = StrictFirestore()
    first = store.rotate_app_webhook_signing_db('app-1', 'whsec_first', firestore_client=strict)
    assert first.previous is None
    assert set(strict.rows) == {APP_DOC}
    assert 'whsec_first' not in json.dumps(strict.rows[APP_DOC])

    # Prime the delivery cache, then rotate: the read happens inside the transaction (StrictFirestore
    # rejects a read after the write), the write is the composed record, and the cache is dropped so
    # the next delivery signs with both secrets.
    redis_db.set_generic_cache(store._app_cache_path('app-1'), strict.rows[APP_DOC], ttl=600)
    second = store.rotate_app_webhook_signing_db('app-1', 'whsec_second', firestore_client=strict)
    assert second.current == 'whsec_second' and second.previous == 'whsec_first'
    assert len(strict.transactions) == 2
    assert [path for path, _ in strict.transactions[1].sets] == [APP_DOC]
    assert redis_db.get_generic_cache(store._app_cache_path('app-1')) is None
    assert store._decode(strict.rows[APP_DOC], 'app-1') == second
