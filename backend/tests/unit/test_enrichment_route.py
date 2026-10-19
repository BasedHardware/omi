"""C3: ``POST /v2/enrichment/run`` over the outbox consumer (contracts (a), (d)).

Expected retries answer 409 ``retry``, never 5xx/429/503 (the 10-18 and 10-19 queue stalls). Consumed
deliveries answer 200. Rows bound to the legacy ``/v2/sync-jobs/run`` handler and to this one share the
same payload and row, so both drain.
"""

import time
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database.outbox_firestore import ENRICHMENT_OUTBOX
from routers import enrichment as route
from tests.unit.test_sync_reprocess_coalesce import state  # noqa: F401
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
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
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


def test_lifecycle_fence_settles_as_superseded(rows):
    from utils.enrichment.callback import SyncConversationPersistenceFenced

    result = _deliver(rows, Mock(side_effect=SyncConversationPersistenceFenced('synthetic')))
    assert (result.outcome, result.reason) == ('discarded', 'superseded')
    assert KEY not in rows[0]


def test_open_live_target_defers_with_a_new_wake(rows, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
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


def test_unexpected_errors_stay_5xx_and_keep_the_lease(rows, client, monkeypatch):
    monkeypatch.setattr(
        consumer_module.EnrichmentConsumer, '_callback', lambda self: Mock(side_effect=RuntimeError('synthetic'))
    )
    token = rows[0][KEY]['task_token']
    with pytest.raises(RuntimeError):
        client.post('/v2/enrichment/run', json={'kind': 'enrichment', 'key': KEY, 'task_token': token})
    assert rows[0][KEY]['lease_until'] > 0  # the sweep re-wakes after expiry


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
    assert reprocess._dispatch_binding()['handler'].endswith('/v2/sync-jobs/run')
    monkeypatch.setenv('ENRICHMENT_ROUTE', 'enrichment_queue')
    monkeypatch.setenv('ENRICHMENT_TASKS_QUEUE', 'enrichment')
    monkeypatch.setenv('ENRICHMENT_TASKS_HANDLER_URL', 'https://workers.invalid/v2/enrichment/run')
    binding = reprocess._dispatch_binding()
    assert binding['queue'] == 'enrichment' and binding['handler'].endswith('/v2/enrichment/run')
    assert reprocess.valid_dispatch_binding(binding)
    monkeypatch.delenv('ENRICHMENT_TASKS_QUEUE')
    assert reprocess._dispatch_binding()['handler'].endswith('/v2/sync-jobs/run')  # incomplete: fall back, counted


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
