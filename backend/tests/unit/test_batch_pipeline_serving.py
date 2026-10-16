"""Private pull/complete RPC enforces identity and stage while admission is off."""

from dataclasses import asdict
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from routers import batch_pipeline as module
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import PoolCapacity
from utils.batch_pipeline.serving import Serving
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
@pytest.mark.parametrize('status,code', [('busy', 503), ('completed', 200)])
async def test_landed_reprocess_busy_response_remains_retryable(monkeypatch, status, code):
    from unittest.mock import Mock
    from utils.sync import reprocess

    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(module, 'run_enrichment', Mock(return_value=status))
    response = await module.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})
    assert response.status_code == code


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
