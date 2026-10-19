"""WAL source-frame coverage through the sync coordinator: VAD/STT see only unreceived audio.

Uses the shared sync_v2 coordinator harness (all heavy deps stubbed) plus real
labeled PCM WAV files so the trimmed bytes reaching VAD can be asserted.
"""

import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import tests.unit.test_sync_v2 as sync_v2_harness
from tests.unit.test_sync_recording_lineage import ORIGIN, generation
from tests.unit.test_wal_audio_coverage import EPOCH, RATE, ROOT, _envelope, _frame_bytes, _run
from utils.sync import recording_lineage
from utils.sync import wal_audio_coverage as coverage_mod

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

FRAME_SAMPLES = 8000
BIN_NAME = 'audio_pcm16_1760000000.bin'
WAV_STEM = 'audio_pcm16_1760000000'


@pytest.fixture
def coordinator():
    module, stubs = sync_v2_harness.TestAsyncCoordinatorBehavioral._load_sync_module()
    try:
        yield module, stubs
    finally:
        sync_v2_harness.TestAsyncCoordinatorBehavioral._cleanup(stubs['saved_modules'])


def _write_labeled_wav(path, frame_values):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        for value in frame_values:
            wav.writeframes(_frame_bytes(value, FRAME_SAMPLES))


def _read_payload(path):
    with wave.open(str(path), 'rb') as wav:
        return wav.readframes(wav.getnframes())


def _claim(frame_count=10):
    return {
        'capture_root': ROOT,
        'clock_epoch': EPOCH,
        'source_frame_start': 0,
        'frame_count': frame_count,
        'rate_hz': RATE,
        'codec': 'pcm16',
        'channel': 'mono',
    }


def _ts(path):
    return float(Path(path).stem.rsplit('_', 1)[-1])


def _duration(path):
    try:
        with wave.open(str(path), 'rb') as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:
        return 0.0


def _wire(pipeline, monkeypatch, tmp_path, *, lineage_rows, frame_values=range(10), wav_name=WAV_STEM):
    """Wire a coordinator attempt: one labeled WAL whose rows carry live envelopes."""
    wav_path = tmp_path / f'{wav_name}.wav'
    _write_labeled_wav(wav_path, frame_values)

    def decode(raw_paths, decoded_frames=None):
        if decoded_frames is not None:
            decoded_frames[str(wav_path)] = [FRAME_SAMPLES] * len(list(frame_values))
        return [str(wav_path)]

    pipeline.decode_files_to_wav = MagicMock(side_effect=decode)
    pipeline._cleanup_files = MagicMock()
    pipeline.get_timestamp_from_path = _ts
    pipeline.get_wav_duration = _duration
    pipeline.users_db = MagicMock()
    pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
    pipeline.build_person_embeddings_cache = MagicMock(return_value={})
    pipeline.record_usage = MagicMock()
    pipeline.get_sync_job = MagicMock(return_value={'partial_result': {}})
    pipeline.get_processed_segments = MagicMock(return_value=set())
    pipeline._reprocess_merged_conversations = lambda *a, **k: None
    outcomes = []
    pipeline._record_sync_job_outcome_async = AsyncMock(side_effect=lambda outcome, **kw: outcomes.append(outcome))
    monkeypatch.setattr(coverage_mod, 'get_timestamp_from_path', _ts)
    monkeypatch.setattr(coverage_mod, 'get_wav_duration', _duration)
    monkeypatch.setattr(coverage_mod, 'parse_sync_filename_timestamp', _ts)

    lineage_module = sys.modules[pipeline.plan_segment_targets.__module__]
    lineage_calls = []

    def load_lineage(*args, **kwargs):
        lineage_calls.append(kwargs)
        return (list(lineage_rows), None, False)

    monkeypatch.setattr(lineage_module, '_load_lineage', load_lineage)

    vad_seen = []

    def fake_vad(path, segmented, errors, *args, **kwargs):
        vad_seen.append(path)
        stem = Path(path).stem
        segmented.add(str(tmp_path / f'seg_{stem}.wav'))

    pipeline.retrieve_vad_segments = fake_vad
    processed = []

    def process(path, uid, response, lock, errors, *args, **kwargs):
        processed.append(path)
        response['updated_memories'].add('sync-row')
        return True

    pipeline.process_segment = process
    return SimpleNamespace(
        vad_seen=vad_seen,
        processed=processed,
        outcomes=outcomes,
        lineage_calls=lineage_calls,
        coverage_calls=lambda: [call for call in lineage_calls if call.get('include_capture_evidence')],
    )


def _coverage_env(monkeypatch, coverage_flag=None):
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    for name in (
        'SYNC_WAL_AUDIO_COVERAGE_ENABLED',
        'SYNC_LINEAGE_RESOLVE_ENABLED',
        'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')  # Explicit legacy global policy.
    if coverage_flag is not None:
        monkeypatch.setenv('SYNC_WAL_AUDIO_COVERAGE_ENABLED', coverage_flag)


async def _run_batch(module, stubs, tmp_path, *, claims=True, session=ORIGIN, raw_name=BIN_NAME):
    kwargs = dict(
        target_conversation_id=None,
        client_device_id='pendant',
        recording_session_id=session,
        audio_start_seconds=1759999000.0,
        audio_end_seconds=1760000100.0,
        task_mode=True,
        capture_evidence_claims={BIN_NAME: _claim()} if claims is True else claims,
    )
    await module._run_full_pipeline_background_async(
        'job-coverage', 'uid', [f'/tmp/{raw_name}'], 'omi', False, str(tmp_path / 'job'), **kwargs
    )


class _FakeQuery:
    def __init__(self, docs=()):
        self.docs = list(docs)
        self.ops = []

    def collection(self, name):
        self.ops.append(('collection', name))
        return self

    def document(self, name):
        self.ops.append(('document', name))
        return self

    def where(self, *, filter):
        self.ops.append(('where', filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field_path, direction):
        self.ops.append(('order_by', field_path, direction))
        return self

    def select(self, field_paths):
        self.ops.append(('select', tuple(field_paths)))
        return self

    def limit(self, count):
        self.ops.append(('limit', count))
        return self

    def stream(self):
        return iter(self.docs)


def _selected(ops):
    return next(value for name, *rest in ops if name == 'select' for value in rest)


def test_projection_flag_off_byte_identical_and_flag_on_adds_evidence(monkeypatch):
    from database import sync_recording_lineage as lineage_db

    monkeypatch.setattr(lineage_db, 'record_firestore_read', lambda *args: None)
    before = datetime.fromtimestamp(1760000000, timezone.utc)
    after = datetime.fromtimestamp(1759999000, timezone.utc)

    off = _FakeQuery()
    lineage_db.get_recording_generations(
        'u', ORIGIN, started_before=before, finished_after=after, limit=8, firestore_client=off
    )
    assert _selected(off.ops) == tuple(lineage_db.LINEAGE_FIELD_PATHS)
    assert ('limit', 9) in off.ops

    on = _FakeQuery()
    lineage_db.get_recording_generations(
        'u',
        ORIGIN,
        started_before=before,
        finished_after=after,
        limit=8,
        include_capture_evidence=True,
        firestore_client=on,
    )
    assert _selected(on.ops) == tuple(lineage_db.LINEAGE_FIELD_PATHS) + ('capture_evidence',)
    assert ('limit', 9) in on.ops
    off_filters = [op for op in off.ops if op[0] in ('where', 'order_by', 'limit')]
    on_filters = [op for op in on.ops if op[0] in ('where', 'order_by', 'limit')]
    assert off_filters == on_filters

    off_origin = _FakeQuery()
    lineage_db.get_origin_generation('u', ORIGIN, limit=5, firestore_client=off_origin)
    assert _selected(off_origin.ops) == tuple(lineage_db.LINEAGE_FIELD_PATHS)
    assert ('limit', 6) in off_origin.ops

    on_origin = _FakeQuery()
    lineage_db.get_origin_generation('u', ORIGIN, limit=5, include_capture_evidence=True, firestore_client=on_origin)
    assert _selected(on_origin.ops) == tuple(lineage_db.LINEAGE_FIELD_PATHS) + ('capture_evidence',)
    assert ('limit', 6) in on_origin.ops


def test_loader_preserves_old_kwargs_shape_for_stubs(monkeypatch):
    from utils.sync import recording_lineage

    seen = []

    class StubDb:
        @staticmethod
        def get_recording_generations(uid, origin_id, *, started_before, finished_after, limit, firestore_client):
            seen.append('generations')
            return []

        @staticmethod
        def get_origin_generation(uid, origin_id, *, limit, firestore_client):
            seen.append('origin')
            return []

    monkeypatch.setattr(recording_lineage, '_load_lineage', recording_lineage._load_lineage)
    import database.sync_recording_lineage as real_db

    monkeypatch.setattr(real_db, 'get_recording_generations', StubDb.get_recording_generations)
    monkeypatch.setattr(real_db, 'get_origin_generation', StubDb.get_origin_generation)
    rows, truncated, degraded = recording_lineage._load_lineage(
        'u', ORIGIN, datetime.now(timezone.utc), None, datetime.now(timezone.utc)
    )
    assert rows == [] and truncated is None and degraded is False
    assert seen == ['generations', 'origin']


@pytest.mark.asyncio
async def test_cancelled_coverage_preserves_inputs_and_adopts_nothing(tmp_path, monkeypatch):
    import asyncio
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from utils.executors import run_blocking
    from utils.sync import recording_lineage

    _coverage_env(monkeypatch)
    wav_path = tmp_path / f'{WAV_STEM}.wav'
    _write_labeled_wav(wav_path, range(10))
    claim = _claim()
    started = threading.Event()
    release = threading.Event()
    derivative_written = []

    def worker(uid, origin_id, **kwargs):
        coverage_dir = tmp_path / f'{WAV_STEM}.coverage' / 'attempt-unique'
        coverage_dir.mkdir(parents=True, exist_ok=True)
        orphan = coverage_dir / f'{WAV_STEM}_1760000003.5.wav'
        orphan.write_bytes(b'partial')
        derivative_written.append(str(orphan))
        started.set()
        release.wait(10)
        return {
            'status': 'applied',
            'reason': 'none',
            'stats': {
                'kept_seconds': 1.5,
                'dropped_seconds': 3.5,
                'context_seconds': 0.0,
                'file_count': 1,
                'suppressed_count': 0,
            },
            'wav_paths': [str(orphan)],
            'source_frame_maps': {},
            'retired_paths': [str(wav_path)],
            'generated_paths': {str(orphan)},
            'suppressed_all': False,
        }

    monkeypatch.setattr(coverage_mod, 'apply_batch_wal_audio_coverage', worker)
    monkeypatch.setattr(recording_lineage, 'load_lineage', lambda *a, **k: ([], None, False))
    cleaned = []

    def cleanup(paths):
        cleaned.extend(paths)
        for p in paths:
            if os.path.exists(p):
                os.remove(p)

    db_pool = ThreadPoolExecutor(1)
    storage_pool = ThreadPoolExecutor(1)
    try:
        task = asyncio.create_task(
            coverage_mod.apply_sync_wal_audio_coverage(
                'uid',
                'omi',
                False,
                'pendant',
                ORIGIN,
                {BIN_NAME: claim},
                [str(wav_path)],
                {str(wav_path): [FRAME_SAMPLES] * 10},
                run_blocking=run_blocking,
                db_executor=db_pool,
                storage_executor=storage_pool,
                cleanup_files=cleanup,
            )
        )
        assert await asyncio.to_thread(started.wait, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        db_pool.shutdown(wait=True)
        storage_pool.shutdown(wait=True)
        assert derivative_written
        assert cleaned == derivative_written
        for orphan_path in derivative_written:
            assert not os.path.exists(orphan_path)
        assert wav_path.exists()
        assert _read_payload(str(wav_path)) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    finally:
        release.set()
        db_pool.shutdown(wait=False)
        storage_pool.shutdown(wait=False)


@pytest.mark.asyncio
async def test_cleanup_and_logging_exceptions_never_lose_inputs(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from utils.executors import run_blocking
    from utils.sync import recording_lineage

    _coverage_env(monkeypatch)
    wav_path = tmp_path / f'{WAV_STEM}.wav'
    _write_labeled_wav(wav_path, range(10))
    claim = _claim()
    derivative = tmp_path / f'{WAV_STEM}.coverage' / 'attempt-x' / f'{WAV_STEM}_1760000003.5.wav'
    derivative.parent.mkdir(parents=True)
    derivative.write_bytes(b'kept')

    def worker(uid, origin_id, **kwargs):
        return {
            'status': 'applied',
            'reason': 'none',
            'stats': {
                'kept_seconds': 1.5,
                'dropped_seconds': 3.5,
                'context_seconds': 0.0,
                'file_count': 1,
                'suppressed_count': 0,
            },
            'wav_paths': [str(derivative)],
            'source_frame_maps': {str(derivative): {'claim': claim}},
            'retired_paths': [str(wav_path)],
            'generated_paths': {str(derivative)},
            'suppressed_all': False,
        }

    monkeypatch.setattr(coverage_mod, 'apply_batch_wal_audio_coverage', worker)
    monkeypatch.setattr(recording_lineage, 'load_lineage', lambda *a, **k: ([], None, False))
    monkeypatch.setattr(coverage_mod.logger, 'info', MagicMock(side_effect=RuntimeError('log failure')))

    def cleanup(paths):
        raise RuntimeError('cleanup failure')

    db_pool = ThreadPoolExecutor(1)
    storage_pool = ThreadPoolExecutor(1)
    try:
        paths, maps, suppressed = await coverage_mod.apply_sync_wal_audio_coverage(
            'uid',
            'omi',
            False,
            'pendant',
            ORIGIN,
            {BIN_NAME: claim},
            [str(wav_path)],
            {str(wav_path): [FRAME_SAMPLES] * 10},
            run_blocking=run_blocking,
            db_executor=db_pool,
            storage_executor=storage_pool,
            cleanup_files=cleanup,
        )
    finally:
        db_pool.shutdown(wait=False)
        storage_pool.shutdown(wait=False)
    assert paths == [str(derivative)]
    assert suppressed is False
    assert wav_path.exists()
    assert derivative.exists()


@pytest.fixture(scope='module')
def real_pipeline():
    from models import transcript_segment  # noqa: F401
    from utils.conversations import lifecycle  # noqa: F401
    from database import conversations  # noqa: F401
    from utils.sync import legacy_segment_core as pipeline

    return pipeline


SMALL_FRAME_SAMPLES = 3200


def _write_short_frame_wav(path, frame_values):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        for value in frame_values:
            wav.writeframes(_frame_bytes(value, SMALL_FRAME_SAMPLES))


def _short_tail_batch(monkeypatch, wav_path):
    from utils.sync import recording_lineage

    claim = _claim()
    env = _envelope([_run(0, 9, samples_per_frame=SMALL_FRAME_SAMPLES)])
    monkeypatch.setattr(
        recording_lineage, 'load_lineage', lambda *a, **k: ([generation(1, capture_evidence=env)], None, False)
    )
    return coverage_mod.apply_batch_wal_audio_coverage(
        'u',
        ORIGIN,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        wav_paths=[str(wav_path)],
        source_frame_maps={
            str(wav_path): {
                'claim': claim,
                'offsets': [i * SMALL_FRAME_SAMPLES for i in range(11)],
                'incomplete': False,
            }
        },
        decoded_frames={str(wav_path): [SMALL_FRAME_SAMPLES] * 10},
    )


def test_receipt_only_batch_keeps_original_and_trim_marker_admits_short_slice(real_pipeline, monkeypatch, tmp_path):
    pipeline = real_pipeline
    _coverage_env(monkeypatch)
    wav_path = tmp_path / f'{WAV_STEM}.wav'
    _write_short_frame_wav(wav_path, range(10))
    batch = _short_tail_batch(monkeypatch, wav_path)
    assert batch['status'] == 'applied' and batch['wav_paths'] == [str(wav_path)]
    assert batch['suppressed_all'] is False
    derivative = batch['wav_paths'][0]
    mapping = {**batch['source_frame_maps'][derivative], 'coverage_trimmed': True}

    monkeypatch.setattr(pipeline, 'get_timestamp_from_path', _ts)
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *a, **k: [{'start': 0, 'end': 0.4}])
    admitted = set()
    pipeline.retrieve_vad_segments(derivative, admitted, [], source_frame_map=mapping)
    assert len(admitted) == 1
    exported = next(iter(admitted))
    assert _read_payload(exported) == _frame_bytes(0, SMALL_FRAME_SAMPLES) + _frame_bytes(1, SMALL_FRAME_SAMPLES)

    dropped = set()
    pipeline.retrieve_vad_segments(derivative, dropped, [], source_frame_map=None)
    assert dropped == set()
    dropped_default = set()
    pipeline.retrieve_vad_segments(
        derivative, dropped_default, [], source_frame_map={**mapping, 'coverage_trimmed': False}
    )
    assert dropped_default == set()


def test_receipt_only_full_coverage_preserves_the_wal_untouched(real_pipeline, monkeypatch, tmp_path):
    from utils.sync import recording_lineage

    pipeline = real_pipeline
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.delenv('SYNC_WAL_AUDIO_COVERAGE_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_ENABLED', raising=False)
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')  # Explicit legacy global policy.

    wav_path = tmp_path / f'{WAV_STEM}.wav'
    _write_labeled_wav(wav_path, range(10))
    claim = _claim()
    env = _envelope([_run(0, 10, samples_per_frame=FRAME_SAMPLES)])
    rows = [generation(1, capture_evidence=env)]
    monkeypatch.setattr(recording_lineage, 'load_lineage', lambda *a, **k: (list(rows), None, False))
    batch = coverage_mod.apply_batch_wal_audio_coverage(
        'u',
        ORIGIN,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        wav_paths=[str(wav_path)],
        source_frame_maps={
            str(wav_path): {'claim': claim, 'offsets': [i * FRAME_SAMPLES for i in range(11)], 'incomplete': False}
        },
        decoded_frames={str(wav_path): [FRAME_SAMPLES] * 10},
    )
    assert batch['status'] == 'applied'
    assert batch['suppressed_all'] is False
    assert batch['wav_paths'] == [str(wav_path)]
    assert batch['retired_paths'] == []
    assert batch['stats']['dropped_seconds'] == 0.0
    assert _read_payload(str(wav_path)) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


_WHOLE_BATCH_ARGS = ('uid', ORIGIN, 'omi', 'pendant', False, 1759999000.0, 1760000100.0)


def _s1_spies(pipeline, monkeypatch):
    """Observe the routing split without changing it: the old whole-batch
    resolver versus the per-segment lineage planner."""
    resolver_calls = []
    monkeypatch.setattr(
        pipeline,
        'resolve_recording_session_sync_target',
        lambda *args, **kwargs: resolver_calls.append(args) or 'resolved-target',
    )
    plan_calls = []
    monkeypatch.setattr(pipeline, 'plan_segment_targets', lambda *args, **kwargs: plan_calls.append(args) or {})
    return SimpleNamespace(resolver_calls=resolver_calls, plan_calls=plan_calls)


def test_s1_oversize_claim_set_returns_false_before_serialization(monkeypatch):
    """Oversize claim sets are rejected by bound before the bounded JSON
    serializer is ever invoked."""
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    dump_calls = []
    monkeypatch.setattr(recording_lineage.json, 'dumps', lambda *a, **k: dump_calls.append(a) or '{}')
    oversize = {f'f{i}.bin': _claim() for i in range(21)}
    assert not recording_lineage.lineage_resolution_requested(
        'u',
        ORIGIN,
        1.0,
        2.0,
        capture_evidence_claims=oversize,
        filenames=list(oversize),
    )
    assert dump_calls == []
    assert not recording_lineage.lineage_resolution_requested(
        'u',
        ORIGIN,
        1.0,
        2.0,
        capture_evidence_claims={BIN_NAME: _claim()},
        filenames=[f'f{i}.bin' for i in range(21)],
    )
    assert dump_calls == []
