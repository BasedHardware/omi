"""Behavioral coalescing, budget, acknowledgement and admission regression contracts."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from config.dream_agent import Caps
from database import dream_store
from models.dream_agent import Triage, Cluster
from tests.support.dream_firestore import DreamFirestore
from tests.unit.fixtures.strict_firestore_transaction import ReadAfterWriteError, InvalidFirestoreValueError
from utils import dream_agent, dream_reads, dream_transport
from utils.dream_prompt import fits_triage
from utils.llm.shaped_agent import Turn

UID = 'synthetic-queue-owner'
NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def queue(monkeypatch):
    db = DreamFirestore()
    db.rows[('users', UID)] = {}
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', UID)
    monkeypatch.setenv('DREAM_AGENT_TESTFLIGHT_ENABLED', 'false')
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(dream_store, 'vocabulary', lambda *a: [])
    monkeypatch.setattr(dream_store, 'demoted_types', lambda *a: set())
    monkeypatch.setattr(dream_agent.review_store, 'remaining_today', lambda *a: 3)
    monkeypatch.setattr(dream_reads.screen_activity, 'get_screen_activity', lambda *a, **k: [])
    monkeypatch.setattr(
        dream_reads, 'read_record', lambda uid, ref: {'structured': {'title': 'Synthetic record ' * 100}}
    )
    return db


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


def test_repeated_writes_coalesce_without_reading_state(queue):
    for _ in range(50):
        dream_store.mark_dirty(UID, [('conversations', 'same'), ('conversations', 'same')])
    rows = dream_store.dirty_refs(UID)
    assert len(rows) == 1 and rows[0].to_dict()['change_count'] == 50
    assert queue.rows[('dream_users', UID)]['score'] == 50
    assert queue.reads == [('users', UID)] * 50
    assert not queue.transactions
    dream_store.mark_dirty(UID, [('conversations', 'other')])
    assert dream_store.dirty_refs(UID)[0].to_dict()['id'] == 'other'


def test_paid_weight_and_ref_identity(queue):
    from config.plan_catalog import PAID_PLAN_IDS

    queue.rows[('users', UID)] = {'plan': next(iter(PAID_PLAN_IDS))}
    dream_store.mark_dirty(UID, [('people', 'same'), ('conversations', 'same')])
    assert dream_store.dirty_count(UID) == 2
    assert queue.rows[('dream_users', UID)]['score'] == 2


def test_budget_reads_newest_first_and_watermark_never_skips_unread(queue):
    seed(queue, 80)
    caps = Caps(tokens=12000)
    lease = dream_store.acquire(UID, caps, now=NOW)
    records, consumed = dream_reads.read_changes(UID, lease, caps)
    assert 0 < len(consumed) < 80
    assert list(records) == [f'conversations/{i}' for i in range(79, 79 - len(consumed), -1)]
    assert fits_triage(records, caps)
    assert not fits_triage(
        {**records, f'conversations/{79 - len(consumed)}': {'structured': {'title': 'Synthetic record ' * 100}}}, caps
    )
    dream_store.finish(UID, lease, {'tokens': 1}, success=True, consumed=consumed)
    assert dream_store.dirty_count(UID) == 80 - len(consumed)
    state = queue.rows[('dream_users', UID)]
    oldest = dream_store.dirty_refs(UID, newest=False)[0].to_dict()['last_changed_at']
    assert state['watermark'] < oldest
    assert state['score'] > 0
    next_lease = dream_store.acquire(UID, caps, now=NOW)
    next_records, _ = dream_reads.read_changes(UID, next_lease, caps)
    assert set(next_records).isdisjoint(records)
    assert list(next_records)[0] == f'conversations/{79 - len(consumed)}'


def test_failed_pass_keeps_every_version_queued(queue):
    seed(queue, 2)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    _, consumed = dream_reads.read_changes(UID, lease, Caps())
    dream_store.finish(UID, lease, {'tokens': 3}, success=False, consumed=consumed)
    assert dream_store.dirty_count(UID) == 2
    assert queue.rows[('dream_users', UID)]['watermark'] == dream_store.EPOCH


def test_concurrent_refresh_and_new_arrival_survive_finish(queue):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    _, consumed = dream_reads.read_changes(UID, lease, Caps())
    dream_store.mark_dirty(UID, [('conversations', '0'), ('conversations', 'new')])
    dream_store.finish(UID, lease, {'tokens': 1}, success=True, consumed=consumed)
    assert dream_store.dirty_count(UID) == 2
    assert queue.rows[('dream_users', UID)]['score'] == 2
    assert dream_store.dirty_refs(UID)[0].to_dict()['version'] != consumed[0]['version']


def test_arrivals_after_admission_are_not_read(queue):
    seed(queue, 1)
    lease = dream_store.acquire(UID, Caps(), now=NOW)
    dream_store.mark_dirty(UID, [('conversations', 'new')])
    records, consumed = dream_reads.read_changes(UID, lease, Caps())
    assert list(records) == ['conversations/0']
    assert len(consumed) == 1


def test_idle_pass_refunds_and_can_admit_again(queue, monkeypatch):
    seed(queue, 1)
    monkeypatch.setattr(dream_reads, 'read_record', lambda *a: None)
    turn = AsyncMock(side_effect=AssertionError('idle called model'))
    report = asyncio.run(dream_agent.run_pass(UID, turn=turn))
    assert report['status'] == 'not_admitted' and report['reason'] == 'idle'
    assert report['cost_usd_reserved'] == 0 and report['dirty_read'] == 1
    assert dream_store.dirty_count(UID) == 0
    state = queue.rows[('dream_users', UID)]
    assert state['passes'] == 0 and state['score'] == 0 and state['lease'] is None
    assert queue.rows[('dream_spend', state['day'])]['reserved_usd'] == 0
    turn.assert_not_called()
    dream_store.mark_dirty(UID, [('conversations', 'new')])
    assert dream_store.acquire(UID, Caps(passes=1)) is not None


def test_legacy_events_are_ignored_and_idle_does_not_count(queue):
    queue.rows[('dream_users', UID)] = {'sequence': 10, 'watermark': 4, 'score': 10}
    event = ('dream_users', UID, 'events', '5')
    queue.rows[event] = {'sequence': 5, 'refs': [{'collection': 'conversations', 'id': 'old'}]}
    report = asyncio.run(dream_agent.run_pass(UID, turn=AsyncMock(side_effect=AssertionError())))
    assert report['status'] == 'not_admitted'
    assert event in queue.rows
    assert queue.rows[('dream_users', UID)]['passes'] == 0


def gateway_response(status):
    return httpx.Response(status, request=httpx.Request('POST', 'https://synthetic.invalid/model'))


def test_first_gateway_rejection_refunds_admission_and_spend(queue, monkeypatch):
    seed(queue, 1)
    client = type('Client', (), {'post': AsyncMock(return_value=gateway_response(404))})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    report = asyncio.run(dream_agent.run_pass(UID, caps=Caps(passes=1)))
    assert report['status'] == 'failed' and report['tokens'] == 0
    assert report['cost_usd_reserved'] == 0
    state = queue.rows[('dream_users', UID)]
    assert state['passes'] == 0 and state['lease'] is None
    assert queue.rows[('dream_spend', state['day'])]['reserved_usd'] == 0
    assert dream_store.dirty_count(UID) == 1
    assert dream_store.acquire(UID, Caps(passes=1)) is not None


@pytest.mark.parametrize('failure', ['after_tokens', 'ambiguous'])
def test_billable_or_ambiguous_failure_retains_admission_and_spend(queue, failure):
    seed(queue, 1)

    async def turn(uid, lane, mount, messages):
        if failure == 'ambiguous':
            raise httpx.ReadError('synthetic connection loss')
        if lane == dream_transport.TRIAGE_LANE:
            return Turn(value=Triage(clusters=[Cluster(refs=['conversations/0'], problem='quality')]), tokens=17)
        gateway_response(404).raise_for_status()

    report = asyncio.run(dream_agent.run_pass(UID, turn=turn))
    assert report['status'] == 'failed'
    assert report['tokens'] == (17 if failure == 'after_tokens' else 0)
    state = queue.rows[('dream_users', UID)]
    assert state['passes'] == 1 and state['lease'] is None
    assert queue.rows[('dream_spend', state['day'])]['reserved_usd'] == pytest.approx(0.24)
    assert dream_store.dirty_count(UID) == 1


def test_invalid_model_plan_still_accounts_for_tokens(queue, monkeypatch):
    seed(queue, 1)
    response = gateway_response(200)
    response._content = (
        b'{"usage":{"prompt_tokens":10,"completion_tokens":7},"choices":[{"message":{"content":"invalid json"}}]}'
    )
    client = type('Client', (), {'post': AsyncMock(return_value=response)})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', lambda: 'https://synthetic.invalid')
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_semaphore', lambda: asyncio.Semaphore(1))
    report = asyncio.run(dream_agent.run_pass(UID))
    assert report['status'] == 'failed' and report['tokens'] == 17
    assert queue.rows[('dream_users', UID)]['passes'] == 1


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
    assert queue.rows[('dream_spend', lease['day'])]['reserved_usd'] == 0


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
    lease = dream_store.acquire(UID, Caps())
    real_trim = dream_store.trim_dirty
    calls = 0

    def finish_between_chunks(uid, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            consumed = [s.to_dict() for s in dream_store.dirty_refs(UID, limit=400)]
            dream_store.finish(UID, lease, {'tokens': 1}, success=True, consumed=consumed)
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


def test_local_gateway_config_failure_refunds_before_dispatch(queue, monkeypatch):
    seed(queue, 1)
    client = type('Client', (), {'post': AsyncMock(side_effect=AssertionError('request dispatched'))})()
    monkeypatch.setattr(dream_transport, 'get_llm_gateway_client', lambda: client)
    monkeypatch.setattr(dream_transport, 'llm_gateway_headers', lambda **k: {})

    def missing_url():
        raise RuntimeError('synthetic missing configuration')

    monkeypatch.setattr(dream_transport, 'get_llm_gateway_base_url', missing_url)
    report = asyncio.run(dream_agent.run_pass(UID))
    state = queue.rows[('dream_users', UID)]
    assert report['status'] == 'failed' and report['tokens'] == 0
    assert state['passes'] == 0 and state['lease'] is None
    assert queue.rows[('dream_spend', state['day'])]['reserved_usd'] == 0
    client.post.assert_not_called()


def test_pre_model_timeout_refunds_but_retains_worker_safety_lease(queue, monkeypatch):
    seed(queue, 1)

    def timed_out(*args):
        raise TimeoutError('synthetic storage timeout')

    monkeypatch.setattr(dream_reads, 'read_changes', timed_out)
    turn = AsyncMock(side_effect=AssertionError('model invoked'))
    report = asyncio.run(dream_agent.run_pass(UID, turn=turn))
    state = queue.rows[('dream_users', UID)]
    assert report['status'] == 'failed' and report['tokens'] == 0
    assert report['cost_usd_reserved'] == 0
    assert state['passes'] == 0 and state['lease']['run_id'] == report['run_id']
    assert queue.rows[('dream_spend', state['day'])]['reserved_usd'] == 0
    assert dream_store.acquire(UID, Caps()) is None
    assert dream_store.dirty_count(UID) == 1
    turn.assert_not_called()
