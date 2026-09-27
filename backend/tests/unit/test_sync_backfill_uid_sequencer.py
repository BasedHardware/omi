"""Durable UID ownership and bounded recovery for backfill Cloud Tasks."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from google.cloud import firestore

from database import sync_backfill_sequencer as registry
from database.sync_jobs import is_sync_job_stale
from utils.sync import uid_sequencer


class _Snapshot:
    def __init__(self, path, data):
        self.id = path[-1]
        self.exists = data is not None
        self._data = copy.deepcopy(data)

    def to_dict(self):
        return copy.deepcopy(self._data)


class _Ref:
    def __init__(self, client, path):
        self.client = client
        self.path = path
        self.id = path[-1]

    def get(self, transaction=None):
        return _Snapshot(self.path, self.client.docs.get(self.path))

    def collection(self, name):
        return _Collection(self.client, self.path + (name,))

    def update(self, data):
        self.client.write(self.path, data, merge=True)


class _Query:
    def __init__(self, client, path, field=None, maximum=None, order=None, limit=None):
        self.client, self.path = client, path
        self.field, self.maximum, self.order, self.maximum_results = field, maximum, order, limit

    def where(self, field, op, maximum):
        assert op == '<='
        return _Query(self.client, self.path, field, maximum, self.order, self.maximum_results)

    def order_by(self, field):
        return _Query(self.client, self.path, self.field, self.maximum, field, self.maximum_results)

    def limit(self, count):
        return _Query(self.client, self.path, self.field, self.maximum, self.order, count)

    def stream(self):
        rows = [(path, value) for path, value in self.client.docs.items() if path[:-1] == self.path]
        if self.field:
            rows = [(path, value) for path, value in rows if value.get(self.field) <= self.maximum]
        rows.sort(key=lambda row: (row[1].get(self.order), row[0]) if self.order else row[0])
        if self.maximum_results is not None:
            rows = rows[: self.maximum_results]
        return [_Snapshot(path, value) for path, value in rows]


class _Collection(_Query):
    def document(self, name):
        return _Ref(self.client, self.path + (name,))


class _Transaction:
    def __init__(self, client):
        self.client = client

    def set(self, ref, data, merge=False):
        self.client.write(ref.path, data, merge=merge)

    def update(self, ref, data):
        self.client.write(ref.path, data, merge=True)

    def delete(self, ref):
        self.client.docs.pop(ref.path, None)


class _Firestore:
    def __init__(self):
        self.docs = {}
        self.lock = threading.RLock()

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        return _Transaction(self)

    def write(self, path, data, *, merge):
        value = copy.deepcopy(self.docs.get(path, {})) if merge else {}
        for key, field_value in data.items():
            if field_value is firestore.DELETE_FIELD:
                value.pop(key, None)
            else:
                value[key] = copy.deepcopy(field_value)
        self.docs[path] = value


@pytest.fixture
def db(monkeypatch):
    client = _Firestore()

    def transactional(fn):
        def run(transaction):
            with client.lock:
                return fn(transaction)

        return run

    monkeypatch.setattr(registry.firestore, 'transactional', transactional)
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: client)
    return client


NOW = datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)


def _register(uid, job_id, seconds, *, db, now=NOW):
    return registry.register_job(
        uid, job_id, {'uid': uid, 'job_id': job_id}, now.timestamp() + seconds, firestore_client=db, now=now
    )


def test_waiting_jobs_run_oldest_first_and_terminal_failure_releases(db):
    _register('a', 'new', 300, db=db)
    assert registry.is_registered('a', 'new', firestore_client=db)
    _register('a', 'old', 100, db=db)
    _register('a', 'middle', 200, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert first['job_id'] == 'old'
    assert registry.claim_next('a', firestore_client=db, now=NOW) is None
    assert registry.begin_job('a', 'old', first['epoch'], firestore_client=db, now=NOW)
    assert registry.finish_job('a', 'old', first['epoch'], 'failed', firestore_client=db, now=NOW)
    assert not registry.finish_job('a', 'old', first['epoch'], 'failed', firestore_client=db, now=NOW)
    second = registry.claim_next('a', firestore_client=db, now=NOW)
    assert second['job_id'] == 'middle'
    assert registry.is_registered('a', 'middle', firestore_client=db)


def test_contention_only_one_active_and_other_uid_can_dispatch(db):
    for index in range(30):
        _register('heavy', f'h{index}', index, db=db)
    _register('light', 'l0', 0, db=db)
    with ThreadPoolExecutor(max_workers=12) as pool:
        claims = list(pool.map(lambda _: registry.claim_next('heavy', firestore_client=db, now=NOW), range(12)))
    assert len([claim for claim in claims if claim]) == 1
    assert registry.get_owner('heavy', firestore_client=db)['pending_count'] == 29
    assert registry.claim_next('light', firestore_client=db, now=NOW)['job_id'] == 'l0'


def test_expired_lease_redrive_is_fenced_and_duplicate_delivery_is_inert(db):
    _register('a', 'job', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    assert registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW)
    assert registry.renew_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=4))
    assert (
        registry.redrive_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=31)) is None
    )
    second = registry.redrive_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))
    assert second['epoch'] == first['epoch'] + 1
    assert not registry.begin_job('a', 'job', first['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))
    assert not registry.finish_job(
        'a', 'job', first['epoch'], 'failed', firestore_client=db, now=NOW + timedelta(minutes=35)
    )
    assert registry.begin_job('a', 'job', second['epoch'], firestore_client=db, now=NOW + timedelta(minutes=35))


def test_sweeper_replaces_lost_dispatch_then_releases_terminal_job(db, monkeypatch):
    _register('a', 'lost', 0, db=db)
    _register('a', 'next', 1, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda claim: dispatched.append(claim))
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _job_id: False)
    monkeypatch.setattr(uid_sequencer, 'get_raw_sync_job', lambda _job_id: {'status': 'queued'})
    expired = NOW + timedelta(minutes=6)
    owner = registry.get_owner('a', firestore_client=db)
    assert uid_sequencer.reconcile_uid('a', owner, now=expired) == 'lease_expired'
    assert dispatched[0]['job_id'] == 'lost'
    assert dispatched[0]['epoch'] == first['epoch'] + 1
    assert registry.finish_job('a', 'lost', dispatched[0]['epoch'], 'failed', firestore_client=db, now=expired)
    assert uid_sequencer.kick('a')
    assert dispatched[-1]['job_id'] == 'next'


def test_flag_switch_does_not_change_persisted_owner_or_legacy_task(db, monkeypatch):
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    assert registry.enabled()
    _register('a', 'sequenced', 0, db=db)
    first = registry.claim_next('a', firestore_client=db, now=NOW)
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'off')
    assert not registry.enabled()
    assert registry.begin_job('a', 'sequenced', first['epoch'], firestore_client=db, now=NOW)
    assert registry.finish_job('a', 'sequenced', first['epoch'], 'completed', firestore_client=db, now=NOW)
    monkeypatch.setenv('SYNC_BACKFILL_UID_SEQUENCER', 'on')
    assert registry.claim_next('legacy', firestore_client=db, now=NOW) is None


def test_polling_cannot_stale_finalize_queued_or_running_sequenced_job():
    old = NOW.timestamp() - 3600
    for status in ('queued', 'processing'):
        assert not is_sync_job_stale(
            {'status': status, 'dispatch_mode': 'sequenced', 'created_at': old, 'updated_at': old},
            now=NOW.timestamp(),
        )
