"""Drainer cause 2 (privacy-lane ruling faf00e): a privacy-blocked record_pending row
leaves the drain page through an available_at-only, fence-exempt update."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


class Snap:
    def __init__(self, doc):
        self._doc, self.exists = doc, doc is not None

    def to_dict(self):
        return self._doc


class Client:
    def __init__(self, doc):
        self.doc = doc
        self.tx = SimpleNamespace(update=Mock(), set=Mock(), create=Mock())

    def collection(self, name):
        assert name == 'batch_pipeline_dev_jobs'
        return SimpleNamespace(document=lambda key: SimpleNamespace(get=lambda transaction=None: Snap(self.doc)))

    def transaction(self, **options):
        return self.tx


@pytest.fixture
def recovery(monkeypatch):
    from google.cloud import firestore
    from database import batch_pipeline_recovery as recovery

    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(recovery, 'mirror_refresh', lambda *_: None)
    monkeypatch.setattr(recovery, 'assert_batch_write_allowed', Mock(side_effect=BatchPrivacyBlocked('fenced')))
    return recovery


def pending(**fields):
    return {'state': 'record_pending', 'available_at': 5.0, 'owner_id': 'u', 'conversation_id': 'c', **fields}


def test_blocked_row_gets_an_update_of_available_at_only(recovery):
    client = Client(pending())
    assert recovery.defer_privacy_blocked_record(client, 'batch_pipeline_dev', 'j', 910.0, 10.0) is True
    client.tx.update.assert_called_once()
    assert client.tx.update.call_args.args[1] == {'available_at': 910.0}
    # An UPDATE (exists precondition), never a set/create that could recreate a purged job.
    client.tx.set.assert_not_called()
    client.tx.create.assert_not_called()


def test_purged_job_is_not_resurrected(recovery):
    client = Client(None)
    assert recovery.defer_privacy_blocked_record(client, 'batch_pipeline_dev', 'j', 910.0, 10.0) is False
    client.tx.update.assert_not_called()
    client.tx.set.assert_not_called()
    client.tx.create.assert_not_called()


@pytest.mark.parametrize('doc', [pending(state='ready'), pending(state='leased'), pending(available_at=50.0)])
def test_only_a_due_record_pending_row_moves(recovery, doc):
    client = Client(doc)
    assert recovery.defer_privacy_blocked_record(client, 'batch_pipeline_dev', 'j', 910.0, 10.0) is False
    client.tx.update.assert_not_called()


def test_an_allowed_row_is_left_to_the_normal_claim(recovery, monkeypatch):
    monkeypatch.setattr(recovery, 'assert_batch_write_allowed', Mock(return_value=3))
    client = Client(pending())
    assert recovery.defer_privacy_blocked_record(client, 'batch_pipeline_dev', 'j', 910.0, 10.0) is False
    client.tx.update.assert_not_called()


def test_any_other_field_in_the_defer_write_is_refused(recovery, monkeypatch):
    assert recovery.PRIVACY_DEFER_FIELDS == frozenset({'available_at'})
    original = recovery.privacy_defer_update

    def widened(until):
        update = original(until)
        update['state'] = 'ready'
        return recovery._check_privacy_defer_fields(update)

    monkeypatch.setattr(recovery, 'privacy_defer_update', widened)
    with pytest.raises(ValueError, match='available_at only'):
        recovery.defer_privacy_blocked_record(Client(pending()), 'batch_pipeline_dev', 'j', 910.0, 10.0)


def fenced_store(*rows):
    store = MemoryStore()
    for segment, fenced in rows:
        store.rows['jobs', segment] = {
            'owner_id': f'synthetic-{segment}',
            'segment_id': segment,
            'state': 'record_pending',
            'available_at': 0,
            'privacy_fenced': fenced,
        }
    original_run = store.run

    def run(body):
        # The claim is a full job write; the store flush fence refuses it for a fenced owner.
        def guarded(tx):
            put = tx.put

            def fenced_put(table, key, value):
                if value.get('privacy_fenced'):
                    raise BatchPrivacyBlocked('recording_privacy_changed')
                put(table, key, value)

            tx.put = fenced_put
            return body(tx)

        return original_run(guarded)

    store.run = run
    return store


@pytest.fixture
def drain(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    monkeypatch.setattr(live.random, 'shuffle', lambda segments: segments.sort())
    monkeypatch.setattr(live.time, 'time', lambda: 1000)
    admitted = []

    async def admission(store, row):
        admitted.append(row['segment_id'])
        store.rows['jobs', row['segment_id']]['state'] = 'ready'

    monkeypatch.setattr(live, 'admit_recording', admission)
    return live, admitted


def test_a_fully_blocked_oldest_page_no_longer_starves_the_rows_behind_it(drain, monkeypatch):
    live, admitted = drain
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    store = fenced_store(('a-fenced', True), ('b-fenced', True), ('c-ok', False))
    # Pass 1: the whole oldest page is blocked; both rows leave it. Nothing was admitted, so
    # the pass keeps the idle wait (no immediate rescan, record drain pacing) ...
    assert asyncio.run(live.drain_recordings(store)) is False
    assert [store.rows['jobs', s]['available_at'] for s in ('a-fenced', 'b-fenced')] == [1900.0, 1900.0]
    assert [store.rows['jobs', s]['state'] for s in ('a-fenced', 'b-fenced')] == ['record_pending'] * 2
    # Pass 2: the row that was starved behind them is admitted.
    asyncio.run(live.drain_recordings(store))
    assert admitted == ['c-ok']


def test_kill_switch_zero_restores_the_stay_due_behavior(drain, monkeypatch):
    live, admitted = drain
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '2')
    monkeypatch.setenv('RECORD_DRAIN_PRIVACY_DEFER_SECONDS', '0')
    store = fenced_store(('a-fenced', True), ('b-fenced', True), ('c-ok', False))
    assert asyncio.run(live.drain_recordings(store)) is False
    assert [store.rows['jobs', s]['available_at'] for s in ('a-fenced', 'b-fenced')] == [0, 0]
    asyncio.run(live.drain_recordings(store))
    assert admitted == []  # starved, as before the fix


def test_a_failed_defer_keeps_the_row_due_and_the_idle_wait(drain, monkeypatch):
    live, admitted = drain
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '1')
    store = fenced_store(('a-fenced', True))
    store.defer_privacy_blocked_record = Mock(side_effect=RuntimeError('contention'))
    assert asyncio.run(live.drain_recordings(store)) is False
    assert store.rows['jobs', 'a-fenced']['available_at'] == 0


def test_kill_switch_parsing():
    from config.record_drain import record_drain_privacy_defer_seconds

    import os

    for raw, expected in (('900', 900), ('0', 0), ('-5', 0), ('bad', 900), ('999999', 86400)):
        os.environ['RECORD_DRAIN_PRIVACY_DEFER_SECONDS'] = raw
        try:
            assert record_drain_privacy_defer_seconds() == expected
        finally:
            del os.environ['RECORD_DRAIN_PRIVACY_DEFER_SECONDS']
