"""C3: ``POST /v2/enrichment/run`` over the outbox consumer (contracts (a), (d)).

Expected retries answer 409 ``retry``, never 5xx/429/503 (the 10-18 and 10-19 queue stalls). Consumed
deliveries answer 200. Rows bound to the legacy ``/v2/sync-jobs/run`` handler and to this one share the
same payload and row, so both drain.
"""

import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database.outbox_firestore import ENRICHMENT_OUTBOX
from routers import enrichment as route
from tests.unit.test_sync_reprocess_coalesce import state  # noqa: F401
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


def _provider_sweep(monkeypatch, sweep):
    """Stub the C8 provider-STT outbox that maintain() also sweeps (M3 review); never touches Firestore."""
    import database.outbox as outbox_module
    from types import SimpleNamespace

    monkeypatch.setattr(outbox_module, 'outbox_for', lambda kind: SimpleNamespace(sweep=sweep))


def test_maintenance_sweeps_the_outbox_and_admits_summary_debt(rows, monkeypatch):
    from services import summary_debt_repair
    from database.outbox import SweepCounts

    monkeypatch.setattr(ENRICHMENT_OUTBOX, 'sweep', lambda *, now, limit=100: SweepCounts(2, 0, 1, 0))
    _provider_sweep(monkeypatch, lambda *, now, limit=100: SweepCounts(4, 1, 2, 1))
    monkeypatch.setattr(summary_debt_repair, 'tick', lambda *, now: {'scanned': 5, 'admitted': 3, 'errors': 0})
    assert route.maintain(1000.0) == {
        'rewoken': 2,
        'discarded': 1,
        'sweep_errors': 0,
        'provider_stt_rewoken': 4,
        'provider_stt_discarded': 2,
        'provider_stt_sweep_errors': 1,
        'summary_debt_scanned': 5,
        'summary_debt_admitted': 3,
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
    monkeypatch.setattr(summary_debt_repair, 'tick', lambda *, now: {'scanned': 1, 'admitted': 1, 'errors': 0})
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
