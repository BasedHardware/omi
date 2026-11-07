"""Drainer cause 2 (privacy-lane ruling faf00e): a privacy-blocked record_pending row
leaves the drain page through an available_at-only, fence-exempt update."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import fakeredis

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


@pytest.fixture
def fast_records(monkeypatch):
    from utils.batch_pipeline import record_attention

    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'serve')
    monkeypatch.setenv('PIPELINE_RECORD_FAST_ENABLED', 'true')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    redis = fakeredis.FakeRedis(server=fakeredis.FakeServer())
    monkeypatch.setattr(record_attention.attention, 'serving', lambda _: True)
    monkeypatch.setattr(record_attention.attention, 'client', lambda: redis)
    return record_attention, redis


def test_fast_records_reserve_original_age_under_continuous_fresh_traffic(fast_records):
    records, redis = fast_records
    from config.record_audio import record_identity

    records.register('aged', 'old', 1)
    old = record_identity('aged', 'old')[1]
    for tick in range(20):
        for n in range(8):
            records.register(f'fresh-{tick}-{n}', f'c-{tick}-{n}', 1000 + tick * 8 + n)
        selected = records.select([], 4, redis=redis, now=2000)
        assert selected[0] == old and len(selected) == 4
    # A retry cannot launder original enqueue age.
    records.register('aged', 'old', 9999)
    assert redis.zscore(records.base() + 'age', old) == 1


def test_small_fast_passes_alternate_oldest_service_and_cap_owner(fast_records):
    records, redis = fast_records
    from config.record_audio import record_identity

    records.register('old', 'c', 1)
    records.register('new', 'c', 100)
    records.register('new', 'second', 101)
    assert records.select([], 1, redis=redis, now=200)[0] == record_identity('new', 'second')[1]
    assert records.select([], 1, redis=redis, now=200)[0] == record_identity('old', 'c')[1]
    assert len(records.select([], 4, redis=redis, now=200)) == 2


def test_oldest_reserve_counts_distinct_eligible_owners(fast_records):
    records, redis = fast_records
    from config.record_audio import record_identity

    records.register('aged-one', 'first', 1)
    records.register('aged-one', 'second', 2)
    records.register('aged-two', 'first', 3)
    for n in range(10):
        records.register(f'fresh-{n}', 'c', 1000 + n)
    selected = records.select([], 8, redis=redis, now=2000)
    assert selected[:2] == [record_identity('aged-one', 'first')[1], record_identity('aged-two', 'first')[1]]


def test_seal_wakes_parked_record_but_never_steals_active_lease(fast_records):
    records, redis = fast_records
    from config.record_audio import record_identity

    store = MemoryStore()
    sealed = {
        'status': 'completed',
        'record_lane_owner': 'batch_live_v1',
        'finished_at': 90,
        'record_audio_closed': True,
        'record_upload_revision': 2,
    }
    segment = record_identity('u', 'c')[1]
    store.rows['jobs', segment] = pending(
        owner_id='u', conversation_id='c', enqueued_at=1, available_at=1000, pipeline_record_deferred=True
    )
    assert records.sealed('u', 'c', sealed, store=store, now=100)
    assert store.rows['jobs', segment]['available_at'] == 100
    store.rows['jobs', segment].update(available_at=500, pipeline_record_lease_until=500)
    assert records.sealed('u', 'c', sealed, store=store, now=101)
    assert store.rows['jobs', segment]['available_at'] == 500
    assert records.select([], 4, redis=redis, now=102) == []
    assert not records.sealed('u', 'c', {**sealed, 'record_audio_partial': True}, store=store, now=102)


def test_record_fast_off_is_exact_legacy_selection(fast_records, monkeypatch):
    records, redis = fast_records
    monkeypatch.setenv('PIPELINE_RECORD_FAST_ENABLED', 'false')
    assert records.select(['oldest', 'next'], 2, redis=redis) == ['oldest', 'next']


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
    # Pass 1: the whole oldest page is blocked; both rows leave it, so another pass is warranted.
    assert asyncio.run(live.drain_recordings(store)) is True
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


@pytest.mark.asyncio
async def test_seal_wake_burst_is_coalesced_and_stop_interrupts_pop(fast_records, monkeypatch):
    import fakeredis.aioredis

    records, _ = fast_records
    redis = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer())

    async def client():
        return redis

    monkeypatch.setattr(records, 'get_async_redis_client', client)
    stop = asyncio.Event()
    try:
        await redis.lpush(records.base() + 'wakes', *[str(n) for n in range(100)])
        await asyncio.wait_for(records.wait_for_wake(stop), timeout=3)
        assert await redis.llen(records.base() + 'wakes') == 0
        waiting = asyncio.create_task(records.wait_for_wake(stop))
        await asyncio.sleep(0)
        stop.set()
        await asyncio.wait_for(waiting, timeout=3)
    finally:
        await redis.aclose()


def test_admission_owner_cap_survives_missing_redis_hints(drain, fast_records, monkeypatch):
    live, admitted = drain
    monkeypatch.setenv('RECORD_DRAIN_BATCH', '3')
    store = fenced_store(('a', False), ('b', False), ('c', False))
    for row in store.rows.values():
        row['owner_id'] = 'same-owner'
    assert asyncio.run(live.drain_recordings(store)) is True  # The original due page was full.
    assert len(admitted) == 1
