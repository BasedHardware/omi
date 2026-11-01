"""Exercise the real GPU coordinator, idle priority, and private HTTP boundary."""

import asyncio
import threading
import io
import json
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from diarizer import batch_pipeline
from tests.unit.test_batch_pipeline_worker import setup_worker, item
from tests.unit.test_batch_pipeline_shadow import repository, running, row  # noqa: F401
from utils.batch_pipeline.artifacts import ArtifactStore
from utils.batch_pipeline.contracts import RecoveryWork, WorkResult, PoolCapacity, WorkItem, FailedWork
from utils.batch_pipeline.shadow_worker import ShadowRunner
from routers import batch_pipeline as router
from utils.batch_pipeline import artifact_policy, shadow_recovery
from utils.batch_pipeline import retention, shadow_intake
from utils.batch_pipeline import compute_client
from utils import cloud_tasks
from utils.batch_pipeline.artifact_policy import create_artifact_store
from tests.unit.test_batch_pipeline_artifacts import ObjectClient
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.pump import Pump


async def run_shadow(runner, pump):
    return await runner.run_once(pump, capacity=PoolCapacity(time.time(), available_slots=1))


async def test_generic_failed_shadow_keeps_measured_error_without_new_paid_call(repository):
    work = running(repository)
    repository.take = lambda _: work
    recovery = Mock(side_effect=AssertionError('opaque model errors must not authorize paid calls'))
    runner = ShadowRunner(repository, recovery)
    worker = Mock()
    worker.process_batch.return_value = [FailedWork(work.segment_id, 2)]
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=worker)
    assert await run_shadow(runner, pump) == 1
    result = row(repository, work.segment_id)
    assert result['outcome'] == 'error' and result['vad'] == 'worker'
    assert result['speech_seconds'] == result['speech_loss_seconds'] == 2
    recovery.assert_not_called()


@pytest.mark.parametrize('restriction', ['zero_slots', 'fresh_reserved', 'stale', 'shared_live', 'oversized'])
async def test_shadow_obeys_the_same_capacity_snapshot_as_normal_pull(repository, restriction):
    runner = ShadowRunner(repository, Mock())
    runner.worker_id = 'worker-capacity'
    repository.offer(runner.worker_id)
    reservation = repository.reserve('synthetic-owner', 'capacity-unit', 'deep')
    work = WorkItem(reservation[0], 'synthetic-owner', 1, 'synthetic:audio', 300, 2, shadow=True, privacy_generation=0)
    assert repository.ready(reservation, work, '')
    fields = {'observed_at': time.time(), 'available_slots': 1}
    fields.update(
        {
            'zero_slots': {'available_slots': 0},
            'fresh_reserved': {'reserved_fresh_slots': 1},
            'stale': {'observed_at': time.time() - 30},
            'shared_live': {'shared_with_live': True, 'gpu_id': 'synthetic-gpu', 'memory_headroom_bytes': 8 * 1024**3},
            'oversized': {'max_item_seconds': 120},
        }[restriction]
    )
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=Mock())
    assert await runner.run_once(pump, capacity=PoolCapacity(**fields)) == 0
    pump.worker.process_batch.assert_not_called()
    assert row(repository, work.segment_id)['outcome'] == 'dropped'


async def test_runner_uses_full_worker_but_never_normal_publication(repository, monkeypatch):
    work = running(repository)
    # running() consumed the offer; restore a new ready unit for this runner.
    runner = ShadowRunner(repository, Mock(side_effect=AssertionError('no recovery for words')))
    runner.worker_id = 'worker-actual'
    repository.offer(runner.worker_id)
    reservation = repository.reserve('synthetic-owner', 'actual', 'deep')
    work = replace(work, segment_id=reservation[0], duration_seconds=2)
    assert repository.ready(reservation, work, '')

    from utils.batch_pipeline.artifact_policy import shadow_result

    artifacts = ArtifactStore(
        Mock(),
        bucket='synthetic-bucket',
        namespace='batch_pipeline_dev',
        authorize=Mock(),
        key_for_owner=Mock(),
        register_artifact=Mock(),
        shadow_result=lambda work, payload: shadow_result(
            repository.store, work, payload, projection=lambda *args: {'status': 'planned'}
        ),
    )
    worker, words, _, decoded, diarized, failures = setup_worker(persist=artifacts.persist_result)
    monkeypatch.setattr(batch_pipeline, 'cap_dispatch_enabled', Mock(side_effect=AssertionError('no user quota')))
    monkeypatch.setattr(batch_pipeline, 'record_audio', Mock(side_effect=AssertionError('no user usage')))
    normal_store = MemoryStore()
    pump = Pump(
        Scheduler(normal_store), worker, shadow=runner, capacity=lambda: PoolCapacity(time.time(), available_slots=1)
    )
    pump._publish_flight = AsyncMock(side_effect=AssertionError('shadow cannot enter normal publication'))
    assert await pump.run_once(maintain=False) == 1
    assert words.calls and decoded and diarized and not failures
    assert row(repository, work.segment_id)['outcome'] == 'recovered'
    assert row(repository, work.segment_id)['paid_providers'] == []
    assert all(path[0].startswith('batch_pipeline_dev_shadow_') for path in repository.store.client.rows)
    artifacts.register_artifact.assert_not_called()
    pump._publish_flight.assert_not_awaited()
    assert not any(table == 'jobs' for table, _ in normal_store.rows)


async def test_runner_does_not_wait_behind_live_gpu_or_claimed_flight(repository):
    runner = ShadowRunner(repository, Mock())
    lock = asyncio.Lock()
    await lock.acquire()
    pump = SimpleNamespace(_gpu=lock, _normal_flights=0, worker=Mock())
    repository.take = Mock(side_effect=AssertionError('must not take behind live GPU'))
    assert await run_shadow(runner, pump) == 0
    lock.release()
    pump._normal_flights = 1
    assert await run_shadow(runner, pump) == 0
    repository.take.assert_not_called()


async def test_live_claim_during_take_drops_before_gpu_dispatch(repository):
    work = running(repository)
    runner = ShadowRunner(repository, Mock())
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=Mock())

    def take(_):
        pump._normal_flights = 1
        return work

    repository.take = take
    assert await run_shadow(runner, pump) == 0
    pump.worker.process_batch.assert_not_called()
    assert row(repository, work.segment_id)['outcome'] == 'dropped'


async def test_missing_gpu_result_never_starts_paid_recovery(repository):
    work = running(repository)
    repository.take = lambda _: work
    recovery = Mock()
    runner = ShadowRunner(repository, recovery)
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=Mock(process_batch=Mock(return_value=[])))
    assert await run_shadow(runner, pump) == 1
    recovery.assert_not_called()
    assert row(repository, work.segment_id)['outcome'] == 'error'


async def test_busy_probe_failure_settles_taken_work_immediately(repository):
    work = running(repository)
    repository.take = lambda _: work
    repository.busy = Mock(side_effect=TimeoutError('synthetic probe timeout'))
    runner = ShadowRunner(repository, Mock())
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=Mock())
    assert await run_shadow(runner, pump) == 0
    pump.worker.process_batch.assert_not_called()
    assert row(repository, work.segment_id)['outcome'] == 'dropped'


async def test_late_take_reply_is_dropped_without_leaving_raw_owner(repository):
    work = running(repository)
    runner = ShadowRunner(repository, Mock())
    runner.worker_id = 'worker-late'
    repository.offer(runner.worker_id)
    reservation = repository.reserve(work.owner_id, 'late-take', 'deep')
    work = replace(work, segment_id=reservation[0])
    assert repository.ready(reservation, work, '')
    take, release = repository.take, threading.Event()

    def delayed(worker):
        result = take(worker)
        release.wait(3)
        return result

    repository.take = delayed
    pump = SimpleNamespace(_gpu=asyncio.Lock(), _normal_flights=0, worker=Mock())
    try:
        assert await run_shadow(runner, pump) == 0
        assert row(repository, work.segment_id)['state'] == 'running'
    finally:
        release.set()
    for _ in range(100):
        if row(repository, work.segment_id).get('state') == 'settled':
            break
        await asyncio.sleep(0.01)
    assert row(repository, work.segment_id)['outcome'] == 'dropped'
    assert 'item' not in row(repository, work.segment_id)
    pump.worker.process_batch.assert_not_called()


def test_empty_gpu_worker_hands_off_to_shadow_recovery(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    worker, _, _, _, _, _ = setup_worker(recover_words=lambda *args: [])
    worker.words.transcribe_batch = lambda samples: [[] for _ in samples]
    result = worker.process_batch([replace(item(), shadow=True)])
    assert len(result) == 1 and isinstance(result[0], RecoveryWork)


def test_shadow_empty_asr_cannot_increment_live_fallback_metrics(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    fallback = Mock()
    monkeypatch.setattr(batch_pipeline, 'record_fallback', fallback)
    worker, _, _, _, _, _ = setup_worker(recover_words=lambda *args: [])
    worker.words.transcribe_batch = lambda samples: [[] for _ in samples]
    worker.process_batch([replace(item(), shadow=True)])
    fallback.assert_not_called()


async def test_disabled_upload_and_byok_have_no_io(monkeypatch):
    from utils.batch_pipeline import shadow_intake

    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '0')
    factory = Mock(side_effect=AssertionError('disabled shadow must do no IO'))
    monkeypatch.setattr(shadow_intake, 'FirestoreStore', factory)
    kwargs = dict(
        uid='synthetic',
        content_id='content',
        paths=['never-read'],
        lane='fresh',
        age=0,
        conversation_id=None,
        source='omi',
        device_id=None,
        byok=False,
        policy=SimpleNamespace(batch_enabled=False),
    )
    await shadow_intake.offer_upload(**kwargs)
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    await shadow_intake.offer_upload(**{**kwargs, 'byok': True})
    factory.assert_not_called()


def test_private_http_recovery_writes_only_shadow_state(repository, monkeypatch):
    from utils.batch_pipeline.recovery_recognizers import words_payload
    from utils.batch_pipeline import projection
    from utils.sync import assignment

    monkeypatch.setattr(projection, 'cap_dispatch_enabled', lambda *args: False)
    monkeypatch.setattr(assignment, 'smart_merge_flatten_enabled', lambda: False)
    monkeypatch.setattr(assignment, 'sync_lineage_resolve_enabled', lambda: False)
    work = running(repository, duration=20)
    monkeypatch.setattr(router.WorkerRequest, 'service', lambda self: SimpleNamespace(store=repository.store))
    monkeypatch.setattr(artifact_policy, 'artifacts_for', lambda _: SimpleNamespace(fetch_audio=lambda _: b'audio'))
    original = shadow_recovery.recover_async
    spans = [{'start': 0, 'end': 2}]
    provider = Mock(
        return_value=words_payload(20, spans, [{'word': 'Synthetic', 'timestamp': [0, 1], 'speaker': '0'}], 'en')
    )
    monkeypatch.setattr(
        shadow_recovery,
        'recover_async',
        lambda repo, artifacts, segment: original(
            repo,
            artifacts,
            segment,
            stt=provider,
            inspect=lambda *a: (b'', 20, spans),
        ),
    )
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.verify_worker] = lambda: 1
    app.dependency_overrides[router.require_http_stage] = lambda: None
    with TestClient(app) as client:
        response = client.post(
            '/v2/batch-pipeline/shadow-recover', json={'stage': 'dev', 'segment_id': work.segment_id}
        )
        assert response.status_code == 200
        assert response.json() == {'status': 'recovered'}
        assert client.post(
            '/v2/batch-pipeline/shadow-recover', json={'stage': 'dev', 'segment_id': work.segment_id}
        ).json() == {'status': 'held'}
    assert provider.call_count == 1
    assert row(repository, work.segment_id)['projection_status'] == 'planned'
    assert all(path[0].startswith('batch_pipeline_dev_shadow_') for path in repository.store.client.rows)
    assert 'private transcript' not in repr(repository.store.client.rows)


def test_shadow_client_uses_existing_recovery_role_and_oidc_audience(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_RECOVERY_API_URL', 'https://recovery.invalid')
    monkeypatch.setenv('BATCH_PIPELINE_API_URL', 'https://admission.invalid')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    token = Mock(return_value='synthetic-token')
    monkeypatch.setattr(compute_client, 'fetch_id_token', token)
    client = compute_client.shadow_from_env()
    client._send = Mock(return_value=io.BytesIO(b'{"status":"failed_held"}'))
    assert client.shadow_recover('sh_unit') == {'status': 'failed_held'}
    request = client._send.call_args.args[0]
    assert request.full_url == 'https://recovery.invalid/v2/batch-pipeline/shadow-recover'
    assert json.loads(request.data) == {'stage': 'dev', 'segment_id': 'sh_unit'}
    assert token.call_args.args[1] == 'https://recovery.invalid'


@pytest.mark.parametrize('path', ['shadow-recover', 'shadow-project'])
def test_shadow_endpoint_uses_recovery_audience_with_gpu_principal(monkeypatch, path):
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', 'https://recovery.invalid')
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', 'synthetic-worker@example.invalid')
    verify = Mock(return_value=1)
    monkeypatch.setattr(cloud_tasks, 'verify_configured_cloud_tasks_oidc', verify)
    assert router.verify_worker(SimpleNamespace(url=SimpleNamespace(path='/v2/batch-pipeline/' + path))) == 1
    assert verify.call_args.kwargs['audience'] == 'https://recovery.invalid'
    assert verify.call_args.kwargs['invoker_sa'] == 'synthetic-worker@example.invalid'


def test_private_projection_runs_real_planner_and_only_writes_shadow_metadata(repository, monkeypatch):
    from utils.batch_pipeline import shadow_projection
    from tests.unit.test_batch_pipeline_shadow_projection import payload

    work = running(repository, duration=10)
    repository.store.run(
        lambda tx: tx.put(
            'shadow_jobs', work.segment_id, {**tx.get('shadow_jobs', work.segment_id), 'state': 'running'}
        )
    )
    monkeypatch.setattr(router.WorkerRequest, 'service', lambda self: SimpleNamespace(store=repository.store))
    actual = shadow_projection.plan
    # The network read adapter is separate: execute the real builder/assignment
    # here against an empty synthetic snapshot without a customer SDK reference.
    monkeypatch.setattr(
        shadow_projection,
        'plan',
        lambda work, data, context, reader, **kwargs: actual(
            work, data, context, lambda *args: None, decode=lambda raw: raw
        ),
    )
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.verify_worker] = lambda: 1
    app.dependency_overrides[router.require_http_stage] = lambda: None
    before = deepcopy(repository.store.client.rows)
    with TestClient(app) as client:
        body = {'stage': 'dev', 'segment_id': work.segment_id, 'payload': payload()}
        result = client.post('/v2/batch-pipeline/shadow-project', json=body)
        assert result.status_code == 200 and result.json()['status'] == 'planned'
        assert client.post('/v2/batch-pipeline/shadow-project', json=body).json() == {'status': 'not_eligible'}
    changed = {path for path, data in repository.store.client.rows.items() if before.get(path) != data}
    assert changed and all(
        path[0] in {'batch_pipeline_dev_shadow_jobs', 'batch_pipeline_dev_shadow_spend'} for path in changed
    )
    assert 'A useful synthetic sentence.' not in repr(repository.store.client.rows)


@pytest.mark.parametrize(
    'language_mode',
    [
        'declared',
        'conversation_inherited',
        'user_inherited',
        'audio_lid',
        'self_lid',
        'unavailable',
        'funding_denied',
        'funding_denied_outside_execution',
        'consent_denied',
        'privacy_revoked',
        'privacy_between_probes',
    ],
)
async def test_real_decode_encrypted_staging_preserves_legacy_files(repository, monkeypatch, tmp_path, language_mode):
    from diarizer.batch_pipeline_models import StagedAudio
    from utils.batch_pipeline.audio import read_context
    from utils.stt import batch_language
    from utils import stt_cap_dispatch
    from utils import funded_processing
    from config import stt_cap_dispatch as cap_config
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    original = Path(pcm(tmp_path, 1750000100, samples=16000))
    original_bytes = original.read_bytes()
    directory, copies = shadow_intake.copy_paths([str(original)])

    denied = language_mode.startswith('funding_denied') or language_mode == 'consent_denied'
    inherited = language_mode in {'conversation_inherited', 'user_inherited'}
    conversation_id = 'synthetic-conversation' if language_mode == 'conversation_inherited' else None
    phase = {'revoked': False}
    probes = []

    def privacy(*args, **kwargs):
        if phase['revoked']:
            raise BatchPrivacyBlocked('synthetic privacy revoked')
        if kwargs.get('snapshots') is not None:
            kwargs['snapshots'].update(
                user={
                    'language': 'en',
                    'transcription_preferences': {
                        'single_language_mode': language_mode in {'declared', 'conversation_inherited'}
                    },
                },
                conversations={conversation_id: {'language': 'fr'}} if conversation_id else {},
            )
        return 0

    actual_resolver = batch_language.resolve_language
    inputs = []

    def resolve(language, audio, *, before_probe, before_self_probe, **kwargs):
        inputs.append(language)
        if language_mode == 'declared' or inherited:
            return actual_resolver(
                language, audio, before_probe=before_probe, before_self_probe=before_self_probe, **kwargs
            )
        assert language == 'multi'  # With inheritance off, primary language is not proof.
        if language_mode == 'privacy_revoked':
            phase['revoked'] = True
        assert before_self_probe() is (not denied)
        if not denied:
            probes.append('self')
        if language_mode == 'privacy_between_probes':
            phase['revoked'] = True
        assert before_probe() is (not denied)
        if not denied:
            probes.append('vendor')
        if language_mode == 'unavailable' or denied:
            return batch_language.LanguageDecision('und', 0.0, 'unavailable')
        return batch_language.LanguageDecision('en', 1.0, language_mode, 1.0)

    monkeypatch.setattr(batch_language, 'resolve_language', resolve)
    monkeypatch.setattr(cap_config, 'execution_admission_enabled', lambda *args: language_mode == 'funding_denied')
    monkeypatch.setattr(
        stt_cap_dispatch, 'sync_allowed', lambda *args, **kwargs: not language_mode.startswith('funding_denied')
    )
    monkeypatch.setattr(funded_processing, 'consent_allows', lambda *args: language_mode != 'consent_denied')
    monkeypatch.setattr(shadow_intake, 'language_inheritance_enabled', lambda: inherited)
    monkeypatch.setattr(retention, 'assert_batch_write_allowed', privacy)
    objects = ObjectClient()
    artifacts = create_artifact_store(repository.store, objects, 'synthetic-bucket', b's' * 32)
    monkeypatch.setattr(shadow_intake, 'artifacts_for', lambda _: artifacts)
    repository.offer('worker-stage')
    reservation = repository.reserve('synthetic-owner', 'upload:0', 'fresh')
    await shadow_intake.stage_upload(
        repository,
        reservation,
        'synthetic-owner',
        'upload',
        copies,
        directory,
        'fresh',
        conversation_id,
        'omi',
        'synthetic-device',
    )
    staged = row(repository, reservation[0])
    assert original.exists() and original.read_bytes() == original_bytes
    assert not Path(directory).exists()
    if denied or language_mode.startswith('privacy_'):
        assert staged['state'] == 'settled'
        assert staged['outcome'] == ('dropped' if denied else 'error')
        assert objects.uploads == 0
        assert probes == (['self'] if language_mode == 'privacy_between_probes' else [])
        return
    assert staged['state'] == 'ready'
    work = repository.take('worker-stage')
    assert work.duration_seconds == 1 and work.shadow
    assert artifacts.fetch_audio(work).startswith(b'RIFF')
    context = read_context(artifacts.fetch_audio(work))
    assert inputs == [
        (
            'fr'
            if language_mode == 'conversation_inherited'
            else 'en' if language_mode == 'declared' or inherited else 'multi'
        )
    ]
    assert context['stt_language_evidence'] == (
        'declared' if language_mode == 'declared' or inherited else language_mode
    )
    staged_audio = StagedAudio(artifacts.fetch_audio)
    worker, words, _, _, _, _ = setup_worker(decode=staged_audio.decode, language_of=staged_audio.language)
    results = worker.process_batch([work])
    if language_mode in {'declared', 'audio_lid', 'self_lid'} or inherited:
        assert words.calls and isinstance(results[0], WorkResult)
    else:
        assert not words.calls  # Uncertain/denied evidence never becomes permission.
    assert objects.uploads == 1  # audio only, no transcript upload
    assert all(b'synthetic-owner' not in body for _, body in objects.objects.values())
    for path, record in repository.store.client.rows.items():
        assert path[0].startswith('batch_pipeline_dev_shadow_') or (
            path[0] == 'batch_pipeline_dev_artifacts' and record['shadow'] and record['cleanup_after']
        )


async def test_v1_shaped_offer_computes_identity_before_legacy_decode(repository, monkeypatch, tmp_path):
    from utils.executors import start_background_task
    from utils.sync.content_id import compute_sync_content_id
    from database.batch_pipeline_shadow import identity

    original = Path(pcm(tmp_path, 1750000100, samples=16000))
    content = compute_sync_content_id('synthetic-owner', [str(original)])

    def privacy(*args, **kwargs):
        if kwargs.get('snapshots') is not None:
            kwargs['snapshots'].update(user={'language': ''})
        return 0

    tasks = []

    def track(coro, *, name):
        task = start_background_task(coro, name=name)
        tasks.append(task)
        return task

    monkeypatch.setattr(retention, 'assert_batch_write_allowed', privacy)
    artifacts = create_artifact_store(repository.store, ObjectClient(), 'synthetic-bucket', b's' * 32)
    monkeypatch.setattr(shadow_intake, 'artifacts_for', lambda _: artifacts)
    monkeypatch.setattr(shadow_intake, 'FirestoreStore', lambda _: repository.store)
    monkeypatch.setattr(shadow_intake, 'ShadowStore', lambda _: repository)
    monkeypatch.setattr(shadow_intake, 'selected', lambda *args: True)
    monkeypatch.setattr(shadow_intake, 'start_background_task', track)
    repository.offer('worker-v1')
    await shadow_intake.offer_upload(
        uid='synthetic-owner',
        content_id=None,
        paths=[str(original)],
        lane='fresh',
        age=0,
        conversation_id=None,
        source='omi',
        device_id='synthetic-device',
        byok=False,
        policy=SimpleNamespace(batch_enabled=False),
    )
    await asyncio.gather(*tasks)
    assert row(repository, identity('synthetic-owner', content + ':0'))['state'] == 'ready'
    assert original.exists()  # Only shadow's private copy was decoded/cleaned.
