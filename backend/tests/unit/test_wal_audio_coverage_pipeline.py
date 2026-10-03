"""WAL source-frame coverage through the sync coordinator: VAD/STT see only unreceived audio.

Uses the shared sync_v2 coordinator harness (all heavy deps stubbed) plus real
labeled PCM WAV files so the trimmed bytes reaching VAD can be asserted.
"""

import logging
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
    if coverage_flag is not None:
        monkeypatch.setenv('SYNC_WAL_AUDIO_COVERAGE_ENABLED', coverage_flag)


async def _run_batch(module, stubs, tmp_path, *, claims=True, session=ORIGIN):
    kwargs = dict(
        target_conversation_id=None,
        client_device_id='pendant',
        recording_session_id=session,
        audio_start_seconds=1759999000.0,
        audio_end_seconds=1760000100.0,
        task_mode=True,
        capture_evidence_claims={BIN_NAME: _claim()} if claims else None,
    )
    await module._run_full_pipeline_background_async(
        'job-coverage', 'uid', ['/tmp/f.bin'], 'omi', False, str(tmp_path / 'job'), **kwargs
    )


@pytest.mark.asyncio
async def test_tail_received_frames_suppressed_vad_sees_only_new(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    derivative = state.vad_seen[0]
    assert '.coverage' in derivative and derivative.endswith('_1760000003.5.wav')
    assert _read_payload(derivative) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (7, 8, 9))
    assert len(state.coverage_calls()) == 1


@pytest.mark.asyncio
async def test_prelive_and_missed_holes_preserved_as_two_files(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(3, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 2
    payloads = sorted(_read_payload(path) for path in state.vad_seen)
    expected = sorted(b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in group) for group in ((0, 1, 2), (7, 8, 9)))
    assert payloads == expected


@pytest.mark.asyncio
async def test_fully_covered_file_yields_no_stt_and_success_not_silence(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 10, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert state.vad_seen == []
    assert state.processed == []
    assert len(state.outcomes) == 1
    assert state.outcomes[0].value == 'success'


@pytest.mark.asyncio
async def test_flag_off_keeps_original_bytes_path_and_no_lookup(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch, coverage_flag='off')
    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert state.coverage_calls() == []
    assert len(state.vad_seen) == 1
    original = state.vad_seen[0]
    assert original.endswith(f'{WAV_STEM}.wav')
    assert _read_payload(original) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_absent_signal_keeps_original_audio(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_wrong_root_and_provenance_mismatch_keep_audio(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    other = '999e4567-e89b-12d3-a456-426614174999'
    wrong_root = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES, root=other)])
    wrong_device = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    rows = [
        generation(1, capture_evidence=wrong_root),
        generation(2, capture_evidence=wrong_device, client_device_id='other-device'),
    ]
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=rows)
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_conflicting_envelope_abstains_whole_capture(coordinator, monkeypatch, tmp_path, caplog):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    conflicted = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)], conflicts=1)
    clean = _envelope([_run(0, 5, samples_per_frame=FRAME_SAMPLES)])
    rows = [generation(1, capture_evidence=conflicted), generation(2, capture_evidence=clean)]
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=rows)
    with caplog.at_level(logging.INFO):
        await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    coverage_lines = [r.getMessage() for r in caplog.records if 'event=sync_wal_audio_coverage' in r.getMessage()]
    assert any('outcome=abstained' in line for line in coverage_lines)


@pytest.mark.asyncio
async def test_truncated_lookup_abstains(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    state = _wire(
        pipeline,
        monkeypatch,
        tmp_path,
        lineage_rows=[generation(1, capture_evidence=_envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)]))],
    )

    lineage_module = sys.modules[pipeline.plan_segment_targets.__module__]
    monkeypatch.setattr(lineage_module, '_load_lineage', lambda *a, **k: ([generation(1)], float('inf'), False))
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_clock_skewed_filename_still_trims_by_frame_key(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    rows = [generation(1, capture_evidence=env)]
    skewed = 'audio_pcm16_1760001200'
    claims = {skewed + '.bin': _claim()}
    wav_dir = tmp_path / 'skew'
    wav_dir.mkdir()
    state = _wire(pipeline, monkeypatch, wav_dir, lineage_rows=rows, wav_name=skewed)
    kwargs = dict(
        target_conversation_id=None,
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        audio_start_seconds=1759999000.0,
        audio_end_seconds=1760000100.0,
        task_mode=True,
        capture_evidence_claims=claims,
    )
    await module._run_full_pipeline_background_async(
        'job-coverage-skew', 'uid', ['/tmp/f.bin'], 'omi', False, str(wav_dir / 'job'), **kwargs
    )
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (7, 8, 9))


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
async def test_lineage_lookup_failure_keeps_audio_and_reports_fallback(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])

    lineage_module = sys.modules[pipeline.plan_segment_targets.__module__]

    def broken(*args, **kwargs):
        raise RuntimeError('read failed')

    monkeypatch.setattr(lineage_module, 'load_lineage', broken)
    fallback_calls = []
    monkeypatch.setattr(coverage_mod, 'record_fallback', lambda **kwargs: fallback_calls.append(kwargs))
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    assert fallback_calls and fallback_calls[0]['from_mode'] == 'sync_lineage'


@pytest.mark.asyncio
async def test_invalid_time_geometry_keeps_audio_via_fallback(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    monkeypatch.setattr(coverage_mod, 'get_timestamp_from_path', lambda path: float('nan'))
    fallback_calls = []
    monkeypatch.setattr(coverage_mod, 'record_fallback', lambda **kwargs: fallback_calls.append(kwargs))
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    assert fallback_calls


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
    from database import conversations
    from models import transcript_segment
    from utils.conversations import lifecycle
    from utils.sync import pipeline

    return pipeline


@pytest.mark.parametrize('skew', [40, 1200])
def test_saved_transcript_proof_live_words_once_then_new(real_pipeline, monkeypatch, tmp_path, skew):
    import threading

    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_cross_job_assignment import intake
    from tests.unit.test_sync_lineage_dedupe_replay import at, live_row, seeded_store
    from utils.conversations import lifecycle
    from utils.sync import recording_lineage

    from config.sync_live_dedupe import SYNC_LINEAGE_LIVE_DEDUPE_ENV

    pipeline = real_pipeline
    monkeypatch.delenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, raising=False)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.delenv('SYNC_WAL_AUDIO_COVERAGE_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)

    base_ts = 1_760_000_000 + skew
    stem = f'audio_pcm16_{int(base_ts)}'
    wav_path = tmp_path / f'{stem}.wav'
    _write_labeled_wav(wav_path, range(10))
    claim = {**_claim(), 'capture_root': ROOT}

    def word(value):
        return f'live-word-{value}' if value < 7 else f'new-word-{value}'

    live_segments = [
        {
            'start': i * 0.5,
            'end': i * 0.5 + 0.5,
            'text': word(i),
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
        }
        for i in range(7)
    ]
    row = live_row(
        started_at=at(1760000000),
        finished_at=at(1760000003.5),
        transcript_segments=live_segments,
    )
    store = seeded_store([row])

    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
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
    assert len(batch['wav_paths']) == 1
    derivative = batch['wav_paths'][0]

    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', lambda _path: 'file://x')
    monkeypatch.setattr(pipeline, 'schedule_syncing_temporal_file_deletion', lambda _path: None)
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', lambda _lang: ('deepgram', 'cfg', 'nova-3'))
    prerecorded_calls = []

    def fake_prerecorded(url, **kwargs):
        prerecorded_calls.append(url)
        return (['w'], 'en')

    monkeypatch.setattr(pipeline, 'prerecorded', fake_prerecorded)
    monkeypatch.setattr(pipeline, 'postprocess_words', lambda words, offset: _segments_from_bytes(derivative, word))
    monkeypatch.setattr(pipeline, 'identify_speakers_for_segments', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline.conversations_db, 'get_manual_speaker_receipt', lambda *args: {})
    monkeypatch.setattr(pipeline, 'capture_evidence_dark_write_enabled', lambda: False)
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    finish = MagicMock()
    monkeypatch.setattr(pipeline, 'finish_sync_segment', finish)

    response = {'new_memories': set(), 'updated_memories': set()}
    ok = pipeline.process_segment(
        derivative,
        'u',
        response,
        threading.Lock(),
        [],
        target_conversation_id=row['id'],
        client_device_id='pendant',
    )
    assert ok is True
    texts = [s['text'] for s in store.rows[('users', 'u', 'conversations', row['id'])]['transcript_segments']]
    assert sorted(texts) == sorted(word(i) for i in range(10))
    assert prerecorded_calls


def _segments_from_bytes(path, frame_words, frame_samples=FRAME_SAMPLES):
    from models.transcript_segment import TranscriptSegment

    with wave.open(str(path), 'rb') as wav:
        payload = wav.readframes(wav.getnframes())
    values = [
        int.from_bytes(payload[i : i + 2], 'little', signed=True) for i in range(0, len(payload), frame_samples * 2)
    ]
    return [
        TranscriptSegment(
            text=frame_words(v),
            start=i * frame_samples / RATE,
            end=(i + 1) * frame_samples / RATE,
            speaker='SPEAKER_00',
            is_user=False,
            speaker_id=0,
        )
        for i, v in enumerate(values)
    ]


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


def test_short_novel_tail_marked_and_admitted_past_vad_floor(real_pipeline, monkeypatch, tmp_path):
    pipeline = real_pipeline
    _coverage_env(monkeypatch)
    wav_path = tmp_path / f'{WAV_STEM}.wav'
    _write_short_frame_wav(wav_path, range(10))
    batch = _short_tail_batch(monkeypatch, wav_path)
    assert batch['status'] == 'applied' and len(batch['wav_paths']) == 1
    derivative = batch['wav_paths'][0]
    mapping = batch['source_frame_maps'][derivative]
    assert mapping['coverage_trimmed'] is True
    assert _duration(derivative) == pytest.approx(0.4)
    assert _read_payload(derivative) == _frame_bytes(8, SMALL_FRAME_SAMPLES) + _frame_bytes(9, SMALL_FRAME_SAMPLES)

    monkeypatch.setattr(pipeline, 'get_timestamp_from_path', _ts)
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *a, **k: [{'start': 0, 'end': 0.4}])
    admitted = set()
    pipeline.retrieve_vad_segments(derivative, admitted, [], source_frame_map=mapping)
    assert len(admitted) == 1
    exported = next(iter(admitted))
    assert _read_payload(exported) == _read_payload(derivative)

    dropped = set()
    pipeline.retrieve_vad_segments(derivative, dropped, [], source_frame_map=None)
    assert dropped == set()
    dropped_default = set()
    pipeline.retrieve_vad_segments(
        derivative, dropped_default, [], source_frame_map={**mapping, 'coverage_trimmed': False}
    )
    assert dropped_default == set()


def test_subsecond_tail_saved_transcript_contains_new_word(real_pipeline, monkeypatch, tmp_path):
    import threading

    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_cross_job_assignment import intake
    from tests.unit.test_sync_lineage_dedupe_replay import at, live_row, seeded_store
    from utils.conversations import lifecycle

    from config.sync_live_dedupe import SYNC_LINEAGE_LIVE_DEDUPE_ENV

    pipeline = real_pipeline
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    _coverage_env(monkeypatch)
    wav_path = tmp_path / f'{WAV_STEM}.wav'
    _write_short_frame_wav(wav_path, range(10))
    batch = _short_tail_batch(monkeypatch, wav_path)
    assert batch['status'] == 'applied' and len(batch['wav_paths']) == 1
    derivative = batch['wav_paths'][0]
    mapping = batch['source_frame_maps'][derivative]

    live_segments = [
        {
            'start': i * 0.5,
            'end': i * 0.5 + 0.5,
            'text': f'live-word-{i}',
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
        }
        for i in range(9)
    ]
    row = live_row(
        started_at=at(1760000000),
        finished_at=at(1760000004.5),
        transcript_segments=live_segments,
    )
    store = seeded_store([row])

    monkeypatch.setattr(pipeline, 'get_timestamp_from_path', _ts)
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *a, **k: [{'start': 0, 'end': 0.4}])
    segmented = set()
    pipeline.retrieve_vad_segments(derivative, segmented, [], source_frame_map=mapping)
    assert len(segmented) == 1
    seg_path = next(iter(segmented))

    def word(value):
        return f'live-word-{value}' if value < 9 else 'new-word-9'

    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', lambda _path: 'file://x')
    monkeypatch.setattr(pipeline, 'schedule_syncing_temporal_file_deletion', lambda _path: None)
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', lambda _lang: ('deepgram', 'cfg', 'nova-3'))
    prerecorded_calls = []

    def fake_prerecorded(url, **kwargs):
        prerecorded_calls.append(url)
        return (['w'], 'en')

    monkeypatch.setattr(pipeline, 'prerecorded', fake_prerecorded)
    monkeypatch.setattr(
        pipeline, 'postprocess_words', lambda words, offset: _segments_from_bytes(seg_path, word, SMALL_FRAME_SAMPLES)
    )
    monkeypatch.setattr(pipeline, 'identify_speakers_for_segments', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline.conversations_db, 'get_manual_speaker_receipt', lambda *args: {})
    monkeypatch.setattr(pipeline, 'capture_evidence_dark_write_enabled', lambda: False)
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    finish = MagicMock()
    monkeypatch.setattr(pipeline, 'finish_sync_segment', finish)

    response = {'new_memories': set(), 'updated_memories': set()}
    ok = pipeline.process_segment(
        seg_path,
        'u',
        response,
        threading.Lock(),
        [],
        target_conversation_id=row['id'],
        client_device_id='pendant',
    )
    assert ok is True
    assert prerecorded_calls
    texts = [s['text'] for s in store.rows[('users', 'u', 'conversations', row['id'])]['transcript_segments']]
    assert 'new-word-9' in texts


def test_fully_covered_intake_never_calls_provider_or_enrichment(real_pipeline, monkeypatch, tmp_path):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from tests.unit.test_sync_lineage_dedupe_replay import live_row, seeded_store
    from utils.sync import recording_lineage

    pipeline = real_pipeline
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    monkeypatch.delenv('SYNC_WAL_AUDIO_COVERAGE_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_ENABLED', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)

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
    assert batch['suppressed_all'] is True
    assert batch['wav_paths'] == []
    prerecorded = MagicMock()
    monkeypatch.setattr(pipeline, 'prerecorded', prerecorded)
    assert prerecorded.call_count == 0
