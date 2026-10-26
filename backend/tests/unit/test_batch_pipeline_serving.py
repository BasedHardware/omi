"""Private pull/complete RPC enforces identity and stage while admission is off."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import asyncio
from dataclasses import asdict
import json
import logging
import threading
from unittest.mock import Mock

from prometheus_client import CollectorRegistry
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
import pytest

from routers import batch_pipeline as module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import PoolCapacity
from utils.batch_pipeline.serving import Serving
from utils.batch_pipeline.metrics import QueueMetrics
from utils.batch_pipeline.scheduler import Scheduler


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    store = MemoryStore()
    service = Serving(store)
    Scheduler(store).enqueue(item('synthetic'), time.time())
    monkeypatch.setattr(module, 'serving_for_stage', lambda stage: service)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.verify_worker] = lambda: 0
    return TestClient(app), store


def test_unconfigured_or_unauthenticated_worker_cannot_pull(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_AUDIENCE', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', raising=False)
    app = FastAPI()
    app.include_router(module.router)
    response = TestClient(app).post('/v2/batch-pipeline/pull', json={'stage': 'dev'})
    assert response.status_code == 403


def test_stage_and_capacity_required_before_claim(api):
    client, store = api
    assert (
        client.post(
            '/v2/batch-pipeline/pull', json={'stage': 'prod', 'capacity': asdict(PoolCapacity(time.time(), 1))}
        ).status_code
        == 409
    )
    assert client.post('/v2/batch-pipeline/pull', json={'stage': 'dev'}).status_code == 422
    assert store.rows['jobs', 'synthetic']['state'] == 'ready'


def test_flag_off_drains_pull_heartbeat_and_idempotent_complete(api):
    client, store = api
    pulled = client.post(
        '/v2/batch-pipeline/pull', json={'stage': 'dev', 'limit': 1, 'capacity': asdict(PoolCapacity(time.time(), 1))}
    )
    assert pulled.status_code == 200
    lease = pulled.json()['leases'][0]
    token = {'segment_id': 'synthetic', 'token': lease['token']}
    heartbeat = client.post(
        '/v2/batch-pipeline/heartbeat',
        json={'stage': 'dev', 'leases': [token, {'segment_id': 'foreign', 'token': 'stale'}]},
    )
    assert heartbeat.json() == {'accepted': ['synthetic']}
    body = {
        'stage': 'dev',
        'token': lease['token'],
        'result': {'segment_id': 'synthetic', 'result_uri': 'gs://synthetic/result', 'outcome': 'success'},
    }
    assert client.post('/v2/batch-pipeline/complete', json=body).json()['accepted']
    assert client.post('/v2/batch-pipeline/complete', json=body).json()['accepted']
    assert len([1 for table, _ in store.rows if table == 'results']) == 1
    body['token'] = 'old-token'
    assert not client.post('/v2/batch-pipeline/complete', json=body).json()['accepted']


def test_default_off_serving_startup_does_not_construct_store_or_task(monkeypatch):
    from utils.batch_pipeline import serving

    monkeypatch.delenv('BATCH_PIPELINE_SERVING_ENABLED', raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError('disabled serving touched runtime')

    monkeypatch.setattr(serving, 'serving_for_stage', forbidden)
    monkeypatch.setattr(serving, 'start_background_task', forbidden)
    assert serving.start_serving_from_env() is None


def test_rollback_reconcile_runs_cleanup_and_projection_without_cohort_check(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    cleanup, projector = Mock(), Mock()
    store = MemoryStore()
    Serving(store, cleanup=cleanup, projector=projector).reconcile()
    cleanup.assert_called_once()
    assert cleanup.call_args.args[0] is store
    projector.sweep.assert_called_once()


def test_storage_cleanup_failure_does_not_stop_projection_or_lease_recovery():
    from unittest.mock import Mock

    projector = Mock()
    cleanup = Mock(side_effect=TimeoutError('synthetic storage unavailable'))
    Serving(MemoryStore(), projector=projector, cleanup=cleanup).reconcile()
    projector.sweep.assert_called_once()


@pytest.mark.asyncio
async def test_production_pump_lazily_composes_rpc_authorization_and_completes(api, monkeypatch):
    """The exact default Pump path used by B's runtime calls the backend seal."""
    import json
    import io
    from types import SimpleNamespace
    from utils.batch_pipeline import pump as pump_module, admission
    from utils.batch_pipeline.compute_client import ComputeClient
    from utils.batch_pipeline.contracts import WorkResult
    from unittest.mock import Mock

    client, store = api
    row = store.rows['jobs', 'synthetic']
    row['requires_compute_admission'] = True
    row['projection_binding'] = {'job_id': 'bp_job', 'content_id': 'content'}
    store.rows['intakes', 'bp_job'] = {'total_audio_seconds': 30}
    monkeypatch.setattr(admission, 'reserve_backfill_speech', Mock(return_value=SimpleNamespace(allowed=True)))
    calls = []

    def send(request, timeout):
        calls.append(request.full_url)
        response = client.post('/v2/batch-pipeline/authorize-compute', json=json.loads(request.data))
        assert response.status_code == 200
        return io.BytesIO(response.content)

    transport = ComputeClient('https://synthetic.invalid', 'audience', 'dev', token=lambda: 'service-token', send=send)
    monkeypatch.setattr(pump_module, 'compute_client_from_env', lambda: transport)

    class Worker:
        calls = 0

        def process_batch(self, items):
            self.calls += 1
            return [WorkResult(item.segment_id, 'gs://synthetic/authorized-result') for item in items]

    worker = Worker()
    pump = pump_module.Pump(Scheduler(store), worker, capacity=lambda: PoolCapacity(time.time(), 1))
    assert await pump.run_once() == 1
    assert worker.calls == 1 and len(calls) == 1
    assert store.rows['jobs', 'synthetic']['state'] == 'committed'
    assert store.rows['jobs', 'synthetic']['compute_admission_token'] == store.rows['jobs', 'synthetic']['token']


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [{}, {'key': None, 'task_token': 'token'}, {'key': 'key', 'task_token': 1}])
async def test_enrichment_binding_is_validated_before_adapter_or_io(monkeypatch, payload):
    from unittest.mock import Mock

    adapter = Mock(side_effect=AssertionError('invalid request reached adapter'))
    monkeypatch.setattr(module, 'run_enrichment', adapter)
    assert (await module.enrichment_response(payload)).status_code == 400
    adapter.assert_not_called()


@pytest.mark.asyncio
async def test_landed_reprocess_runtime_fence_precedes_adapter(monkeypatch):
    from unittest.mock import Mock
    from utils.sync import reprocess

    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: False)
    adapter = Mock(side_effect=AssertionError('foreign runtime reached data'))
    monkeypatch.setattr(module, 'run_enrichment', adapter)
    response = await module.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})
    assert response.status_code == 200 and b'foreign_runtime' in response.body
    adapter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('namespace', ['batch_pipeline_dev', 'arbitrary_namespace'])
async def test_dev_reprocess_is_foreign_runtime_for_any_namespace(monkeypatch, namespace):
    from unittest.mock import Mock

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_NAMESPACE', namespace)
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    adapter = Mock(side_effect=AssertionError('dev runtime must not reach reprocess data'))
    monkeypatch.setattr(module, 'run_enrichment', adapter)

    response = await module.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})

    assert response.status_code == 200 and b'foreign_runtime' in response.body
    adapter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [('busy', 200), ('completed', 200)])
@pytest.mark.parametrize('deadline', ['false', 'true'])
async def test_landed_reprocess_response_preserves_status_and_logs_busy_without_ids(
    monkeypatch, caplog, status, code, deadline
):
    from unittest.mock import Mock
    from utils.sync import reprocess

    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', deadline)

    async def run(executor, func, *args):
        assert executor is (module.postprocess_executor if deadline == 'true' else module.sync_executor)
        return func(*args)

    monkeypatch.setattr(module, 'run_blocking', run)
    monkeypatch.setattr(module, 'run_enrichment', Mock(return_value=status))
    caplog.set_level(logging.INFO, logger=module.__name__)
    response = await module.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})
    assert response.status_code == code
    assert json.loads(response.body) == {'status': status}
    if status == 'busy':
        messages = [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]
        assert messages == ['event=batch_enrichment_sync_reprocess outcome=busy']


@pytest.mark.asyncio
async def test_summary_runs_while_transcription_executor_is_full(monkeypatch):
    from utils.sync import reprocess

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(module, 'run_enrichment', lambda *_: 'processed')
    release = threading.Event()
    # Run the real adapter and executors; a route-level mock hides this wait.
    with ThreadPoolExecutor(max_workers=1) as transcription:
        transcription.submit(release.wait)
        monkeypatch.setattr(module, 'sync_executor', transcription)
        try:
            response = await asyncio.wait_for(
                module.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32}),
                timeout=2,
            )
            assert response.status_code == 200
            assert json.loads(response.body) == {'status': 'processed'}
        finally:
            release.set()


def test_historical_dead_redrive_is_authenticated_stage_bound_and_idempotent(api, monkeypatch):
    client, store = api
    Scheduler(store).pull(time.time())
    store.rows['jobs', 'synthetic'].update(state='dead', token='', lease_until=0)
    path = '/v2/batch-pipeline/redrive-dead'
    assert client.post(path, json={'stage': 'prod', 'segment_id': 'synthetic'}).status_code == 409
    assert client.post(path, json={'stage': 'dev', 'segment_id': 'synthetic'}).json() == {'accepted': True}
    assert client.post(path, json={'stage': 'dev', 'segment_id': 'synthetic'}).json() == {'accepted': False}
    assert store.rows['jobs', 'synthetic']['merge_pending']
    app = FastAPI()
    app.include_router(module.router)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_AUDIENCE', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', raising=False)
    assert TestClient(app).post(path, json={'stage': 'dev', 'segment_id': 'synthetic'}).status_code == 403


def test_held_partial_scan_runs_on_a_slow_cadence_behind_its_kill_switch(monkeypatch):
    projector = Mock()
    service = Serving(MemoryStore(), projector=projector)
    service.reconcile()
    service.reconcile()
    projector.sweep_held.assert_called_once()
    service.held_partial_due = 0.0
    monkeypatch.setenv('BATCH_PIPELINE_HELD_PARTIAL_ENABLED', 'false')
    service.reconcile()
    projector.sweep_held.assert_called_once()
    monkeypatch.delenv('BATCH_PIPELINE_HELD_PARTIAL_ENABLED')
    projector.sweep_held.side_effect = TimeoutError('synthetic held scan failure')
    service.reconcile()
    # A failed scan never stops lease recovery or the projection sweep.
    assert projector.sweep_held.call_count == 2 and projector.sweep.call_count == 4
    # Projectors without the scan (the pipeline simulator's model) are skipped.
    Serving(MemoryStore(), projector=SimpleNamespace(sweep=lambda: None)).reconcile()


def test_budget_stopped_held_pass_resumes_next_tick_and_carries_its_bounds(monkeypatch):
    from utils.batch_pipeline import serving as serving_module

    clock = {'monotonic': 10_000.0}
    monkeypatch.setattr(
        serving_module, 'time', SimpleNamespace(monotonic=lambda: clock['monotonic'], time=lambda: 1_000_000.0)
    )
    results = [
        {'partial': 0, 'waiting': 32, 'error': 0, 'units': 32, 'more': 1},
        {'partial': 3, 'waiting': 2, 'error': 0, 'units': 5, 'more': 0},
    ]
    projector = Mock()
    projector.sweep_held = Mock(side_effect=results)
    service = Serving(MemoryStore(), projector=projector)
    service.reconcile()
    call = projector.sweep_held.call_args
    assert call.kwargs['deadline'] - clock['monotonic'] == serving_module.HELD_PARTIAL_TICK_SECONDS
    assert call.kwargs['max_pages'] == (
        serving_module.HELD_PARTIAL_READS_PER_HOUR // (32 * serving_module.HELD_PARTIAL_READS_PER_UNIT)
    )
    # A pass stopped mid-backlog does not wait out the interval.
    assert service.held_partial_due == clock['monotonic']
    clock['monotonic'] += 1
    service.reconcile()
    assert projector.sweep_held.call_count == 2
    # A short page ends the pass and re-arms the slow interval.
    assert service.held_partial_due == clock['monotonic'] + serving_module.HELD_PARTIAL_INTERVAL_SECONDS
    assert service.held_partial_reads == [
        (10_000.0, 32 * serving_module.HELD_PARTIAL_READS_PER_UNIT),
        (10_001.0, 5 * serving_module.HELD_PARTIAL_READS_PER_UNIT),
    ]


def test_held_partial_kill_switch_stops_even_a_resuming_pass(monkeypatch):
    projector = Mock()
    projector.sweep_held = Mock(return_value={'partial': 0, 'waiting': 4, 'error': 0, 'units': 4, 'more': 1})
    service = Serving(MemoryStore(), projector=projector)
    service.reconcile()
    assert projector.sweep_held.call_count == 1 and service.held_partial_due <= time.monotonic()
    monkeypatch.setenv('BATCH_PIPELINE_HELD_PARTIAL_ENABLED', 'false')
    service.reconcile()
    assert projector.sweep_held.call_count == 1


def test_held_partial_governor_charges_the_sweeps_exact_reads(monkeypatch):
    from utils.batch_pipeline import serving as serving_module

    clock = {'monotonic': 20_000.0}
    monkeypatch.setattr(
        serving_module, 'time', SimpleNamespace(monotonic=lambda: clock['monotonic'], time=lambda: 1_000_000.0)
    )
    projector = Mock()
    projector.sweep_held = Mock(
        return_value={'partial': 2, 'waiting': 0, 'error': 0, 'units': 32, 'reads': 500, 'more': 0}
    )
    service = Serving(MemoryStore(), projector=projector)
    service.reconcile()
    # A sweep that reports its own reads (sibling-heavy uploads cost more than
    # the per-unit estimate) is charged exactly what it reported.
    assert projector.sweep_held.call_count == 1
    assert service.held_partial_reads == [(20_000.0, 500)]


def test_held_partial_read_governor_defers_the_sweep_until_the_window_refills(monkeypatch):
    from utils.batch_pipeline import serving as serving_module

    clock = {'monotonic': 50_000.0}
    monkeypatch.setattr(
        serving_module, 'time', SimpleNamespace(monotonic=lambda: clock['monotonic'], time=lambda: 1_000_000.0)
    )
    projector = Mock()
    projector.sweep_held = Mock(return_value={'partial': 0, 'waiting': 0, 'error': 0, 'units': 0, 'more': 0})
    service = Serving(MemoryStore(), projector=projector)
    service.held_partial_reads = [(clock['monotonic'], serving_module.HELD_PARTIAL_READS_PER_HOUR)]
    service.reconcile()
    service.reconcile()
    # The hourly window is spent: no sweep, and the gate retries for free.
    assert projector.sweep_held.call_count == 0 and service.held_partial_due == clock['monotonic']
    clock['monotonic'] += serving_module.HELD_PARTIAL_WINDOW_SECONDS
    service.reconcile()
    assert projector.sweep_held.call_count == 1


def test_recovery_is_scheduled_inside_service_but_metrics_reconcile_does_not_dispatch():
    from unittest.mock import Mock

    recovery = Mock()
    service = Serving(MemoryStore(), recovery=recovery)
    service.reconcile()
    recovery.sweep.assert_not_called()
    service.reconcile(recover_quarantine=True)
    recovery.sweep.assert_called_once()


def test_reconcile_entry_point_requires_existing_worker_oidc(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_AUDIENCE', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', raising=False)
    app = FastAPI()
    app.include_router(module.router)
    response = TestClient(app).post('/v2/batch-pipeline/reconcile', json={'stage': 'dev'})
    assert response.status_code == 403


@pytest.mark.parametrize('enabled', [False, True])
def test_reconcile_and_metrics_routes_share_flagged_async_coordinator(api, monkeypatch, enabled):
    from unittest.mock import Mock, AsyncMock

    client, _ = api
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', str(enabled).lower())
    service = module.serving_for_stage('dev')
    service.projector = Mock(has_async_followups=enabled)
    service.projector.start_followups = AsyncMock()
    service.recovery = Mock()
    response = client.post('/v2/batch-pipeline/reconcile', json={'stage': 'dev'})
    assert response.status_code == 200 and response.json() == {'status': 'reconciled'}
    assert client.get('/v2/batch-pipeline/metrics').status_code == 200
    assert service.projector.sweep.call_count == 2
    assert service.projector.start_followups.await_count == (2 if enabled else 0)
    service.recovery.sweep.assert_called_once()


def test_read_only_metrics_serves_fresh_gauges_while_drain_is_blocked(api, monkeypatch):
    client, store = api
    monkeypatch.setenv('BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'true')
    entered, release = threading.Event(), threading.Event()

    def blocked_enrichment():
        entered.set()
        assert release.wait(5)

    enrichment = Mock(side_effect=blocked_enrichment)
    gauges = QueueMetrics(registry=CollectorRegistry())
    service = Serving(store, metrics=gauges, enrichment_sweep=enrichment)
    monkeypatch.setattr(module, 'serving_for_stage', lambda stage: service)
    initial = deepcopy(store.rows)
    drain = threading.Thread(target=service.reconcile)
    drain.start()
    try:
        assert entered.wait(2)
        response = client.get('/v2/batch-pipeline/metrics')
        assert response.status_code == 200
        assert gauges.refreshed_at.labels(*gauges.scope)._value.get() > 0
        assert gauges.ready_age.labels('fresh', *gauges.scope)._value.get() >= 0
        assert enrichment.call_count == 1
        assert store.rows == initial
    finally:
        release.set()
        drain.join(timeout=2)
    assert not drain.is_alive()


@pytest.mark.parametrize('scrape_flag,serving_flag', [(None, 'true'), ('true', 'false')])
def test_metrics_retains_legacy_drain_until_both_controls_are_on(api, monkeypatch, scrape_flag, serving_flag):
    client, store = api
    monkeypatch.delenv('BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED', raising=False)
    if scrape_flag is not None:
        monkeypatch.setenv('BATCH_PIPELINE_READ_ONLY_METRICS_ENABLED', scrape_flag)
    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', serving_flag)
    from unittest.mock import AsyncMock

    service = Mock(store=store)
    service.reconcile_async = AsyncMock()
    monkeypatch.setattr(module, 'serving_for_stage', lambda stage: service)
    assert client.get('/v2/batch-pipeline/metrics').status_code == 200
    service.reconcile_async.assert_awaited_once_with(periodic=True)
    service.metrics.refresh.assert_not_called()


@pytest.mark.asyncio
async def test_recovery_request_awaits_paid_intent_before_response_and_projection(api, monkeypatch):
    import asyncio
    from routers import batch_pipeline as routes

    _, store = api
    service = routes.serving_for_stage('dev')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    entered, release = asyncio.Event(), asyncio.Event()

    async def recover(segment, owner):
        entered.set()
        await release.wait()
        return 'recovered'

    service.recovery = Mock()
    from unittest.mock import AsyncMock

    service.recovery.recover_async = AsyncMock(side_effect=recover)
    service.reconcile_async = AsyncMock()
    task = asyncio.create_task(
        routes.recover_quarantine(
            routes.RedriveRequest(stage='dev', segment_id='synthetic'), SimpleNamespace(headers={})
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert not task.done()  # The request stays active during the provider call.
        service.reconcile_async.assert_not_awaited()
    finally:
        release.set()
    assert await task == {'status': 'recovered'}
    service.reconcile_async.assert_awaited_once_with(
        owner_id=store.rows['jobs', 'synthetic']['owner_id'], recovered='synthetic'
    )
    assert service.recovery.recover_async.await_args.args == ('synthetic', store.rows['jobs', 'synthetic']['owner_id'])
    service.recovery.recover.assert_not_called()


def test_recovery_task_rejects_foreign_stage_and_missing_oidc(api, monkeypatch):
    client, _ = api
    path = '/v2/batch-pipeline/recover-quarantine'
    assert client.post(path, json={'stage': 'prod', 'segment_id': 'synthetic'}).status_code == 409
    monkeypatch.delenv('BATCH_PIPELINE_WORKER_AUDIENCE', raising=False)
    app = FastAPI()
    app.include_router(module.router)
    assert TestClient(app).post(path, json={'stage': 'dev', 'segment_id': 'synthetic'}).status_code == 403


@pytest.mark.parametrize(
    'path,expected', [('/v2/batch-pipeline/recover-quarantine', 'tasks-sa'), ('/v2/batch-pipeline/pull', 'worker-sa')]
)
def test_recovery_invoker_cannot_gain_worker_authority(monkeypatch, path, expected):
    from starlette.requests import Request
    from utils import cloud_tasks

    monkeypatch.setenv('BATCH_PIPELINE_WORKER_AUDIENCE', 'https://worker.run.app')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', 'https://integration.run.app')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', 'worker-sa')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'tasks-sa')
    verify = Mock(return_value=0)
    monkeypatch.setattr(cloud_tasks, 'verify_configured_cloud_tasks_oidc', verify)
    module.verify_worker(Request({'type': 'http', 'path': path, 'headers': []}))
    assert verify.call_args.kwargs['invoker_sa'] == expected
    assert verify.call_args.kwargs['audience'] == (
        'https://integration.run.app' if expected == 'tasks-sa' else 'https://worker.run.app'
    )


@pytest.mark.asyncio
async def test_real_adapter_logs_closed_class_site_without_exception_text(monkeypatch, caplog):
    from utils.sync import reprocess

    adapter = module
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)

    async def run(*_):
        raise reprocess.FirstSummaryCallbackPending('DO-NOT-LOG synthetic payload')

    monkeypatch.setattr(adapter, 'run_blocking', run)
    caplog.set_level(logging.WARNING, logger=adapter.__name__)
    response = await adapter.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})
    assert response.status_code == 409
    assert json.loads(response.body) == {'status': 'retry', 'reason': 'callback_pending'}
    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        'event=batch_enrichment_sync_reprocess outcome=retry retry_class=callback_pending site=run_enrichment '
        'exception_type=FirstSummaryCallbackPending'
    ]


def _retry_count(reason):
    return module.ENRICHMENT_RETRIES.labels(reason)._value.get()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['callback_pending', 'persistence_fenced', 'fenced_subclass', 'unexpected'])
async def test_expected_enrichment_retries_are_409_and_unexpected_stay_500(monkeypatch, caplog, kind):
    from utils.sync import reprocess

    # Importing the real sync pipeline costs seconds; the identity check below
    # pins its defining module and name instead.
    SyncConversationPersistenceFenced = type(
        'SyncConversationPersistenceFenced', (RuntimeError,), {'__module__': 'utils.sync.pipeline'}
    )

    class StaleSnapshot(SyncConversationPersistenceFenced):
        pass

    error, code, reason = {
        'callback_pending': (reprocess.FirstSummaryCallbackPending('x'), 409, 'callback_pending'),
        'persistence_fenced': (SyncConversationPersistenceFenced('x'), 409, 'persistence_fenced'),
        'fenced_subclass': (StaleSnapshot('x'), 409, 'persistence_fenced'),
        # Same class name from another module is not a deliberate retry.
        'unexpected': (type('FirstSummaryCallbackPending', (RuntimeError,), {})('x'), 500, 'unexpected'),
    }[kind]
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)

    async def run(*_):
        raise error

    monkeypatch.setattr(module, 'run_blocking', run)
    before = _retry_count(reason)
    caplog.set_level(logging.WARNING, logger=module.__name__)
    response = await module.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})
    # Never 429/503: those throttle the whole Cloud Tasks queue.
    assert response.status_code == code
    assert json.loads(response.body)['status'] == 'retry'
    assert _retry_count(reason) == before + 1
    [record] = [record for record in caplog.records if record.name == module.__name__]
    assert f'retry_class={reason} ' in record.getMessage()
    assert record.levelno == (logging.ERROR if code == 500 else logging.WARNING)


def test_first_summary_callback_pending_from_its_defining_module_is_an_expected_retry():
    # #22431 moved the class to utils.enrichment.outbox; a key on the old module path turned the
    # expected retry back into a fast 500 (the Cloud Tasks stall pattern of 10-18 and 10-19).
    from utils.enrichment.outbox import FirstSummaryCallbackPending
    from utils.sync import reprocess

    assert module.expected_retry_reason(FirstSummaryCallbackPending('x')) == 'callback_pending'
    assert module.expected_retry_reason(reprocess.FirstSummaryCallbackPending('x')) == 'callback_pending'


def test_expected_retry_classes_are_defined_where_the_router_matches_them():
    import ast
    from pathlib import Path

    backend = Path(module.__file__).resolve().parents[1]
    for (module_name, class_name), _ in module.EXPECTED_RETRIES.items():
        tree = ast.parse((backend / (module_name.replace('.', '/') + '.py')).read_text())
        assert class_name in {node.name for node in tree.body if isinstance(node, ast.ClassDef)}


def test_periodic_maintenance_runs_on_one_serving_instance_per_lease():
    from utils.batch_pipeline.leader import SERVING_MAINTENANCE, LeaderLease

    store = MemoryStore()
    instances = []
    for _ in range(2):
        instance = Serving(
            store,
            projector=Mock(),
            cleanup=Mock(),
            enrichment_sweep=Mock(),
            recovery=Mock(),
            metrics=Mock(),
            leader=LeaderLease(store, SERVING_MAINTENANCE, ttl_seconds=60),
        )
        instances.append(instance)
    for instance in instances:
        instance.reconcile(recover_quarantine=True, periodic=True)
    leader, follower = instances
    for maintenance in ('cleanup', 'enrichment_sweep'):
        assert getattr(leader, maintenance).call_count == 1
        assert getattr(follower, maintenance).call_count == 0
    leader.recovery.sweep.assert_called_once()
    follower.recovery.sweep.assert_not_called()
    # Projection throughput and each instance's own gauges are not leader-gated.
    for instance in instances:
        instance.projector.sweep.assert_called_once()
        instance.metrics.refresh.assert_called_once()
    # Explicit RPC reconcile always runs, lease or not.
    follower.reconcile(recover_quarantine=True)
    follower.recovery.sweep.assert_called_once()
    follower.cleanup.assert_called_once()


def test_recovery_dispatch_tick_runs_only_recovery_on_the_maintenance_leader():
    from utils.batch_pipeline.leader import SERVING_MAINTENANCE, LeaderLease

    store = MemoryStore()
    leader, follower = (
        Serving(
            store,
            projector=Mock(),
            cleanup=Mock(),
            recovery=Mock(),
            leader=LeaderLease(store, SERVING_MAINTENANCE, ttl_seconds=60),
        )
        for _ in range(2)
    )
    leader.recovery.sweep.return_value = {'queued': 1}
    assert leader.dispatch_recovery() == {'queued': 1}
    assert follower.dispatch_recovery() is None
    follower.recovery.sweep.assert_not_called()
    for instance in (leader, follower):
        instance.cleanup.assert_not_called()
        instance.projector.sweep.assert_not_called()
    assert Serving(store).dispatch_recovery() is None  # No recovery configured.


@pytest.mark.asyncio
@pytest.mark.parametrize('interval,dispatches', [('1', True), ('off', False)])
async def test_serving_runtime_dispatches_recovery_beside_the_serving_pass(monkeypatch, interval, dispatches):
    from utils.batch_pipeline import serving

    monkeypatch.setenv('BATCH_PIPELINE_SERVING_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_INTERVAL_SECONDS', interval)
    passes = asyncio.Event()

    async def reconcile_async(**kwargs):
        passes.set()

    service = SimpleNamespace(store=Mock(), reconcile_async=reconcile_async, dispatch_recovery=Mock())

    async def drain_recordings(store):
        return None

    monkeypatch.setattr(serving, 'current_stage', lambda: 'prod')
    monkeypatch.setattr(serving, 'serving_for_stage', lambda stage: service)
    monkeypatch.setattr(serving, 'drain_recordings', drain_recordings)
    runtime = serving.start_serving_from_env()
    await asyncio.wait_for(passes.wait(), timeout=5)
    for _ in range(50):
        if service.dispatch_recovery.called or not dispatches:
            break
        await asyncio.sleep(0.01)
    await serving.stop_serving(runtime)
    assert service.dispatch_recovery.called is dispatches
    assert runtime[1].done()


def test_serving_maintenance_fails_open_when_lease_store_errors():
    from utils.batch_pipeline.leader import SERVING_MAINTENANCE, LeaderLease

    broken = Mock()
    broken.run.side_effect = RuntimeError('lease store down')
    store = MemoryStore()
    service = Serving(store, cleanup=Mock(), leader=LeaderLease(broken, SERVING_MAINTENANCE, ttl_seconds=60))
    service.reconcile(periodic=True)
    service.cleanup.assert_called_once()
