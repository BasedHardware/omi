"""Native audio read-ahead across the real owner walk and artifact reader."""

from concurrent.futures import Future
from dataclasses import replace
import hashlib
import json
from unittest.mock import Mock

import pytest

from tests.unit.test_batch_pipeline_artifacts import setup as artifact_fixture
from tests.unit.test_batch_pipeline_owner_chain_projection import (
    BURST,
    SUCCESS_PAYLOAD,
    ResultLog,
    patch_conversation_assignment,
    projector_for,
)
from tests.unit.test_batch_pipeline_owner_drain import InlineExecutor
from utils.batch_pipeline import projection, projection_prefetch
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.source_audio import MAGIC


@pytest.fixture(autouse=True)
def native_audio_enabled_by_default(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED', raising=False)


def native_prefetch_counts():
    return {
        sample.labels['outcome']: sample.value
        for sample in projection_prefetch.NATIVE_AUDIO_PREFETCH.collect()[0].samples
        if sample.name.endswith('_total')
    }


class DelayedManifestExecutor(InlineExecutor):
    def __init__(self):
        self.loads = []

    def submit(self, fn, *args, **kwargs):
        if fn is projection_prefetch._read_manifest:
            future = Future()
            self.loads.append((future, fn, args, kwargs))
            return future
        return super().submit(fn, *args, **kwargs)


@pytest.mark.parametrize(
    'eager,fault',
    [
        (False, None),
        (True, None),
        (True, 'staging'),
        (False, 'staging'),
        (False, 'source'),
        (False, 'privacy'),
        (False, 'delayed'),
    ],
)
def test_native_read_ahead_only_defers_with_full_assignment_verification(monkeypatch, eager, fault):
    if eager:
        monkeypatch.setenv('BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED', 'false')
    monkeypatch.setenv('BUCKET_PRIVATE_CLOUD_SYNC', 'synthetic-private')
    log = ResultLog()
    segment = 'native-unit'
    log.commit(BURST, 'native', segment, [segment], record=True, outcome='success')
    binding = log.bindings[segment] = replace(
        log.bindings[segment], native_record=True, target_conversation_id='native'
    )
    job = log.jobs[segment]
    job.update(conversation_id='native', privacy_generation=0, requires_compute_admission=True)
    unit = WorkItem(**{key: job[key] for key in WorkItem.__dataclass_fields__ if key in job})
    pcm = b'\x01\x00' * 16000
    path = f'chunks/{BURST}/native/capture.bin'
    context = {
        'owner_id': BURST,
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': segment,
        'capture_at': unit.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': 'native',
    }
    manifest = {
        'owner_id': BURST,
        'conversation_id': 'native',
        'capture_at': unit.capture_at,
        'context': context,
        'references': [
            {
                'bucket': 'synthetic-private',
                'path': path,
                'generation': 7,
                'pcm_sha256': hashlib.sha256(pcm).hexdigest(),
                'start_frame': 0,
                'offset_frame': 0,
                'frames': 16000,
            }
        ],
    }
    artifacts, gcs, privacy = artifact_fixture()
    job['audio_uri'] = artifacts.stage_audio(unit, MAGIC + json.dumps(manifest).encode())
    stage_path = next(iter(gcs.objects))
    generation, sealed = gcs.objects[stage_path]
    if fault == 'staging':
        gcs.objects[stage_path] = (generation, sealed[:-1] + bytes([sealed[-1] ^ 1]))
    gcs.objects[path] = (7, b'\0\0' * 16000 if fault == 'source' else pcm)
    checks = []
    authorize = artifacts.authorize

    def check(item):
        checks.append(gcs.downloads)
        current = authorize(item)
        if current.generation != item.privacy_generation:
            raise PermissionError('synthetic privacy generation was revoked')
        return current

    def revoke_after_source():
        if gcs.downloads == 2:
            privacy.context = ProtectionContext('enhanced', 1)

    artifacts.authorize = check
    if fault == 'privacy':
        gcs.after_download = revoke_after_source
    patch_conversation_assignment(monkeypatch, None, fail_first_n=0)
    projector = projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD))
    projector.clock = lambda: log.clock
    projector.fetch_audio = artifacts.fetch_audio
    delayed = DelayedManifestExecutor() if fault == 'delayed' else None
    executor = delayed or InlineExecutor()
    prefetch = projection_prefetch.ChainPrefetch(projector, owner_key(BURST), 1, executor=executor)
    before = native_prefetch_counts()
    prefetch.advance(None)
    eager_failure = eager and fault == 'staging'
    assert gcs.downloads == (1 if eager_failure else 2 if eager else 0)
    if delayed is not None:
        original_wait = projection_prefetch.wait

        def expire_pending_read(futures, *, timeout):
            assert 0 < timeout <= 15
            if futures[0].done():
                return original_wait(futures, timeout=timeout)
            return set(), set(futures)

        monkeypatch.setattr(projection_prefetch, 'wait', expire_pending_read)
        assert projector.drain_step(BURST, 15, prefetch=prefetch) == projection.Walk([], [], True, 'prefetch_wait')
        assert gcs.downloads == 0
        [(future, fn, args, kwargs)] = delayed.loads
        future.set_result(fn(*args, **kwargs))
    walk = projector.drain_step(BURST, 15, prefetch=prefetch)
    prefetch.close()
    after = native_prefetch_counts()
    terminal = 'abandoned' if eager_failure else 'consumed'
    assert after == {**before, 'started': before['started'] + 1, terminal: before[terminal] + 1}
    assert gcs.downloads == (1 if fault == 'staging' and not eager_failure else 2)
    if fault in {None, 'delayed'}:
        assert checks == [0, 1, 2]
        assert walk.advanced == [segment]
        assert log.results[segment]['projection']['state'] == 'persisted'
    elif fault in {'staging', 'source'}:
        assert log.results[segment]['projection']['state'] == 'quarantined'
    else:
        assert walk.advanced == []
        assert 'projection' not in log.results[segment]


def test_native_read_ahead_counts_one_taken_unused_and_one_closed_candidate(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_DEFER_NATIVE_PROJECTION_AUDIO_PREFETCH_ENABLED', raising=False)
    log = ResultLog()
    ids = ['unused', 'untaken']
    for segment in ids:
        log.commit(BURST, 'native', segment, ids, record=True, outcome='success')
        log.bindings[segment] = replace(log.bindings[segment], native_record=True)
        log.jobs[segment]['requires_compute_admission'] = True
    projector = projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD))
    projector.fetch_audio = Mock(side_effect=AssertionError('speculative audio download'))
    walk = Mock(side_effect=projection.ProjectionBlocked('synthetic guard'))
    monkeypatch.setattr(projector, '_persist_read', walk)
    prefetch = projection_prefetch.ChainPrefetch(projector, owner_key(BURST), 2, executor=InlineExecutor())
    before = native_prefetch_counts()
    assert projector.drain_step(BURST, 15, prefetch=prefetch).advanced == []
    prefetch.close()
    assert walk.call_count == 1
    projector.fetch_audio.assert_not_called()
    assert native_prefetch_counts() == {
        **before,
        'started': before['started'] + 2,
        'abandoned': before['abandoned'] + 2,
    }


def test_native_read_ahead_settles_late_future_after_close():
    prefetch = projection_prefetch.ChainPrefetch(projector_for(ResultLog()), owner_key(BURST), 1)
    running, queued = Future(), Future()
    assert running.set_running_or_notify_cancel()
    prefetch.rows = {'running': running, 'queued': queued}
    before = native_prefetch_counts()
    token = projection_prefetch.NativeAudioPrefetch()
    prefetch.close()
    assert queued.cancelled() and prefetch.take('running') is None
    running.set_result(projection_prefetch.Prefetched({}, Mock(), native_audio=token))
    assert native_prefetch_counts() == {
        **before,
        'started': before['started'] + 1,
        'abandoned': before['abandoned'] + 1,
    }
