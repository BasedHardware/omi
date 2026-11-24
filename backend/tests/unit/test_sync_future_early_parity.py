"""Execute main and candidate admission; compare real early-clock job documents."""

import ast
from copy import deepcopy
from dataclasses import asdict
from functools import partial
import importlib.util
from pathlib import Path
import subprocess
import types
import uuid
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.api_core.exceptions import Aborted
from prometheus_client import Counter, CollectorRegistry

from config.policy import BatchUnitPolicy
from database.batch_pipeline_staging import artifact_id
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_capture_time_skew import client, _default_skew
from utils.batch_pipeline import intake, contracts, upload_coalescing
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.stt import batch_language
from utils.sync import legacy_dark, receipt_clock
from routers import sync as router
from routers import batch_pipeline as batch_router

# Main at the review's scope-reduction decision, not the prior Q12-H tree.
MAIN = 'b23851a097739b0a144c60cc4cae54233bc45b76'
ROOT = Path(__file__).resolve().parents[3]
NOW = 1794700800.0


def main_source(path):
    return subprocess.check_output(['git', 'show', f'{MAIN}:{path}'], cwd=ROOT, text=True)


def main_module(path, monkeypatch):
    name = 'utils.batch_pipeline._q12_main_' + Path(path).stem
    module = types.ModuleType(name)
    module.__package__ = 'utils.batch_pipeline'
    module.__file__ = str(ROOT / path)
    monkeypatch.setitem(__import__('sys').modules, name, module)
    with monkeypatch.context() as scoped:
        if path.endswith('/upload_coalescing.py'):
            scoped.setattr('prometheus_client.Counter', partial(Counter, registry=CollectorRegistry()))
        exec(compile(main_source(path), f'main:{path}', 'exec'), module.__dict__)
    return module


def main_endpoint():
    tree = ast.parse(main_source('backend/routers/sync.py'))
    function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'sync_local_files_v2')
    function.decorator_list = []
    scope = dict(router.__dict__)
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'main:sync-v2', 'exec'), scope)
    return scope['sync_local_files_v2']


@pytest.mark.parametrize('future_enabled', [False, True])
@pytest.mark.parametrize('mixed', [False, True])
def test_early_upload_job_and_context_documents_equal_main(client, monkeypatch, tmp_path, future_enabled, mixed):
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', str(future_enabled).lower())
    monkeypatch.setenv('BATCH_PIPELINE_PACKING_SAMPLE_RATE', '0.001')
    monkeypatch.setenv('BATCH_PIPELINE_UPLOAD_COALESCING_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'false')
    monkeypatch.setattr(router.time, 'time', lambda: NOW)
    monkeypatch.setattr(router._uuid, 'uuid4', lambda: uuid.UUID(int=1))
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda *a: legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(
        receipt_clock, 'account_created_at', Mock(side_effect=AssertionError('early must not read future metadata'))
    )
    monkeypatch.setattr(
        batch_language,
        'resolve_language',
        lambda *a, **k: types.SimpleNamespace(
            language='en', parakeet_safe=True, evidence=None, confidence=1.0, probe_seconds=0.0
        ),
    )

    async def batch_route(**kwargs):
        return router.RecordUploadRoute.BATCH

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    baseline = main_module('backend/utils/batch_pipeline/intake.py', monkeypatch)
    baseline.WorkItem = main_module('backend/utils/batch_pipeline/contracts.py', monkeypatch).WorkItem
    records = []
    for module, endpoint in [(baseline, main_endpoint()), (intake, router.sync_local_files_v2)]:
        store = MemoryStore()
        store.namespace = 'batch_pipeline_dev'
        contexts = []
        monkeypatch.setattr(module, 'FirestoreStore', lambda *a: store)
        monkeypatch.setattr(module, 'current_stage', lambda: 'dev')
        monkeypatch.setattr(module, 'serving_for', lambda *a, **k: False)
        monkeypatch.setattr(module, 'admission_language_exclusion_enabled', lambda: False)
        monkeypatch.setattr(module, 'language_guard_enabled', lambda: False)
        monkeypatch.setattr(
            module, 'provider_config', lambda: types.SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
        )

        def authorize(_store, _work, snapshots):
            snapshots['user'] = {'language': 'en'}
            snapshots['conversations'] = {}
            return ProtectionContext('standard', 0)

        monkeypatch.setattr(module, 'batch_artifact_authorize', authorize)

        def freeze(wav, context):
            contexts.append(deepcopy(context))
            return wav

        monkeypatch.setattr(module, 'with_context', freeze)

        def stage(item, wav):
            uri = 'gs://synthetic/audio#1'
            store.rows['artifacts', artifact_id(item.segment_id, uri)] = {
                'owner_id': item.owner_id,
                'privacy_generation': item.privacy_generation,
                'uri': uri,
            }
            return uri

        monkeypatch.setattr(module, 'artifacts_for', lambda *a: types.SimpleNamespace(stage_audio=stage))
        monkeypatch.setattr(
            module,
            'durable_status',
            lambda *a, **k: {
                'job_id': 'bp_job',
                'status': 'queued',
                'total_files': 1,
                'total_segments': 0,
                'poll_after_ms': 0,
                'lane': 'backfill',
            },
        )
        monkeypatch.setattr(router, 'accept_batch_upload', module.accept_upload)
        # The baseline function snapshots its globals; bind this run's actual intake.
        if module is baseline:
            endpoint.__globals__['accept_batch_upload'] = module.accept_upload
        app = FastAPI()
        app.post('/v2/sync-local-files')(endpoint)
        app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'synthetic-uid'
        paths = [pcm(tmp_path, 788918400, 16000)]
        if mixed:
            paths.append(pcm(tmp_path, int(NOW) - 10, 16000))
        files = [('files', (Path(path).name, Path(path).read_bytes(), 'application/octet-stream')) for path in paths]
        with TestClient(app, raise_server_exceptions=False) as routed:
            response = routed.post(
                '/v2/sync-local-files', headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'}, files=files
            )
        assert response.status_code == 202, response.text
        jobs = {key: row for (table, key), row in store.rows.items() if table == 'jobs'}
        assert jobs and all('capture_time_trust' not in row for row in jobs.values())
        assert contexts and all('capture_clock_policy' not in row for row in contexts)
        records.append(
            {
                'jobs': jobs,
                'contexts': contexts,
                'intakes': {key: row for (table, key), row in store.rows.items() if table == 'intakes'},
            }
        )
    assert records[0] == records[1]


def test_early_placement_and_coverage_implementations_are_main_bytes():
    for path in [
        'backend/utils/batch_pipeline/capture_decode.py',
        'backend/utils/capture/batch_coverage.py',
        'backend/utils/sync/pipeline.py',
        'backend/utils/sync/wal_audio_coverage.py',
    ]:
        actual = (ROOT / path).read_text()
        if path.endswith('/capture_decode.py'):
            # Exclude only the export and source-frame telemetry. Every byte
            # involved in the actual early-clock decode and placement stays pinned.
            diagnostic = (
                'validated_frame_count = _frame_count\n',
                '            if received_at is None:\n'
                '                unit = replace(unit, source_frames=len(pcm) // 2 - padding_frames)\n',
                '        padding_frames = 0\n',
                '                padding_frames = 0\n',
                '                    padding_frames = 0\n',
                '                padding_frames += gap\n',
            )
            for fragment in sorted(diagnostic, key=len, reverse=True):
                actual = actual.replace(fragment, '')
        baseline = main_source(path)
        if path.endswith(('/pipeline.py', '/wal_audio_coverage.py')):
            # Compare the early-placement implementation byte for byte. The
            # default staging seam is also exercised directly below.
            def without_unrelated_functions(text):
                # process_segment lost the backfill day cap (#25677).
                # The legacy reprocess callback runs after placement and has
                # its own body parity check in test_enrichment_callback_parity.
                # Its coordinator also runs after placement. Enrichment route
                # tests cover the SCA-3874 retry enrollment there.
                names = (
                    {'apply_wal_audio_coverage'}
                    if path.endswith('/wal_audio_coverage.py')
                    else {
                        '_retrieve_file_paths_v2',
                        'process_segment',
                        '_reprocess_conversation_after_update',
                        '_reprocess_merged_conversations',
                    }
                )
                lines = text.splitlines(keepends=True)
                for node in sorted(
                    (n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name in names),
                    key=lambda n: n.lineno,
                    reverse=True,
                ):
                    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                    lines = lines[: start - 1] + lines[node.end_lineno :]
                return (
                    ''.join(lines)
                    .replace('from utils import backfill_hours_cap\n', '')
                    .replace('from utils.enrichment.admission import require_transcript_decoded\n', '')
                )

            if path.endswith('/wal_audio_coverage.py'):
                actual = actual.replace(
                    '        # This is an already decoded/admitted source. A later admission-switch\n'
                    '        # rollback cannot revoke its clock or its exact source-frame proof.\n',
                    '',
                )
                actual = actual.replace(
                    'parse_sync_filename_timestamp(wav_path, enforce_window=False)',
                    'parse_sync_filename_timestamp(wav_path)',
                )
            else:
                actual, baseline = without_unrelated_functions(actual), without_unrelated_functions(baseline)
        assert actual == baseline, path


def test_anchor_contention_is_503_before_staging_or_acknowledgement(client, monkeypatch, tmp_path):
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'true')
    store = MemoryStore()
    store.namespace = 'batch_pipeline_dev'
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *a: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda *a: legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(intake, 'serving_for', lambda *a, **k: False)
    monkeypatch.setattr(intake, 'admission_language_exclusion_enabled', lambda: False)
    monkeypatch.setattr(intake, 'language_guard_enabled', lambda: False)
    monkeypatch.setattr(
        intake, 'provider_config', lambda: types.SimpleNamespace(pool_kind='dedicated_batch', max_unit_seconds=600)
    )
    monkeypatch.setattr(receipt_clock, 'account_created_at', lambda *a: NOW - 10000)

    def unavailable(*a, **k):
        raise Aborted('synthetic transaction contention')

    monkeypatch.setattr(receipt_clock, 'frozen_offset', unavailable)
    monkeypatch.setattr(intake, 'artifacts_for', lambda *a: artifacts)
    artifacts = types.SimpleNamespace(stage_audio=Mock())
    admit = Mock(side_effect=AssertionError('failed anchor cannot admit work'))
    monkeypatch.setattr(intake, 'admit', admit)

    def authorize(_store, _work, snapshots):
        snapshots['user'] = {'language': 'en'}
        snapshots['conversations'] = {}
        return ProtectionContext('standard', 0)

    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)

    async def batch_route(**kwargs):
        return router.RecordUploadRoute.BATCH

    monkeypatch.setattr(router, 'registered_record_response', batch_route)
    monkeypatch.setattr(router, 'accept_batch_upload', intake.accept_upload)
    future = int(router.time.time()) + 12 * 365 * 86400
    path = Path(pcm(tmp_path, future, 16000))
    payload = path.read_bytes()
    response = client.post(
        '/v2/sync-local-files',
        headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'},
        files=[('files', (f'audio_omi_pcm16_16000_clkeone_{future}.bin', payload, 'application/octet-stream'))],
    )
    assert response.status_code == 503, response.text
    assert response.json()['code'] == 'capture_clock_anchor_unavailable'
    assert response.headers['Retry-After'] == '30'
    artifacts.stage_audio.assert_not_called()
    admit.assert_not_called()
    assert path.read_bytes() == payload  # Synthetic phone copy is untouched.
    assert not store.rows


@pytest.mark.asyncio
async def test_unmarked_rpc_and_coalescing_documents_equal_main_and_old_readers_accept(monkeypatch):
    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    original = main_module('backend/utils/batch_pipeline/contracts.py', monkeypatch)
    previous_coalescing = main_module('backend/utils/batch_pipeline/upload_coalescing.py', monkeypatch)
    args = ('segment', 'synthetic-owner', 100, 'intake:pending', 1, contracts.Priority.RECENT)
    old, current = original.WorkItem(*args), contracts.WorkItem(*args)
    assert current.to_dict(include_nulls=True) == asdict(old)
    assert original.WorkItem(**current.to_dict(include_nulls=True)) == old

    lease = contracts.LeasedWork(current, 'synthetic-token', 1, 200)
    request = types.SimpleNamespace(
        service=lambda: types.SimpleNamespace(pull=lambda *a, **k: [lease]),
        limit=1,
        capacity=None,
        pool='batch',
    )
    response = await batch_router.pull(request)
    assert response == {'leases': [asdict(original.LeasedWork(old, 'synthetic-token', 1, 200))]}
    assert original.WorkItem(**response['leases'][0]['item']) == old

    members = []

    def enqueue(store, member, key, now):
        members.append(deepcopy(member))
        return None

    monkeypatch.setattr(upload_coalescing.config, 'enabled', lambda: True)
    monkeypatch.setattr(upload_coalescing.config, 'hold_seconds', lambda **k: 60)
    monkeypatch.setattr(upload_coalescing.rows, 'enqueue', enqueue)
    packed = (b'synthetic', 9, 100, 101, 1, 1, ['audio.bin'], 16000)
    for module in (previous_coalescing, upload_coalescing):
        monkeypatch.setattr(module, '_pack', lambda *a: packed)
    arguments = {
        'uid': 'synthetic-owner',
        'job_id': 'job',
        'content_id': 'content',
        'paths': ['audio.bin'],
        'lane': 'fresh',
        'source': 'omi',
        'should_lock': False,
        'conversation_id': 'target',
        'client_device_id': 'pendant',
        'client_platform': 'ios',
        'intake_context': {'recording_session_id': 'session'},
    }
    artifacts = types.SimpleNamespace(stage_audio=lambda *a: 'gs://synthetic/audio#1')
    for module, seed in ((previous_coalescing, old), (upload_coalescing, current)):
        assert (
            await module.offer(
                object(),
                artifacts,
                seed,
                arguments=arguments,
                context=ProtectionContext('standard', 0),
                language='en',
                policy=BatchUnitPolicy(batch_enabled=True),
                now=100,
            )
            is None
        )
    assert members[0] == members[1]
    assert 'capture_time_trust' not in members[1]['item']
    original.WorkItem(**members[1]['item'])


def test_old_readers_require_reader_first_roll_and_existing_row_partition_fences_sources(monkeypatch):
    old_contract = main_module('backend/utils/batch_pipeline/contracts.py', monkeypatch)
    future = contracts.WorkItem(
        'segment',
        'synthetic',
        NOW,
        'gs://synthetic/audio',
        1,
        contracts.Priority.DEEP,
        conversation_id='receipt-one',
        capture_time_trust='untrusted',
    )
    # New generic jobs must never reach an old CPU constructor/projector.
    with pytest.raises(TypeError, match='capture_time_trust'):
        old_contract.WorkItem(**future.to_dict())
    # Real old readers filter before construction, so direct-constructor
    # rejection above is not an admission capability fence.
    filtered = old_contract.WorkItem(
        **{key: value for key, value in future.to_dict().items() if key in old_contract.WorkItem.__dataclass_fields__}
    )
    assert not hasattr(filtered, 'capture_time_trust')
    assert filtered.capture_at == future.capture_at
    from utils.batch_pipeline import projection

    tree = ast.parse(main_source('backend/utils/batch_pipeline/projection.py'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'build_incoming')
    scope = dict(projection.__dict__)
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'old:projection-build', 'exec'), scope)
    binding = contracts.ProjectionBinding('synthetic', 'job', 'content', ('segment',))
    payload = {
        'audio_seconds': 1,
        'speech_seconds': 1,
        'words': [{'word': 'Recovered source.', 'timestamp': [0, 1]}],
        'diarization': {'turns': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}]},
    }
    old_row = scope['build_incoming'](filtered, binding, payload)
    assert old_row['id'] != future.conversation_id
    assert old_row.get('capture_time_trust') is None and old_row.get('sync_clock_run') is None
    old_overlap = main_module('backend/utils/sync/live_overlap.py', monkeypatch)
    first = {
        'id': 'receipt-one',
        'source': 'omi',
        'client_device_id': 'pendant',
        'sync_clock_run': 'receipt-one',
        'capture_time_trust': 'untrusted',
    }
    second = {**first, 'id': 'receipt-two', 'sync_clock_run': 'receipt-two'}
    ordinary = {key: value for key, value in first.items() if key not in {'sync_clock_run', 'capture_time_trust'}}
    ordinary['id'] = 'ordinary'
    assert old_overlap.compatible_capture(first, first)
    assert not old_overlap.compatible_capture(first, second)
    assert not old_overlap.compatible_capture(first, ordinary)
    assert not old_overlap.compatible_capture(ordinary, first)


def test_existing_gpu_scheduler_filters_unknown_work_fields_but_retains_full_job_trust(monkeypatch):
    old_contract = main_module('backend/utils/batch_pipeline/contracts.py', monkeypatch)
    old_scheduler = main_module('backend/utils/batch_pipeline/scheduler.py', monkeypatch)
    old_scheduler.WorkItem = old_contract.WorkItem
    store = MemoryStore()
    queue = old_scheduler.Scheduler(store)
    work = contracts.WorkItem(
        'future',
        'synthetic',
        NOW,
        'gs://synthetic/audio',
        1,
        contracts.Priority.DEEP,
        conversation_id='receipt-one',
        capture_time_trust='untrusted',
    )
    assert queue.enqueue(work, 0)
    [lease] = queue.pull(1)
    assert not hasattr(lease.item, 'capture_time_trust')  # Existing compute does not need the marker.
    assert queue.complete(old_contract.WorkResult('future', 'gs://synthetic/result'), lease.token, 2)
    row = store.rows['jobs', 'future']
    assert row['capture_time_trust'] == 'untrusted' and row['conversation_id'] == 'receipt-one'
    # The upgraded CPU reader reconstructs full admission provenance after compute.
    recovered = contracts.WorkItem(**{key: row[key] for key in contracts.WorkItem.__dataclass_fields__ if key in row})
    assert recovered.capture_time_trust == 'untrusted'


@pytest.mark.parametrize('stamp', [788918400, NOW - 10, NOW + 170, NOW + 601, NOW + 86401])
def test_default_staging_preserves_main_clock_and_bytes(monkeypatch, tmp_path, stamp):
    from datetime import datetime, timezone
    from tests.unit.test_sync_capture_time_skew import _Upload
    from utils.sync import pipeline
    from utils.sync.capture_clock import SyncCaptureTimeRejected

    monkeypatch.setenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false')
    monkeypatch.chdir(tmp_path)
    clock = types.SimpleNamespace(
        fromtimestamp=datetime.fromtimestamp, now=lambda *a: datetime.fromtimestamp(NOW, timezone.utc)
    )
    monkeypatch.setattr(pipeline, 'datetime', clock)
    tree = ast.parse(main_source('backend/utils/sync/pipeline.py'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_retrieve_file_paths_v2')
    scope = dict(pipeline.__dict__)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'main:stage', 'exec'), scope)
    outcomes = []
    for index, stage in enumerate([scope['_retrieve_file_paths_v2'], pipeline._retrieve_file_paths_v2]):
        upload = _Upload(f'audio_omi_pcm16_16000_{int(stamp)}.bin')
        try:
            [path] = stage([upload], 'synthetic', str(index))
            outcomes.append(('accepted', Path(path).name, Path(path).read_bytes()))
        except SyncCaptureTimeRejected as error:
            outcomes.append(('refused', error.status_code, error.detail))
    assert outcomes[0] == outcomes[1]
