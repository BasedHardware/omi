"""Execute main and candidate admission; compare real early-clock job documents."""

import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import subprocess
import types
import uuid
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.policy import BatchUnitPolicy
from database.batch_pipeline_staging import artifact_id
from tests.unit.test_batch_pipeline_audio import pcm
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_capture_time_skew import client, _default_skew
from utils.batch_pipeline import intake
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.stt import batch_language
from utils.sync import legacy_dark, receipt_clock
from routers import sync as router

# Main at the review's scope-reduction decision, not the prior Q12-H tree.
MAIN = '2d59f75eace67a03cc31dd07effa7ab73b8e15a5'
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
            actual = actual.replace(
                'validated_frame_count = _frame_count\n', ''
            )  # New export only, no changed early code.
        assert actual == main_source(path), path


def test_anchor_contention_is_503_before_staging_or_acknowledgement(client, monkeypatch, tmp_path):
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
        from google.api_core.exceptions import Aborted

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
    path = Path(pcm(tmp_path, 2147472000, 16000))
    payload = path.read_bytes()
    response = client.post(
        '/v2/sync-local-files',
        headers={'X-App-Platform': 'ios', 'X-Device-Id-Hash': 'abcd1234'},
        files=[('files', ('audio_omi_pcm16_16000_clkeone_2147472000.bin', payload, 'application/octet-stream'))],
    )
    assert response.status_code == 503, response.text
    assert response.json()['code'] == 'capture_clock_anchor_unavailable'
    assert response.headers['Retry-After'] == '30'
    artifacts.stage_audio.assert_not_called()
    admit.assert_not_called()
    assert path.read_bytes() == payload  # Synthetic phone copy is untouched.
    assert not store.rows
