"""C3: ``POST /v2/enrichment/run`` over the outbox consumer (contracts (a), (d)).

Expected retries answer 409 ``retry``, never 5xx/429/503 (the 10-18 and 10-19 queue stalls). Consumed
deliveries answer 200. Rows bound to the legacy ``/v2/sync-jobs/run`` handler and to this one share the
same payload and row, so both drain.
"""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database.outbox_firestore import ENRICHMENT_OUTBOX
from routers import enrichment as route
from tests.unit.test_sync_reprocess_coalesce import state, sweep_query  # noqa: F401
from utils.enrichment import callback  # noqa: F401 (heavy import at collection time, not in a test call)
from utils.enrichment import consumer as consumer_module
from utils.enrichment import custody
from utils.enrichment import outbox as reprocess
from utils.workers.consumer import run_push

KEY = reprocess.key('u', 'c')
SUMMARY = SimpleNamespace(structured={'overview': 'Synthetic committed summary'})


@pytest.fixture
def rows(state, monkeypatch):  # noqa: F811
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: False)
    from database import conversations as conversations_db

    monkeypatch.setattr(conversations_db, 'get_conversation_raw_snapshot', lambda *_args, **_kwargs: {})
    reprocess.mark('u', 'c', 'en', now=0)
    return state


def _deliver(rows, process, *, now=10_000.0):
    state_rows, _tasks = rows
    token = state_rows[KEY]['task_token']
    consumer = consumer_module.EnrichmentConsumer(ENRICHMENT_OUTBOX, process=process)
    return run_push(consumer, ENRICHMENT_OUTBOX, KEY, token, now=now)


@pytest.fixture
def client(rows, monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.verify_enrichment_task] = lambda: 0
    return TestClient(app)


def test_processed_delivery_retires_the_row(rows):
    result = _deliver(rows, Mock(return_value=None))
    assert (result.outcome, result.reason) == ('done', 'processed')
    assert KEY not in rows[0]


def test_first_summary_keeps_a_dormant_receipt(rows, monkeypatch):
    result = _deliver(rows, lambda *_: SUMMARY)
    assert result.outcome == 'done'
    receipt = rows[0][KEY]
    assert receipt['dormant'] and receipt['summary_seen'] and receipt['uid'] is None


def test_callback_pending_is_a_409_retry_that_keeps_the_wake(rows, client, monkeypatch):
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: _pending)
    token = rows[0][KEY]['task_token']
    response = client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 409
    assert response.json() == {'status': 'retry', 'reason': 'callback_pending'}
    assert rows[0][KEY]['lease_until'] == 0 and rows[0][KEY]['task_token'] == token  # the queue retry reclaims


def _pending(*_):
    raise reprocess.FirstSummaryCallbackPending('synthetic')


def test_every_retry_logs_its_cause_and_timing_without_ids(rows, client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(
        consumer_module.EnrichmentConsumer,
        '_callback',
        lambda self: Mock(side_effect=reprocess.FirstSummaryCallbackPending('Redirect target changed')),
    )
    token = rows[0][KEY]['task_token']
    response = client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 409
    lines = [r.getMessage() for r in caplog.records]
    assert 'event=enrichment_consumer outcome=retry reason=callback_pending cause=redirect_target_changed' in lines
    delivery = [line for line in lines if line.startswith('event=enrichment_delivery ')]
    assert len(delivery) == 1
    assert delivery[0].startswith('event=enrichment_delivery outcome=retry reason=callback_pending wait_s=')
    assert ' run_s=' in delivery[0] and KEY not in delivery[0] and token not in delivery[0]


def test_only_slow_deliveries_log_their_end(rows, client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(return_value=None))
    token = rows[0][KEY]['task_token']
    assert (
        client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token}).status_code
        == 200
    )
    assert not [r for r in caplog.records if r.getMessage().startswith('event=enrichment_delivery ')]

    reprocess.mark('u', 'c', 'en', now=0)
    monkeypatch.setattr(route, 'SLOW_DELIVERY_SECONDS', 0.0)
    token = rows[0][KEY]['task_token']
    assert (
        client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token}).status_code
        == 200
    )
    ends = [r.getMessage() for r in caplog.records if r.getMessage().startswith('event=enrichment_delivery ')]
    assert len(ends) == 1 and ends[0].startswith('event=enrichment_delivery outcome=done reason=processed ')


def test_a_slow_unexpected_error_still_logs_its_end(rows, client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(route, 'SLOW_DELIVERY_SECONDS', 0.0)
    monkeypatch.setattr(
        consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(side_effect=RuntimeError('synthetic'))
    )
    token = rows[0][KEY]['task_token']
    with pytest.raises(RuntimeError):
        client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    ends = [r.getMessage() for r in caplog.records if r.getMessage().startswith('event=enrichment_delivery ')]
    assert len(ends) == 1 and ends[0].startswith('event=enrichment_delivery outcome=error reason=unexpected ')


def test_lifecycle_fence_settles_as_superseded(rows):
    from utils.enrichment.callback import SyncConversationPersistenceFenced

    result = _deliver(rows, Mock(side_effect=SyncConversationPersistenceFenced('synthetic')))
    assert (result.outcome, result.reason) == ('discarded', 'superseded')
    assert KEY not in rows[0]


def test_action_item_revision_race_retries_and_keeps_the_row(rows, monkeypatch):
    # synceff 2026-11-05: a sync write moved the revision during the run, so the action-item refresh refused
    # stale extraction. That race is a retry that keeps the row and its wake, not error/unexpected.
    from database.action_item_refresh import RefreshRevisionChanged

    monkeypatch.delenv('ENRICHMENT_REVISION_RACE_RETRY_ENABLED', raising=False)
    result = _deliver(rows, Mock(side_effect=RefreshRevisionChanged()))
    assert (result.outcome, result.reason) == ('retry', 'persistence_fenced')
    assert KEY in rows[0]


def test_action_item_revision_race_kill_switch_restores_the_failure(rows, monkeypatch):
    from database.action_item_refresh import RefreshRevisionChanged

    monkeypatch.setenv('ENRICHMENT_REVISION_RACE_RETRY_ENABLED', 'false')
    with pytest.raises(RefreshRevisionChanged) as raised:
        _deliver(rows, Mock(side_effect=RefreshRevisionChanged()))
    assert isinstance(raised.value, ValueError) and str(raised.value) == 'refresh conversation revision changed'


def test_enrichment_delivery_activates_early_abort_only_during_its_callback(rows):
    from utils.enrichment import early_abort

    seen = []
    result = _deliver(rows, Mock(side_effect=lambda *_: seen.append(early_abort.ACTIVE.get())))
    assert (result.outcome, result.reason) == ('done', 'processed')
    assert seen == [True] and early_abort.ACTIVE.get() is False


def _fenced_run(rows, monkeypatch, *, row, resolved=None, resolve_error=None, first_summary=True):
    # synceff 2026-11-05: a merge redirected the conversation while the run's LLM steps ran, so the persist fenced.
    from database import conversations as conversations_db
    from utils.enrichment import custody
    from utils.enrichment.callback import SyncConversationPersistenceFenced

    if not first_summary:
        rows[0][KEY]['summary_seen'] = True
    reads, resolves, transfers = [], [], []

    def resolve(uid, cid, **_):
        resolves.append(cid)
        if resolve_error is not None:
            raise resolve_error
        return resolved

    monkeypatch.setattr(
        conversations_db, 'get_conversation_raw_snapshot', lambda uid, cid, **kw: reads.append(cid) or row
    )
    monkeypatch.setattr(conversations_db, 'resolve_sync_conversation_redirect', resolve)
    monkeypatch.setattr(custody, 'transfer_redirect', lambda *args, **kwargs: transfers.append(args[3]))
    result = _deliver(rows, Mock(side_effect=SyncConversationPersistenceFenced('synthetic')))
    return result, reads, resolves, transfers


REDIRECTED = {'deleted': True, 'sync_merged_into': 'survivor'}


def test_fenced_run_redirected_mid_run_transfers_custody_to_the_survivor(rows, monkeypatch):
    monkeypatch.delenv('ENRICHMENT_FENCE_REDIRECT_TRANSFER_ENABLED', raising=False)
    result, reads, resolves, transfers = _fenced_run(rows, monkeypatch, row=REDIRECTED, resolved='survivor')
    assert (result.outcome, result.reason) == ('stale', 'redirected')
    assert reads == ['c'] and resolves == ['c'] and transfers == ['survivor']


@pytest.mark.parametrize('resolved,error', [(None, None), ('c', None), (None, RuntimeError('synthetic outage'))])
def test_unresolved_redirect_defers_and_keeps_the_row(rows, monkeypatch, resolved, error):
    result, _reads, _resolves, transfers = _fenced_run(
        rows, monkeypatch, row=REDIRECTED, resolved=resolved, resolve_error=error
    )
    assert result.outcome == 'deferred' and transfers == []
    assert KEY in rows[0]


def test_transient_fault_in_the_fence_redirect_probe_keeps_the_quick_retry(rows, monkeypatch):
    from google.api_core.exceptions import ServiceUnavailable

    result, _reads, _resolves, transfers = _fenced_run(
        rows, monkeypatch, row=REDIRECTED, resolve_error=ServiceUnavailable('synthetic blip')
    )
    assert (result.outcome, result.reason) == ('retry', 'dependency_warming')
    assert transfers == [] and KEY in rows[0]


@pytest.mark.parametrize('row', [{'sync_content_revision': 4}, {'deleted': True}, None])
def test_live_or_plainly_deleted_fenced_row_still_settles_superseded(rows, monkeypatch, row):
    result, reads, resolves, transfers = _fenced_run(rows, monkeypatch, row=row, resolved='survivor')
    assert (result.outcome, result.reason) == ('discarded', 'superseded')
    assert reads == ['c'] and resolves == [] and transfers == []


def test_fence_redirect_kill_switch_keeps_the_superseded_settle(rows, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_FENCE_REDIRECT_TRANSFER_ENABLED', 'false')
    result, reads, resolves, transfers = _fenced_run(rows, monkeypatch, row=REDIRECTED, resolved='survivor')
    assert (result.outcome, result.reason) == ('discarded', 'superseded')
    assert reads == [] and resolves == [] and transfers == []


def test_fence_without_custody_context_reads_nothing(rows, monkeypatch):
    result, reads, resolves, transfers = _fenced_run(
        rows, monkeypatch, row=REDIRECTED, resolved='survivor', first_summary=False
    )
    assert (result.outcome, result.reason) == ('discarded', 'superseded')
    assert reads == [] and resolves == [] and transfers == []


def test_open_live_target_defers_with_a_new_wake(rows, monkeypatch):
    state_rows, tasks = rows
    token = state_rows[KEY]['task_token']

    def live(*_):
        from utils.conversations.summary_delivery import PROCESS_CONTEXT

        context = PROCESS_CONTEXT.get()
        if context is not None:
            context['defer_reason'] = 'open_live_target'

    result = _deliver(rows, live)
    assert (result.outcome, result.reason) == ('deferred', 'not_due')
    assert state_rows[KEY]['due_at'] == pytest.approx(time.time() + reprocess.LIVE_DEFER_SECONDS, abs=5)
    assert state_rows[KEY]['task_token'] != token and tasks[-1]['task_token'] == state_rows[KEY]['task_token']
    # The row records the custody cause (as the sync handler's rows do), not the consumer's not_due.
    assert state_rows[KEY]['deferred_reason'] == 'open_live_target'


def test_long_stuck_live_target_polls_hourly_through_the_consumer(rows, monkeypatch):
    state_rows, _ = rows
    old = time.time() - reprocess.STUCK_DEFER_GRACE_SECONDS - 60
    state_rows[KEY].update(deferred_reason='open_live_target', deferred_since=old, first_pending_at=old)

    def live(*_):
        from utils.conversations.summary_delivery import PROCESS_CONTEXT

        context = PROCESS_CONTEXT.get()
        if context is not None:
            context['defer_reason'] = 'open_live_target'

    result = _deliver(rows, live, now=time.time())  # the episode clock is the settle clock
    assert (result.outcome, result.reason) == ('deferred', 'not_due')
    assert state_rows[KEY]['deferred_since'] == old
    assert state_rows[KEY]['due_at'] == pytest.approx(time.time() + reprocess.STUCK_DEFER_POLL_SECONDS, abs=5)


def test_unexpected_errors_stay_5xx_and_keep_the_lease(rows, client, monkeypatch):
    monkeypatch.setattr(
        consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(side_effect=RuntimeError('synthetic'))
    )
    token = rows[0][KEY]['task_token']
    with pytest.raises(RuntimeError):
        client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert rows[0][KEY]['lease_until'] > 0  # the sweep re-wakes after expiry


def _expire_budget_once_running(monkeypatch, running: threading.Event) -> None:
    """The route's budget wait expires as soon as the callback is running: no real-clock budget to race."""
    import asyncio

    async def expired(work, timeout):
        assert timeout == route.DELIVERY_BUDGET_SECONDS  # the production budget, not a shrunk one
        assert await asyncio.get_running_loop().run_in_executor(None, running.wait, 10)  # expire only mid-callback
        raise asyncio.TimeoutError

    monkeypatch.delenv('ENRICHMENT_DELIVERY_BUDGET_SECONDS', raising=False)
    fake = SimpleNamespace(**{name: getattr(asyncio, name) for name in ('ensure_future', 'shield', 'Future')})
    fake.wait_for, fake.TimeoutError = expired, asyncio.TimeoutError
    monkeypatch.setattr(route, 'asyncio', fake)


def test_a_delivery_past_its_budget_frees_the_slot_with_a_409_and_still_settles(rows, client, monkeypatch):
    running, release = threading.Event(), threading.Event()
    _expire_budget_once_running(monkeypatch, running)

    def slow(*_):
        running.set()
        assert release.wait(10)

    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: slow)
    token = rows[0][KEY]['task_token']
    response = client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 409
    assert response.json() == {'status': 'retry', 'reason': 'dependency_warming'}
    assert rows[0][KEY]['lease_until'] > 0  # the still-running worker owns the lease; a retry now is BUSY
    release.set()
    deadline = time.monotonic() + 5
    while KEY in rows[0] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert KEY not in rows[0]  # the worker settled its own lease: nothing is dropped


def test_a_retry_after_the_budget_rearms_under_a_fresh_wake(rows, client, monkeypatch):
    from fastapi import HTTPException

    running, release = threading.Event(), threading.Event()
    _expire_budget_once_running(monkeypatch, running)

    def slow_then_warming(*_):
        running.set()
        assert release.wait(10)
        raise HTTPException(status_code=503, detail='synthetic')

    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: slow_then_warming)
    state_rows, tasks = rows
    token = state_rows[KEY]['task_token']
    response = client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 409
    woken = len(tasks)
    release.set()
    deadline = time.monotonic() + 5
    while state_rows[KEY]['task_token'] == token and time.monotonic() < deadline:
        time.sleep(0.02)
    row = state_rows[KEY]
    # The budget 409's queue retry was consumed as BUSY, so the released row gets its own new wake.
    assert row['task_token'] != token and row['lease_until'] == 0 and not row.get('owner')
    assert len(tasks) == woken + 1 and tasks[-1]['task_token'] == row['task_token']


def test_heartbeat_stops_renewing_after_the_hold_cap(monkeypatch):
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, 'max_hold_seconds', 0.05)
    heartbeat = Mock(return_value=True)
    with consumer_module._beating(heartbeat, 0.01, None) as lost:
        time.sleep(0.4)
    assert heartbeat.call_count < 15  # ~40 renewals without the cap; the lease now lapses for the sweep
    assert not lost.is_set()  # a callback that finishes before the lapse still settles


@pytest.mark.parametrize(
    'payload',
    [
        None,
        {},
        {'kind': 'job', 'key': KEY, 'task_token': 'a' * 32},
        {'kind': 'enrichment', 'key': 'x', 'task_token': 'y'},
    ],
)
def test_malformed_tasks_are_400(client, payload):
    assert client.post('/v2/enrichment/run', json=payload).status_code == 400


def test_stale_and_busy_wakes_are_consumed(rows, client):
    stale = client.post('/v2/enrichment/run', json={'kind': 'sync_reprocess', 'key': KEY, 'task_token': 'f' * 32})
    assert stale.status_code == 200 and stale.json()['status'] == 'stale'


def test_new_rows_bind_to_the_enrichment_queue_only_when_routed(rows, monkeypatch):
    assert reprocess.dispatch_binding()['handler'].endswith('/v2/sync-jobs/run')
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://workers.invalid/v2/enrichment/run')
    binding = reprocess.dispatch_binding()
    assert binding['queue'] == 'enrichment' and binding['handler'].endswith('/v2/enrichment/run')
    assert reprocess.valid_dispatch_binding(binding)
    monkeypatch.delenv('ENRICHMENT_TASKS_QUEUE')
    assert reprocess.dispatch_binding()['handler'].endswith('/v2/sync-jobs/run')  # incomplete: fall back, counted


@pytest.fixture
def split_binding(state, monkeypatch):  # noqa: F811
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://workers.invalid/v2/enrichment/run')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_QUEUE', 'sync-backfill-fresh')
    monkeypatch.delenv('ENRICHMENT_BACKFILL_ROUTING_ENABLED', raising=False)
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'backfill')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 0)
    monkeypatch.delenv('ENRICHMENT_FRESH_PROMOTE_MAX_AGE_MIN', raising=False)
    return state


def test_new_background_backfill_uses_existing_queue_and_enrichment_identity(split_binding):
    reprocess.mark('u', 'c', 'en', now=0)
    split_binding[0][KEY].update(dormant=True, summary_seen=True, dispatch=None)
    reprocess.mark('u', 'c', 'en', now=1)
    row = split_binding[0][KEY]
    assert row['summary_lane'] == 'backfill'
    assert row['dispatch'] == {
        'queue': 'sync-backfill-fresh',
        'handler': 'https://workers.invalid/v2/enrichment/run',
        'audience': 'https://workers.invalid/v2/enrichment/run',
        'invoker_sa': 'invoker@example.invalid',
    }


@pytest.mark.parametrize('lane', ['fresh', 'live', 'batch', 'integration'])
def test_other_lanes_keep_enrichment_queue(split_binding, monkeypatch, lane):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: lane)
    reprocess.mark('u', 'c', 'en', now=0)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'


def test_pending_backfill_first_summary_keeps_enrichment_queue(split_binding, monkeypatch):
    reprocess.mark('u', 'c', 'en', now=0, snapshot_summary=True)
    row = split_binding[0][KEY]
    assert reprocess.first_summary_pending(row)
    assert row['dispatch']['queue'] == 'enrichment'


@pytest.mark.parametrize('disable', ['false', ' FALSE '])
def test_backfill_split_kill_switch(split_binding, monkeypatch, disable):
    monkeypatch.setenv('ENRICHMENT_BACKFILL_ROUTING_ENABLED', disable)
    reprocess.mark('u', 'c', 'en', now=0)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'


def test_missing_backfill_queue_keeps_existing_binding(split_binding, monkeypatch):
    monkeypatch.delenv('SYNC_BACKFILL_TASKS_QUEUE')
    reprocess.mark('u', 'c', 'en', now=0)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'


def test_active_backfill_binding_survives_coalescing_and_retries(split_binding, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_BACKFILL_ROUTING_ENABLED', 'false')
    reprocess.mark('u', 'c', 'en', now=0)
    split_binding[0][KEY].update(dormant=True, summary_seen=True, dispatch=None)
    reprocess.mark('u', 'c', 'en', now=1)
    original = dict(split_binding[0][KEY]['dispatch'])
    monkeypatch.delenv('ENRICHMENT_BACKFILL_ROUTING_ENABLED')
    reprocess.mark('u', 'c', 'en', now=100)
    assert split_binding[0][KEY]['dispatch'] == original
    assert reprocess.run(KEY, split_binding[0][KEY]['task_token'], Mock(), now=600) == 'deferred'
    assert split_binding[1][-1]['dispatch'] == original


def test_reopened_backfill_receipt_routes_new_background_obligation(split_binding, monkeypatch):
    reprocess.mark('u', 'c', 'en', now=0)
    split_binding[0][KEY].update(dormant=True, summary_seen=True, dispatch=None)
    reprocess.mark('u', 'c', 'en', now=100)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'sync-backfill-fresh'


def test_backfill_effects_use_existing_queue(split_binding):
    assert reprocess._effects_binding()['queue'] == 'sync-backfill-fresh'


@pytest.mark.parametrize('lane', ['fresh', 'live', 'batch', 'integration'])
def test_new_pending_first_summary_has_reserved_dispatch_slots(split_binding, monkeypatch, lane):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: lane)
    reprocess.mark('u', 'c', 'en', now=0)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment-fresh'


@pytest.mark.parametrize('pending', [False, True])
def test_recent_reopened_obligation_routes_by_pending_state(split_binding, monkeypatch, pending):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    reprocess.mark('u', 'c', 'en', now=0)
    token = split_binding[0][KEY]['task_token']
    split_binding[0][KEY].update(dormant=True, summary_seen=not pending)
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    clock = Mock(return_value=9700)
    monkeypatch.setattr(reprocess, '_conversation_finished_at', clock)
    reprocess.mark('u', 'c', 'en', now=10_000)
    row = split_binding[0][KEY]
    assert row['dispatch']['queue'] == ('enrichment-fresh' if pending else 'enrichment')
    assert row['task_token'] != token
    assert clock.call_count == int(pending)


def test_new_disabled_first_summary_policy_uses_primary_without_clock_read(split_binding, monkeypatch):
    from config.policy import FirstSummaryPolicy

    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    monkeypatch.setattr(
        reprocess, 'resolve_stage_policy', lambda *_args, **_kwargs: FirstSummaryPolicy(first_summary_enabled=False)
    )
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    clock = Mock(return_value=9700)
    monkeypatch.setattr(reprocess, '_conversation_finished_at', clock)
    reprocess.mark('u', 'c', 'en', now=10_000, snapshot_summary=True)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'
    clock.assert_not_called()


def test_admission_cas_retry_rechecks_summary_state_after_cached_recency(split_binding, monkeypatch):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    clock = Mock(return_value=9700)
    monkeypatch.setattr(reprocess, '_conversation_finished_at', clock)
    update = reprocess.mark_update(
        'u', 'c', 'en', current=10_000, settle_at=10_600, coalesce='max', effects_only=False, batch=False
    )
    row, _ = update(None)
    assert row['dispatch']['queue'] == 'enrichment-fresh'
    row.update(dormant=True, summary_seen=True)
    retried, _ = update(row)
    assert retried['dispatch']['queue'] == 'enrichment'
    clock.assert_called_once()


def test_backfill_fallback_cannot_enter_fresh_queue(split_binding, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.delenv('SYNC_BACKFILL_TASKS_QUEUE')
    reprocess.mark('u', 'c', 'en', now=0)
    split_binding[0][KEY].update(dormant=True, summary_seen=True, dispatch=None)
    reprocess.mark('u', 'c', 'en', now=1)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'


def test_fresh_lazy_effects_cannot_enter_fresh_queue(split_binding, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'fresh')
    assert reprocess._effects_binding()['queue'] == 'enrichment'
    reprocess.mark('u', 'c', 'en', now=0, effects_only=True)
    assert split_binding[0][reprocess.key('u', 'c\0effects')]['dispatch']['queue'] == 'enrichment'


@pytest.mark.parametrize('pending', [False, True])
def test_backfill_first_summary_gets_priority_only_while_pending(split_binding, monkeypatch, pending):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    reprocess.mark('u', 'c', 'en', now=0, snapshot_summary=True)
    if not pending:
        split_binding[0][KEY].update(dormant=True, summary_seen=True, dispatch=None)
        reprocess.mark('u', 'c', 'en', now=1)
    assert split_binding[0][KEY]['dispatch']['queue'] == ('enrichment-fresh' if pending else 'sync-backfill-fresh')


def test_sweep_promotes_waiting_fresh_work_and_fences_old_delivery(split_binding, sweep_query, monkeypatch):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    reprocess.mark('u', 'c', 'en', now=0)
    old_token = split_binding[0][KEY]['task_token']
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 9700)  # Finished five minutes ago.
    assert reprocess.sweep(now=10_000) == {'repaired': 1, 'error': 0}
    row = split_binding[0][KEY]
    assert row['dispatch'] == {
        'queue': 'enrichment-fresh',
        'handler': 'https://workers.invalid/v2/enrichment/run',
        'audience': 'https://workers.invalid/v2/enrichment/run',
        'invoker_sa': 'invoker@example.invalid',
    }
    assert row['task_token'] != old_token
    process = Mock()
    assert reprocess.run(KEY, old_token, process, now=10_000) == 'stale'
    process.assert_not_called()


@pytest.mark.parametrize('unbound', [False, True])
@pytest.mark.parametrize('summary_state', ['pending', 'seen', 'disabled', 'effects'])
def test_sweep_reserves_fresh_only_for_pending_first_summaries(
    split_binding, sweep_query, monkeypatch, unbound, summary_state
):
    from config.policy import FirstSummaryPolicy

    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    reprocess.mark('u', 'c', 'en', now=0)
    row = split_binding[0][KEY]
    row['summary_seen'] = summary_state == 'seen'
    row['effects_only'] = summary_state == 'effects'
    if summary_state == 'disabled':
        row['first_summary_policy'] = FirstSummaryPolicy(first_summary_enabled=False).to_dict()
    if unbound:
        row['dispatch'] = None
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    clock = Mock(return_value=9700)
    monkeypatch.setattr(reprocess, '_conversation_finished_at', clock)
    reprocess.sweep(now=10_000)
    pending = summary_state == 'pending'
    assert split_binding[0][KEY]['dispatch']['queue'] == ('enrichment-fresh' if pending else 'enrichment')
    assert clock.call_count == int(pending)


def test_leased_refresh_keeps_existing_fresh_binding_until_reopened(split_binding, sweep_query, monkeypatch):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    reprocess.mark('u', 'c', 'en', now=0)
    row = split_binding[0][KEY]
    row.update(summary_seen=True, lease_until=20_000)
    binding, token = dict(row['dispatch']), row['task_token']
    clock = Mock(return_value=9700)
    monkeypatch.setattr(reprocess, '_conversation_finished_at', clock)
    reprocess.mark('u', 'c', 'en', now=10)
    reprocess.sweep(now=10_000)
    assert split_binding[0][KEY]['dispatch'] == binding
    assert split_binding[0][KEY]['task_token'] == token
    clock.assert_not_called()


@pytest.mark.parametrize('reopened', [False, True])
@pytest.mark.parametrize('age,queue', [(300, 'enrichment-fresh'), (7200, 'enrichment')])
def test_dispatch_uses_conversation_age_not_new_obligation_age(split_binding, monkeypatch, reopened, age, queue):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    if reopened:
        reprocess.mark('u', 'c', 'en', now=0)
        split_binding[0][KEY]['dormant'] = True
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 10_000 - age)
    reprocess.mark('u', 'c', 'en', now=10_000)
    assert split_binding[0][KEY]['dispatch']['queue'] == queue


def test_sweep_keeps_two_hour_old_idle_backlog_on_existing_queue(split_binding, sweep_query, monkeypatch):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    reprocess.mark('u', 'c', 'en', now=0)
    binding = dict(split_binding[0][KEY]['dispatch'])
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 2800)
    reprocess.sweep(now=10_000)
    assert split_binding[0][KEY]['dispatch'] == binding


@pytest.mark.parametrize('minutes,expected', [('1', False), ('30', True), ('0', False), ('bad', True), ('nan', True)])
def test_fresh_priority_window_configuration(split_binding, monkeypatch, minutes, expected):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setenv('ENRICHMENT_FRESH_PROMOTE_MAX_AGE_MIN', minutes)
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 9700)
    assert reprocess._recent_conversation('u', 'c', 10_000) is expected


@pytest.mark.parametrize('metadata', [None, 'invalid', float('nan'), True, 10_001])
def test_unknown_or_future_conversation_time_keeps_established_queue(split_binding, monkeypatch, metadata):
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: metadata)
    assert not reprocess._recent_conversation('u', 'c', 10_000)


@pytest.mark.parametrize('finished', [None, datetime.fromtimestamp(9700, timezone.utc)])
def test_priority_lookup_reads_only_conversation_clocks(state, monkeypatch, finished):
    from utils.enrichment import outbox

    document = Mock()
    document.get.return_value.to_dict.return_value = {
        'created_at': datetime.fromtimestamp(9700, timezone.utc),
        'finished_at': finished,
    }
    client = Mock()
    client.document.return_value = document
    monkeypatch.setattr(outbox, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    assert outbox._recent_conversation('u', 'c', 10_000)
    document.get.assert_called_once_with(field_paths=['finished_at', 'created_at'], timeout=2, retry=None)


def test_priority_metadata_failure_leaves_new_work_on_existing_queue(split_binding, monkeypatch):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', Mock(side_effect=RuntimeError('unavailable')))
    reprocess.mark('u', 'c', 'en', now=10_000)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'


@pytest.mark.parametrize('fence', ['lease', 'effects', 'backfill', 'identity'])
def test_priority_sweep_preserves_custody_and_background_work(split_binding, sweep_query, monkeypatch, fence):
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'batch')
    reprocess.mark('u', 'c', 'en', now=0)
    row = split_binding[0][KEY]
    if fence == 'lease':
        row['lease_until'] = 20_000
    elif fence == 'effects':
        row['effects_only'] = True
    elif fence == 'backfill':
        row['summary_lane'] = 'backfill'
        row['summary_seen'] = True
    else:
        row['dispatch']['handler'] = row['dispatch']['audience'] = 'https://other.invalid/v2/enrichment/run'
    monkeypatch.setenv('ENRICHMENT_FRESH_TASKS_QUEUE', 'enrichment-fresh')
    monkeypatch.setattr(reprocess, '_conversation_finished_at', lambda *_: 9700)
    reprocess.sweep(now=10_000)
    assert split_binding[0][KEY]['dispatch']['queue'] == 'enrichment'


def test_backfill_route_reaches_named_task_creation(split_binding, monkeypatch):
    from utils import cloud_tasks
    from utils.conversations import demand_processing
    from tests.unit.test_sync_reprocess_coalesce import _ENQUEUE

    reprocess.mark('u', 'c', 'en', now=0)
    create = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', create)
    monkeypatch.setattr(demand_processing, 'schedule', lambda *_args, **_kwargs: False)
    _ENQUEUE(split_binding[0][KEY])
    assert create.call_args.args[:2] == ('enrichment', 'https://workers.invalid/v2/enrichment/run')
    assert create.call_args.kwargs['audience'] == 'https://workers.invalid/v2/enrichment/run'


def test_snapshot_first_summary_is_protected_after_env_rollback(split_binding, monkeypatch):
    from config.policy import FirstSummaryPolicy

    operation = reprocess.mark_update(
        'u', 'c', 'en', current=0, settle_at=600, coalesce='max', effects_only=False, batch=False
    )
    old = {
        'dormant': True,
        'summary_lane': 'backfill',
        'first_summary_policy': FirstSummaryPolicy(first_summary_enabled=True).to_dict(),
    }
    row, _ = operation(old)
    assert reprocess.first_summary_pending(row)
    assert row['dispatch']['queue'] == 'enrichment'


@pytest.mark.parametrize('pending', [False, True])
def test_sweep_routes_previously_unbound_backfill_by_summary_state(split_binding, sweep_query, monkeypatch, pending):
    monkeypatch.delenv('ENRICHMENT_TASKS_HANDLER_URL')
    monkeypatch.delenv('SYNC_TASKS_HANDLER_URL')
    reprocess.mark('u', 'c', 'en', now=0, snapshot_summary=True)
    row = split_binding[0][KEY]
    if not pending:
        row['summary_seen'] = True
    assert row['dispatch'] is None and not split_binding[1]
    token = row['task_token']

    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://workers.invalid/v2/enrichment/run')
    assert reprocess.sweep(now=10_000) == {'repaired': 1, 'error': 0}
    repaired = split_binding[0][KEY]
    assert repaired['dispatch']['queue'] == ('enrichment' if pending else 'sync-backfill-fresh')
    assert repaired['task_token'] != token
    assert split_binding[1][-1]['dispatch'] == repaired['dispatch']


def test_unbound_backfill_effects_keep_lane_for_repair_on_a_fresh_host(split_binding, sweep_query, monkeypatch):
    rows, tasks = split_binding
    repair_client = reprocess.get_firestore_client()
    effects_key = reprocess.key('u', 'c\0effects')

    def persist(body, *, merge):
        assert merge
        rows[effects_key] = {**body, 'version': 1}

    document = SimpleNamespace(set=persist)
    client = SimpleNamespace(collection=lambda _: SimpleNamespace(document=lambda _: document))
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(reprocess, '_effects_binding', lambda: {})
    monkeypatch.setattr(reprocess.time, 'time', lambda: 0)
    reprocess.mark_effects('u', 'c', 'en')
    assert rows[effects_key]['summary_lane'] == 'backfill' and not tasks

    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: repair_client)
    monkeypatch.setattr(reprocess.summary_delivery, 'lane', lambda _: 'fresh')
    assert reprocess.sweep(now=3600) == {'repaired': 1, 'error': 0}
    assert tasks[-1]['dispatch']['queue'] == 'sync-backfill-fresh'


def test_not_due_wake_rearms_and_answers_200_not_due(state, monkeypatch):  # noqa: F811
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    monkeypatch.setattr(custody, 'discard_blocked', lambda _row_id: False)
    reprocess.mark('u', 'c', 'en', now=time.time())  # settles 600s from now
    state_rows, tasks = state
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.verify_enrichment_task] = lambda: 0
    token = state_rows[KEY]['task_token']
    response = TestClient(app).post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 200 and response.json() == {'status': 'deferred', 'reason': 'not_due'}
    assert state_rows[KEY]['task_token'] != token and tasks[-1]['task_token'] == state_rows[KEY]['task_token']


@pytest.mark.asyncio
async def test_legacy_sync_handler_delegates_to_the_consumer_when_routed(rows, monkeypatch):
    from routers import batch_pipeline

    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: _pending)
    monkeypatch.setattr(batch_pipeline, 'run_enrichment', Mock(side_effect=AssertionError('legacy run used')))
    token = rows[0][KEY]['task_token']
    response = await batch_pipeline.enrichment_response({'kind': 'sync_reprocess', 'key': KEY, 'task_token': token})
    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'retry', 'reason': 'callback_pending'}


@pytest.mark.asyncio
async def test_legacy_bound_slow_delivery_logs_its_end_too(rows, monkeypatch, caplog):
    from routers import batch_pipeline

    caplog.set_level(logging.INFO)
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setattr(route, 'SLOW_DELIVERY_SECONDS', 0.0)
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(return_value=None))
    token = rows[0][KEY]['task_token']
    response = await batch_pipeline.enrichment_response({'kind': 'sync_reprocess', 'key': KEY, 'task_token': token})
    assert response.status_code == 200
    ends = [r.getMessage() for r in caplog.records if r.getMessage().startswith('event=enrichment_delivery ')]
    assert len(ends) == 1 and ends[0].startswith('event=enrichment_delivery outcome=done reason=processed wait_s=')


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(500, 409), (502, 409), (429, 409), (400, 500)])
async def test_legacy_handler_retries_processing_dependency_failures_without_5xx(monkeypatch, status, code):
    """Lane 4 staging replay 10-19: 51/63 sync-jobs deliveries answered 500 on HTTPException from processing."""
    from fastapi import HTTPException
    from routers import batch_pipeline

    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(batch_pipeline, 'run_enrichment', Mock(side_effect=HTTPException(status_code=status)))

    async def run(_executor, func, *args):
        return func(*args)

    monkeypatch.setattr(batch_pipeline, 'run_blocking', run)
    response = await batch_pipeline.enrichment_response({'kind': 'sync_reprocess', 'key': KEY, 'task_token': 'b' * 32})
    assert response.status_code == code
    if code == 409:
        assert json.loads(response.body) == {'status': 'retry', 'reason': 'dependency_warming'}


def test_consumer_retries_a_processing_dependency_failure_and_keeps_the_wake(rows):
    from fastapi import HTTPException

    token = rows[0][KEY]['task_token']
    result = _deliver(rows, Mock(side_effect=HTTPException(status_code=502)))
    assert (result.outcome, result.reason) == ('retry', 'dependency_warming')
    assert rows[0][KEY]['lease_until'] == 0 and rows[0][KEY]['task_token'] == token


def _gateway_status(status):
    import httpx

    request = httpx.Request('POST', 'http://gateway.invalid/v1/embeddings')
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError('synthetic', request=request, response=response)


def _remapped_aborted():
    """Firestore's commit path: api_core remaps the grpc error, raised from it."""
    from google.api_core import exceptions as google_errors

    try:
        raise RuntimeError('synthetic grpc _InactiveRpcError')
    except RuntimeError as source:
        try:
            raise google_errors.Aborted('synthetic contention') from source
        except google_errors.Aborted as error:
            return error


def _wrapped_read_timeout():
    """A caller's wrapper around the gateway's embedding read timeout."""
    import httpx

    error = RuntimeError('synthetic wrapper')
    error.__cause__ = httpx.ReadTimeout('synthetic')
    return error


@pytest.mark.parametrize(
    'error',
    [
        pytest.param(_remapped_aborted(), id='firestore-aborted'),
        pytest.param(_gateway_status(503), id='gateway-503'),
        pytest.param(_wrapped_read_timeout(), id='wrapped-read-timeout'),
    ],
)
def test_transient_dependency_faults_release_the_lease_as_409(rows, client, monkeypatch, error):
    """Prod 11-03: these answered 500 and kept the lease, so the queue retry was consumed as BUSY."""
    monkeypatch.setattr(consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(side_effect=error))
    token = rows[0][KEY]['task_token']
    response = client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert response.status_code == 409
    assert response.json() == {'status': 'retry', 'reason': 'dependency_warming'}
    assert rows[0][KEY]['lease_until'] == 0 and rows[0][KEY]['task_token'] == token


def test_transient_fault_in_the_empty_output_strike_releases_the_lease(rows, monkeypatch):
    """Luna r1: a store fault inside ``record_empty_failure`` is outside the callback's except clauses."""
    import database._client as firestore_client
    import database.summary_processing as summary_processing

    monkeypatch.setattr(firestore_client, 'get_firestore_client', Mock())
    monkeypatch.setattr(summary_processing, 'record_empty_failure', Mock(side_effect=_remapped_aborted()))
    token = rows[0][KEY]['task_token']
    result = _deliver(rows, lambda *_: SimpleNamespace(structured={'title': 'Synthetic'}))
    assert (result.outcome, result.reason) == ('retry', 'dependency_warming')
    assert rows[0][KEY]['lease_until'] == 0 and rows[0][KEY]['task_token'] == token


def test_empty_output_owner_race_defers_without_burning_callback_attempts(rows, monkeypatch):
    import database._client as firestore_client
    import database.summary_processing as summary_processing

    monkeypatch.setattr(firestore_client, 'get_firestore_client', Mock())
    monkeypatch.setattr(
        summary_processing,
        'record_empty_failure',
        Mock(return_value=summary_processing.EmptyFailureOutcome.OWNER_MISMATCH),
    )
    rows[0][KEY].update(summary_empty_failures=2)
    token = rows[0][KEY]['task_token']
    result = _deliver(rows, lambda *_: SimpleNamespace(structured={'title': 'Synthetic'}))
    assert (result.outcome, result.reason) == ('deferred', 'not_due')
    pending = rows[0][KEY]
    assert pending['deferred_reason'] == 'summary_owner_changed'
    assert pending['summary_empty_failures'] == 2
    assert pending['task_token'] != token and pending['lease_until'] == 0


def test_transient_fault_on_the_effects_only_path_releases_the_lease(rows, monkeypatch):
    """Luna r1: the effects-only branch runs before the callback block."""
    from utils.conversations import lazy_enrichment

    rows[0][KEY]['effects_only'] = True
    monkeypatch.setattr(lazy_enrichment, 'enrich_settled', Mock(side_effect=_gateway_status(503)))
    token = rows[0][KEY]['task_token']
    result = _deliver(rows, Mock())
    assert (result.outcome, result.reason) == ('retry', 'dependency_warming')
    assert rows[0][KEY]['lease_until'] == 0 and rows[0][KEY]['task_token'] == token


def test_non_transient_gateway_status_stays_5xx_and_keeps_the_lease(rows, client, monkeypatch):
    import httpx

    monkeypatch.setattr(
        consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(side_effect=_gateway_status(400))
    )
    token = rows[0][KEY]['task_token']
    with pytest.raises(httpx.HTTPStatusError):
        client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert rows[0][KEY]['lease_until'] > 0


def _provider_sweep(monkeypatch, sweep):
    """Stub the C8 provider-STT outbox that maintain() also sweeps (M3 review); never touches Firestore."""
    import database.outbox as outbox_module
    from types import SimpleNamespace

    monkeypatch.setattr(outbox_module, 'outbox_for', lambda kind: SimpleNamespace(sweep=sweep))


@pytest.mark.parametrize('near_expiry', [2, None], ids=['current', 'legacy'])
def test_maintenance_sweeps_the_outbox_and_admits_summary_debt(rows, monkeypatch, near_expiry):
    from services import summary_debt_repair
    from database.outbox import SweepCounts

    monkeypatch.setattr(ENRICHMENT_OUTBOX, 'sweep', lambda *, now, limit=100: SweepCounts(2, 0, 1, 0))
    _provider_sweep(monkeypatch, lambda *, now, limit=100: SweepCounts(4, 1, 2, 1))
    tick_counts = {'scanned': 5, 'admitted': 3, 'errors': 0, 'expired_seen': 2}
    if near_expiry is not None:
        tick_counts['near_expiry_admitted'] = near_expiry
    monkeypatch.setattr(
        summary_debt_repair,
        'tick',
        lambda *, now: tick_counts,
    )
    assert route.maintain(1000.0) == {
        'rewoken': 2,
        'discarded': 1,
        'sweep_errors': 0,
        'provider_stt_rewoken': 4,
        'provider_stt_discarded': 2,
        'provider_stt_sweep_errors': 1,
        'summary_debt_scanned': 5,
        'summary_debt_expired_seen': 2,
        'summary_debt_admitted': 3,
        'summary_debt_near_expiry_admitted': near_expiry or 0,
        'summary_debt_errors': 0,
    }


def test_maintenance_counts_a_summary_debt_failure_without_5xx(rows, client, monkeypatch):
    from services import summary_debt_repair
    from database.outbox import SweepCounts

    monkeypatch.setattr(ENRICHMENT_OUTBOX, 'sweep', lambda *, now, limit=100: SweepCounts(0, 0, 0, 0))
    _provider_sweep(monkeypatch, lambda *, now, limit=100: SweepCounts(0, 0, 0, 0))
    monkeypatch.setattr(summary_debt_repair, 'tick', Mock(side_effect=RuntimeError('synthetic')))
    response = client.post('/v2/enrichment/sweep')
    assert response.status_code == 200
    assert response.json()['counts']['summary_debt_errors'] == 1


def test_maintenance_isolates_a_provider_stt_sweep_failure(rows, monkeypatch):
    """A provider-STT sweep error is counted and never blocks the enrichment half or summary debt."""
    from services import summary_debt_repair
    from database.outbox import SweepCounts

    monkeypatch.setattr(ENRICHMENT_OUTBOX, 'sweep', lambda *, now, limit=100: SweepCounts(1, 0, 0, 0))
    _provider_sweep(monkeypatch, Mock(side_effect=RuntimeError('synthetic')))
    monkeypatch.setattr(
        summary_debt_repair,
        'tick',
        lambda *, now: {'scanned': 1, 'admitted': 1, 'near_expiry_admitted': 0, 'errors': 0, 'expired_seen': 0},
    )
    counts = route.maintain(1000.0)
    assert counts['rewoken'] == 1 and counts['provider_stt_sweep_errors'] == 1
    assert counts['summary_debt_admitted'] == 1


def _oversized_write_rejection():
    from google.api_core.exceptions import InvalidArgument

    return InvalidArgument(
        "400 Document 'projects/p/databases/(default)/documents/users/u/conversations/c' cannot be written "
        "because its size (1,048,631 bytes) exceeds the maximum allowed size of 1,048,576 bytes."
    )


def test_oversized_conversation_holds_the_outbox_row_instead_of_rewaking(rows, monkeypatch):
    """#23341: the 1 MiB refusal is permanent; the row parks dormant with its reason and no task retries."""
    state_rows, tasks = rows
    token = state_rows[KEY]['task_token']
    process = Mock(side_effect=_oversized_write_rejection())
    assert reprocess.run(KEY, token, process, now=10_000.0) == 'held'
    process.assert_called_once_with('u', 'c', 'en')
    row = state_rows[KEY]
    assert row['dormant'] and row['due_at'] is None and row['lease_until'] == 0 and row['owner'] is None
    assert row['held_reason'] == 'document_size_limit'
    assert row['uid'] == 'u' and row['conversation_id'] == 'c'  # kept findable for a later rollover
    assert len(tasks) == 1  # no successor wake
    # A Cloud Tasks redelivery claims a dormant row as stale (the sweep skips dormant rows the same way).
    assert reprocess.run(KEY, token, process, now=10_001.0) == 'stale'
    assert len(tasks) == 1
    process.assert_called_once()


def test_other_invalid_argument_rejections_still_surface_from_the_outbox(rows):
    from google.api_core.exceptions import InvalidArgument

    state_rows, _tasks = rows
    token = state_rows[KEY]['task_token']
    with pytest.raises(InvalidArgument):
        reprocess.run(KEY, token, Mock(side_effect=InvalidArgument('400 synthetic unrelated rejection')), now=10_000.0)
    assert not state_rows[KEY].get('dormant')


@pytest.mark.asyncio
async def test_legacy_sync_handler_acks_an_oversized_conversation_with_200(rows, monkeypatch):
    from routers import batch_pipeline
    from utils.batch_pipeline import enrichment

    state_rows, _tasks = rows
    # run_enrichment binds discard_blocked by name; the fixture's custody patch does not reach it.
    monkeypatch.setattr(enrichment, 'discard_blocked', lambda _document_id: False)
    monkeypatch.setattr(callback, 'enrich_conversation', Mock(side_effect=_oversized_write_rejection()))

    async def run(_executor, func, *args):
        return func(*args)

    monkeypatch.setattr(batch_pipeline, 'run_blocking', run)
    payload = {'kind': 'sync_reprocess', 'key': KEY, 'task_token': state_rows[KEY]['task_token']}
    response = await batch_pipeline.enrichment_response(payload)
    assert response.status_code == 200
    assert json.loads(response.body) == {'status': 'held'}
    assert state_rows[KEY]['held_reason'] == 'document_size_limit'
    redelivery = await batch_pipeline.enrichment_response(payload)
    assert redelivery.status_code == 200
    assert json.loads(redelivery.body) == {'status': 'stale'}


# synceff 2026-11-05 (lead2 71492d): the per-row repeat-supersede streak and its histogram.


def _streak_count(le):
    from prometheus_client import REGISTRY

    return REGISTRY.get_sample_value('omi_enrichment_supersede_streak_bucket', {'le': le}) or 0.0


def _superseded_with_a_newer_mark(rows, *, now):
    from utils.enrichment.callback import SyncConversationPersistenceFenced

    def fenced(uid, conversation_id, language):
        reprocess.mark(uid, conversation_id, language, now=now - 100)  # the append that moved the revision
        raise SyncConversationPersistenceFenced('synthetic')

    return _deliver(rows, fenced, now=now)


def test_consecutive_supersedes_build_a_bounded_streak_and_processed_clears_it(rows):
    from database.outbox_firestore import SUPERSEDE_STREAK_FIELD

    before = _streak_count('2.0') - _streak_count('1.0')
    assert _superseded_with_a_newer_mark(rows, now=10_000).reason == 'superseded'
    assert rows[0][KEY][SUPERSEDE_STREAK_FIELD] == 1
    assert _superseded_with_a_newer_mark(rows, now=20_000).reason == 'superseded'
    assert rows[0][KEY][SUPERSEDE_STREAK_FIELD] == 2
    assert _streak_count('2.0') - _streak_count('1.0') == before + 1  # one observation of streak 2
    assert _deliver(rows, Mock(return_value=None), now=30_000).reason == 'processed'
    assert SUPERSEDE_STREAK_FIELD not in (rows[0].get(KEY) or {})


def test_revision_race_retry_counts_toward_the_streak(rows):
    from database.action_item_refresh import RefreshRevisionChanged
    from database.outbox_firestore import SUPERSEDE_STREAK_FIELD

    result = _deliver(rows, Mock(side_effect=RefreshRevisionChanged()))
    assert (result.outcome, result.reason) == ('retry', 'persistence_fenced')
    assert rows[0][KEY][SUPERSEDE_STREAK_FIELD] == 1


def test_streak_is_capped(rows):
    from database.outbox_firestore import SUPERSEDE_STREAK_CAP, SUPERSEDE_STREAK_FIELD

    rows[0][KEY][SUPERSEDE_STREAK_FIELD] = SUPERSEDE_STREAK_CAP
    _superseded_with_a_newer_mark(rows, now=10_000)
    assert rows[0][KEY][SUPERSEDE_STREAK_FIELD] == SUPERSEDE_STREAK_CAP


def test_enrichment_early_abort_and_streak_metrics_pass_the_gmp_sync_allowlist():
    # synceff 2026-11-05: backend-integration has the sidecar, but its keep list hid these two families.
    import re
    from pathlib import Path

    import yaml

    config = yaml.safe_load((Path(__file__).parents[2] / 'deploy' / 'cloud_run_gmp_sync.yaml').read_text())
    rules = config['spec']['endpoints'][0]['metricRelabeling']
    keep = [row['regex'] for row in rules if row['action'] == 'keep' and row['sourceLabels'] == ['__name__']]
    for name in (
        'omi_enrichment_early_abort_total',
        'omi_enrichment_supersede_streak_bucket',
        'omi_enrichment_supersede_streak_count',
        'omi_enrichment_supersede_streak_sum',
    ):
        assert any(re.fullmatch(pattern, name) for pattern in keep), name
    for name in (
        'omi_enrichment_supersede_streak_other',
        'enrichment_early_abort_total',
        'omi_enrichment_early_abort_total_extra',
        'omi_enrichment_early_abort',
    ):
        assert not any(re.fullmatch(pattern, name) for pattern in keep), name
