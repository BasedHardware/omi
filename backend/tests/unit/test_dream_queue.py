"""Behavioral coalescing, budget, acknowledgement and admission regression contracts."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from config.dream_agent import Caps
from database import dream_store
from tests.support.dream_firestore import DreamFirestore
from tests.unit.fixtures.strict_firestore_transaction import ReadAfterWriteError, InvalidFirestoreValueError
from utils import dream_agent
from utils.llm.shaped_agent import Turn

UID = 'synthetic-queue-owner'
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def queue(monkeypatch):
    monkeypatch.setattr(dream_agent.dream_capacity, 'claim', AsyncMock(return_value=('slot', 'token')))
    monkeypatch.setattr(dream_agent.dream_capacity, 'release', AsyncMock())
    monkeypatch.setattr(dream_agent.dream_capacity, 'available_model', AsyncMock(return_value='synthetic-model'))
    db = DreamFirestore()
    db.rows[('users', UID)] = {}
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0')
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'false')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    return db


def inspection(uid, lease, caps):
    # These are storage settlement tests: the session supplies exactly the
    # dirty versions whose records were actually read, never a fresh queue scan.
    return {}, [snapshot.to_dict() for snapshot in dream_store.dirty_refs(uid, limit=32, newest=False)]


def seed(queue, count):
    queue.rows[('dream_users', UID)] = {'score': count}
    for i in range(count):
        queue.rows[('dream_users', UID, 'dirty', dream_store.dirty_id('conversations', str(i)))] = {
            'collection': 'conversations',
            'id': str(i),
            'version': str(i),
            'last_changed_at': NOW - timedelta(seconds=count - i),
            'change_count': 1,
        }


def test_repeated_writes_coalesce_with_one_bounded_priority_read(queue):
    for _ in range(50):
        dream_store.mark_dirty(UID, [('conversations', 'same'), ('conversations', 'same')])
    rows = dream_store.dirty_refs(UID)
    assert len(rows) == 1 and rows[0].to_dict()['change_count'] == 50
    assert queue.rows[('dream_users', UID)]['score'] == 50
    assert queue.reads == [('users', UID), ('dream_users', UID)] * 50
    assert not queue.transactions
    dream_store.mark_dirty(UID, [('conversations', 'other')])
    assert dream_store.dirty_refs(UID)[0].to_dict()['id'] == 'other'


def test_paid_weight_and_ref_identity(queue):
    from config.plan_catalog import PAID_PLAN_IDS

    queue.rows[('users', UID)] = {'plan': next(iter(PAID_PLAN_IDS))}
    dream_store.mark_dirty(UID, [('people', 'same'), ('conversations', 'same')])
    assert dream_store.dirty_count(UID) == 2
    assert queue.rows[('dream_users', UID)]['score'] == 2


def test_failed_pass_keeps_every_version_queued(queue):
    seed(queue, 2)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    _, consumed = inspection(UID, lease, Caps())
    dream_store.finish(UID, lease, {'tokens': 3}, success=False, consumed=consumed)
    assert dream_store.dirty_count(UID) == 2
    assert queue.rows[('dream_users', UID)]['watermark'] == dream_store.EPOCH


def test_concurrent_refresh_and_new_arrival_survive_finish(queue):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    _, consumed = inspection(UID, lease, Caps())
    dream_store.mark_dirty(UID, [('conversations', '0'), ('conversations', 'new')])
    dream_store.finish(UID, lease, {'tokens': 1}, success=True, consumed=consumed)
    assert dream_store.dirty_count(UID) == 2
    assert queue.rows[('dream_users', UID)]['score'] == 2
    assert dream_store.dirty_refs(UID)[0].to_dict()['version'] != consumed[0]['version']


def gateway_response(status):
    return httpx.Response(status, request=httpx.Request('POST', 'https://synthetic.invalid/model'))


def test_backlog_cap_drops_oldest_and_reports_drops_once(queue):
    dream_store.mark_dirty(UID, [('conversations', 'old')])
    dream_store.mark_dirty(UID, [('conversations', str(i)) for i in range(505)])
    dirty = dream_store.dirty_refs(UID)
    assert len(dirty) == 500
    assert {s.to_dict()['id'] for s in dirty} == {str(i) for i in range(5, 505)}
    assert queue.rows[('dream_users', UID)]['dirty_dropped'] == 6
    lease = dream_store.acquire(UID, Caps())
    report = {'tokens': 0}
    dream_store.finish(UID, lease, report, success=False, refund=True)
    assert report['dirty_dropped'] == 6
    lease = dream_store.acquire(UID, Caps())
    report = {'tokens': 0}
    dream_store.finish(UID, lease, report, success=False, refund=True)
    assert report['dirty_dropped'] == 0


def test_trim_preserves_version_refreshed_after_oldest_query(queue, monkeypatch):
    seed(queue, 501)
    original = dream_store.dirty_refs
    refreshed = False

    def refresh(uid, **kwargs):
        nonlocal refreshed
        snapshots = original(uid, **kwargs)
        if kwargs.get('newest') is False and not refreshed:
            row = queue.rows[snapshots[0].reference.path]
            row.update(version='fresh-version', last_changed_at=NOW)
            refreshed = True
        return snapshots

    monkeypatch.setattr(dream_store, 'dirty_refs', refresh)
    dream_store.trim_dirty(UID)
    rows = original(UID)
    assert len(rows) == 500 and rows[0].to_dict()['id'] == '0'
    assert all(s.to_dict()['id'] != '1' for s in rows)


def test_refund_uses_lease_day_after_midnight(queue):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    queue.rows[('dream_users', UID)].update(day='2026-10-10', passes=2)
    dream_store.finish(UID, lease, {'tokens': 0}, success=False, refund=True)
    assert queue.rows[('dream_users', UID)]['passes'] == 2
    assert queue.rows[('dream_users', UID, 'spend', lease['day'])]['reserved_usd'] == 0


def test_dream_fixture_keeps_firestore_constraints(queue):
    doc = dream_store.state_ref(queue, UID)
    tx = queue.transaction()
    tx.set(doc, {'value': 1})
    with pytest.raises(ReadAfterWriteError):
        list(doc.collection('dirty').order_by('last_changed_at').limit(1).stream(transaction=tx))
    with pytest.raises(InvalidFirestoreValueError):
        tx.set(doc, {'nested': [[1]]})


def test_final_chunk_preserves_scheduling_if_a_pass_finishes_between_chunks(queue, monkeypatch):
    seed(queue, 1)
    real_trim = dream_store.trim_dirty
    calls = 0

    def finish_between_chunks(uid, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            # Bounded unavailable-only passes can exhaust the first chunk
            # before the writer queues its final chunk and bumps the score.
            while dream_store.dirty_count(UID):
                lease = dream_store.acquire(UID, Caps())
                unavailable = [{**s.to_dict(), 'transient': False} for s in dream_store.dirty_refs(UID, limit=32)]
                dream_store.finish(UID, lease, {}, success=False, refund=True, unavailable=unavailable)
            assert queue.rows[('dream_users', UID)]['score'] == 0
        real_trim(uid, **kwargs)

    monkeypatch.setattr(dream_store, 'trim_dirty', finish_between_chunks)
    dream_store.mark_dirty(UID, [('conversations', str(i)) for i in range(401)])
    assert queue.rows[('dream_users', UID)]['score'] >= 1
    assert dream_store.dirty_count(UID) > 0
    assert dream_store.acquire(UID, Caps()) is not None


def test_trim_does_not_drop_spare_refs_when_a_pass_drains_after_count(queue, monkeypatch):
    seed(queue, 501)
    original = dream_store.dirty_refs

    def drain(uid, **kwargs):
        snapshots = original(uid, **kwargs)
        if kwargs.get('newest') is False:
            queue.rows.pop(('dream_users', UID, 'dirty', dream_store.dirty_id('conversations', '500')))
        return snapshots

    monkeypatch.setattr(dream_store, 'dirty_refs', drain)
    dream_store.trim_dirty(UID)
    assert dream_store.dirty_count(UID) == 500
    assert original(UID, newest=False)[0].to_dict()['id'] == '0'
    assert queue.rows[('dream_users', UID)].get('dirty_dropped', 0) == 0


def test_three_failed_passes_only_poison_the_inspected_version(queue):
    seed(queue, 2)
    for index in range(3):
        lease = dream_store.acquire(UID, Caps(passes=10))
        item = next(row.to_dict() for row in dream_store.dirty_refs(UID) if row.to_dict()['id'] == '1')
        report = {'tokens': 10, 'usage_unknown': False}
        dream_store.finish(UID, lease, report, success=False, consumed=[item], count_failure=True)
        assert report['poisoned'] == int(index == 2)
    assert dream_store.dirty_count(UID) == 1
    assert dream_store.dirty_refs(UID)[0].to_dict()['id'] == '0'


def test_poison_counter_resets_on_refresh_and_fences_concurrent_refresh(queue):
    seed(queue, 1)
    caps = Caps(passes=10, daily_usd=100)
    for attempt in range(2):
        lease = dream_store.acquire(UID, caps)
        consumed = [s.to_dict() for s in dream_store.dirty_refs(UID)]
        dream_store.finish(UID, lease, {'tokens': 10}, success=False, consumed=consumed, count_failure=True)
    assert dream_store.dirty_refs(UID)[0].to_dict()['failed_passes'] == 2
    lease = dream_store.acquire(UID, caps)
    consumed = [s.to_dict() for s in dream_store.dirty_refs(UID)]
    dream_store.mark_dirty(UID, [('conversations', '0')])
    report = {'tokens': 10}
    dream_store.finish(UID, lease, report, success=False, consumed=consumed, count_failure=True)
    row = dream_store.dirty_refs(UID)[0].to_dict()
    assert report['poisoned'] == 0 and row['failed_passes'] == 0
    assert row['version'] != consumed[0]['version']
    # The refreshed product version receives three attempts of its own.
    for attempt in range(3):
        lease = dream_store.acquire(UID, caps)
        consumed = [s.to_dict() for s in dream_store.dirty_refs(UID)]
        dream_store.finish(UID, lease, report, success=False, consumed=consumed, count_failure=True)
    assert report['poisoned'] == 1 and report['records_queued_after'] == 0
    assert queue.rows[('dream_users', UID)]['score'] == 0
    assert dream_store.acquire(UID, caps) is None


@pytest.mark.parametrize('flags', [{'refund': True}, {'release': False}, {'count_failure': False}])
def test_refunded_unreleased_and_pre_reasoning_failures_do_not_poison(queue, flags):
    seed(queue, 1)
    row = dream_store.dirty_refs(UID)[0].reference.path
    queue.rows[row]['failed_passes'] = 2
    lease = dream_store.acquire(UID, Caps())
    consumed = [s.to_dict() for s in dream_store.dirty_refs(UID)]
    report = {'tokens': 0}
    dream_store.finish(UID, lease, report, success=False, consumed=consumed, **{'count_failure': True, **flags})
    assert report['poisoned'] == 0 and dream_store.dirty_count(UID) == 1
    assert queue.rows[row]['failed_passes'] == 2


def test_success_after_failure_settles_without_poisoning(queue):
    seed(queue, 1)
    queue.rows[dream_store.dirty_refs(UID)[0].reference.path]['failed_passes'] = 2
    lease = dream_store.acquire(UID, Caps())
    consumed = [s.to_dict() for s in dream_store.dirty_refs(UID)]
    report = {'tokens': 10}
    dream_store.finish(UID, lease, report, success=True, consumed=consumed)
    assert report['poisoned'] == 0 and dream_store.dirty_count(UID) == 0
    assert queue.rows[('dream_users', UID)].get('poisoned', 0) == 0


@pytest.mark.parametrize('transient', [False, True])
def test_unavailable_settlement_preserves_concurrent_refresh(queue, monkeypatch, transient):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    item = dream_store.dirty_refs(UID)[0].to_dict()
    dream_store.mark_dirty(UID, [('conversations', '0')])
    report = {}
    dream_store.finish(UID, lease, report, success=False, refund=True, unavailable=[{**item, 'transient': transient}])
    assert report['dirty_counts']['permanent_acknowledged'] == report['dirty_counts']['transient_expired'] == 0
    assert dream_store.dirty_refs(UID)[0].to_dict()['failed_passes'] == 0
    assert dream_store.dirty_count(UID) == 1


def test_ambiguous_lease_does_not_settle_unavailable_refs(queue):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    item = dream_store.dirty_refs(UID)[0].to_dict()
    report = {}
    dream_store.finish(UID, lease, report, success=False, release=False, unavailable=[{**item, 'transient': False}])
    assert dream_store.dirty_count(UID) == 1 and report['dirty_counts']['permanent_acknowledged'] == 0


def test_provider_failure_does_not_acknowledge_an_unread_dirty_version(queue):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps())
    report = {'tokens': 10, 'usage_unknown': True}
    dream_store.finish(UID, lease, report, success=False, consumed=[])
    assert dream_store.dirty_count(UID) == 1
    assert dream_store.dirty_refs(UID)[0].to_dict().get('failed_passes', 0) == 0


def test_settlement_rejects_more_than_inspection_limit(queue):
    seed(queue, 35)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    with pytest.raises(ValueError, match='dream_settlement_limit'):
        dream_store.finish(UID, lease, {}, success=True, consumed=[s.to_dict() for s in dream_store.dirty_refs(UID)])
    assert dream_store.dirty_count(UID) == 35
