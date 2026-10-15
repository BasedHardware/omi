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
from config.sync_live_dedupe import SYNC_LINEAGE_LIVE_DEDUPE_ENV
from tests.unit.test_sync_cross_job_assignment import intake
from tests.unit.test_sync_lineage_dedupe_replay import at, live_row, seeded_store
from tests.unit.test_sync_recording_lineage import ORIGIN, generation
from tests.unit.test_wal_audio_coverage import EPOCH, RATE, ROOT, _envelope, _frame_bytes, _run
from utils.audio_timeline import CaptureTimeline, ProviderEpochTranslator
from utils.capture_evidence import SourcePositionMap, unknown_envelope
from utils.conversations import lifecycle
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


@pytest.mark.asyncio
async def test_receipt_only_tail_envelope_vad_sees_the_original_bytes(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    original = state.vad_seen[0]
    assert original.endswith(f'{WAV_STEM}.wav') and '.coverage' not in original
    assert _read_payload(original) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    assert len(state.coverage_calls()) == 1


@pytest.mark.asyncio
async def test_receipt_only_hole_envelope_keeps_the_original_whole(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(3, 7, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_received_but_untranscribed_wal_reaches_stt_and_is_saved(coordinator, monkeypatch, tmp_path):
    """A receipt fully covering 0..10 authorizes nothing: VAD/STT see the original
    bytes and the batch never takes the suppress-all success short circuit."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _envelope([_run(0, 10, samples_per_frame=FRAME_SAMPLES)])
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    assert state.vad_seen[0].endswith(f'{WAV_STEM}.wav')
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    assert len(state.processed) == 1
    assert len(state.outcomes) == 1
    assert state.outcomes[0].value == 'success'


def _committed_envelope(covered, *, fed=None, wall0=1760000000.0, spf=FRAME_SAMPLES, root=ROOT, epoch=EPOCH):
    """Real committed proof from the live producer for ordinals `covered`.

    Wall anchors follow the producer's frame-end convention:
    receipt_wall = wav_start + (ordinal + 1) * frame_duration.
    """
    fed_ordinals = list(range(max(covered) + 1)) if fed is None else list(fed)
    covered_set = set(covered)
    source = SourcePositionMap(committed=True)
    notes = []
    note_start = None
    sample_cursor = 0
    for ordinal in fed_ordinals:
        source.accept(
            {'capture_root': root, 'clock_epoch': epoch, 'source_frame': ordinal},
            sample_start=sample_cursor,
            sample_count=spf,
            rate_hz=RATE,
            payload=_frame_bytes(ordinal, min(spf, 4096)),
            receipt_wall_time=wall0 + (ordinal + 1) * spf / RATE,
        )
        if ordinal in covered_set:
            if note_start is None:
                note_start = sample_cursor
            note_end = sample_cursor + spf
        elif note_start is not None:
            notes.append((note_start, note_end))
            note_start = None
        sample_cursor += spf
    if note_start is not None:
        notes.append((note_start, note_end))
    source.remember_transcripts(
        [{'id': f's{i}', '_capture_word_ranges': ((start, end),)} for i, (start, end) in enumerate(notes)]
    )
    segments = [
        SimpleNamespace(id=f's{i}', text='x', start=0.0, end=1.0, audio_alignment=None) for i in range(len(notes))
    ]
    return source.committed_snapshot('conv', segments)


def _wire_real(
    pipeline,
    monkeypatch,
    tmp_path,
    *,
    lineage_rows,
    word,
    frame_values=range(10),
    wav_writer=_write_labeled_wav,
    frame_samples=FRAME_SAMPLES,
):
    """Real-coordinator wiring: real decode handoff, retrieve_vad_segments,
    process_segment and StrictFirestore intake; only provider words, VAD
    intervals, job ledger and context I/O are stubbed."""
    wav_path = tmp_path / f'{WAV_STEM}.wav'
    wav_writer(wav_path, frame_values)
    frame_count = len(list(frame_values))

    def decode(raw_paths, decoded_frames=None):
        if decoded_frames is not None:
            decoded_frames[str(wav_path)] = [frame_samples] * frame_count
        return [str(wav_path)]

    job_updates = []
    outcomes = []
    prerecorded_calls = []
    processed_paths = []

    monkeypatch.setattr(pipeline, 'decode_files_to_wav', decode)
    monkeypatch.setattr(pipeline, '_cleanup_files', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'get_timestamp_from_path', _ts)
    monkeypatch.setattr(pipeline, 'get_wav_duration', _duration)
    monkeypatch.setattr(pipeline, 'async_resolve_geolocation', AsyncMock(side_effect=lambda geo: geo))
    monkeypatch.setattr(pipeline, 'get_byok_keys', lambda: {})
    monkeypatch.setattr(pipeline, 'set_byok_uid', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'lineage_resolution_requested', lambda *a, **k: True)
    monkeypatch.setattr(pipeline, 'bind_or_converge_sync_ledger_completion', lambda **k: None)
    monkeypatch.setattr(pipeline, '_mark_job_processing_for_run', lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline, '_update_sync_job_for_run', lambda *a, **k: job_updates.append(a[2] if len(a) > 2 else k)
    )
    monkeypatch.setattr(pipeline, '_finalize_sync_job_failure', AsyncMock())
    monkeypatch.setattr(pipeline, '_finalize_sync_job_for_run', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'get_sync_job', lambda *a, **k: {'partial_result': {}})
    monkeypatch.setattr(pipeline, 'get_processed_segments', lambda *a, **k: set())
    monkeypatch.setattr(pipeline, 'get_processed_sync_segment_ids', lambda *a, **k: set())
    monkeypatch.setattr(pipeline, '_add_processed_segment_for_run', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'add_processed_sync_segment_id', lambda *a, **k: True)
    monkeypatch.setattr(pipeline, 'checkpoint_sync_content_partial_result', lambda *a, **k: True)
    monkeypatch.setattr(pipeline, 'mark_sync_content_completed', lambda *a, **k: True)
    monkeypatch.setattr(pipeline, 'delete_sync_job_run_lock_epoch', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, '_record_sync_segment_outcome', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, '_record_sync_segment_failure_async', AsyncMock())
    monkeypatch.setattr(pipeline, '_reprocess_merged_conversations', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'schedule_person_voice_learning_retries', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, '_record_restricted_sync_dg_usage', AsyncMock())
    monkeypatch.setattr(pipeline, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(pipeline, 'try_mark_once', lambda *a, **k: True)
    monkeypatch.setattr(pipeline, 'record_usage', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'plan_segment_targets', lambda *a, **k: {})
    monkeypatch.setattr(pipeline, 'users_db', MagicMock(get_user_transcription_preferences=MagicMock(return_value={})))
    monkeypatch.setattr(pipeline, '_load_sync_segment_context', AsyncMock(return_value=(False, None, {})))
    monkeypatch.setattr(
        pipeline,
        '_record_sync_job_outcome_async',
        AsyncMock(side_effect=lambda outcome, **kwargs: outcomes.append(outcome)),
    )
    monkeypatch.setattr(coverage_mod, 'get_timestamp_from_path', _ts)
    monkeypatch.setattr(coverage_mod, 'get_wav_duration', _duration)
    monkeypatch.setattr(coverage_mod, 'parse_sync_filename_timestamp', _ts)
    monkeypatch.setattr(recording_lineage, 'load_lineage', lambda *a, **k: (list(lineage_rows), None, False))
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda path, **k: [{'start': 0, 'end': _duration(path)}])
    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', lambda _path: 'file://x')
    monkeypatch.setattr(pipeline, 'schedule_syncing_temporal_file_deletion', lambda _path: None)
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', lambda _lang: ('deepgram', 'cfg', 'nova-3'))

    def fake_prerecorded(url, **kwargs):
        prerecorded_calls.append(url)
        return (['w'], 'en')

    monkeypatch.setattr(pipeline, 'prerecorded', fake_prerecorded)
    real_process = pipeline.process_segment

    def tracking_process(path, *args, **kwargs):
        processed_paths.append(path)
        return real_process(path, *args, **kwargs)

    monkeypatch.setattr(pipeline, 'process_segment', tracking_process)
    monkeypatch.setattr(
        pipeline,
        'postprocess_words',
        lambda words, offset: _segments_from_bytes(processed_paths[-1], word, frame_samples),
    )
    monkeypatch.setattr(pipeline, 'identify_speakers_for_segments', lambda *a, **k: None)
    monkeypatch.setattr(pipeline.conversations_db, 'get_manual_speaker_receipt', lambda *a: {})
    finish = MagicMock()
    monkeypatch.setattr(pipeline, 'finish_sync_segment', finish)
    return SimpleNamespace(
        wav_path=wav_path,
        job_updates=job_updates,
        outcomes=outcomes,
        prerecorded_calls=prerecorded_calls,
        processed_paths=processed_paths,
        finish=finish,
    )


async def _run_real(pipeline, tmp_path, *, target_conversation_id=None, session=ORIGIN, claims='default'):
    await pipeline._run_full_pipeline_background_async(
        'job-coverage',
        'u',
        [f'/tmp/{BIN_NAME}'],
        'omi',
        False,
        str(tmp_path / 'job'),
        target_conversation_id=target_conversation_id,
        client_device_id='pendant',
        recording_session_id=session,
        audio_start_seconds=1759999000.0,
        audio_end_seconds=1760000100.0,
        task_mode=True,
        capture_evidence_claims={BIN_NAME: _claim()} if claims == 'default' else claims,
    )


def _live_segments(word, count):
    return [
        {
            'start': i * 0.5,
            'end': i * 0.5 + 0.5,
            'text': word(i),
            'speaker': 'SPEAKER_00',
            'speaker_id': 0,
            'is_user': False,
        }
        for i in range(count)
    ]


def _stored_texts(store, row):
    return [s['text'] for s in store.rows[('users', 'u', 'conversations', row['id'])]['transcript_segments']]


@pytest.mark.asyncio
async def test_committed_live_frames_suppressed_and_new_speech_saved(real_pipeline, monkeypatch, tmp_path):
    pipeline = real_pipeline
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    _coverage_env(monkeypatch)
    env = _committed_envelope(range(7))

    def word(value):
        return f'live-word-{value}' if value < 7 else f'new-word-{value}'

    row = live_row(
        started_at=at(1760000000),
        finished_at=at(1760000003.5),
        transcript_segments=_live_segments(word, 7),
    )
    store = seeded_store([row])
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)], word=word)
    await _run_real(pipeline, tmp_path, target_conversation_id=row['id'])

    texts = _stored_texts(store, row)
    assert sorted(texts) == sorted([word(i) for i in range(7)] + [word(i) for i in range(7, 10)])
    for i in range(7):
        assert texts.count(f'live-word-{i}') == 1
    assert state.finish.call_count == 1
    assert state.finish.call_args.args[1]['id'] == row['id']
    assert state.finish.call_args.args[2]['updated_memories'] == {row['id']}
    assert state.outcomes[-1].value == 'success'
    assert len(state.processed_paths) == 1
    assert _read_payload(state.processed_paths[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (7, 8, 9))
    assert state.prerecorded_calls


@pytest.mark.asyncio
async def test_fully_committed_wal_skips_provider_and_enrichment(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _committed_envelope(range(10))
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert state.vad_seen == []
    assert state.processed == []
    assert len(state.outcomes) == 1
    assert state.outcomes[0].value == 'success'


@pytest.mark.asyncio
async def test_cross_lifetime_root_keeps_untranscribed_wal(real_pipeline, monkeypatch, tmp_path):
    pipeline = real_pipeline
    _coverage_env(monkeypatch)
    env = _committed_envelope(range(10), wall0=1760000000.0 + 86400.0)

    def word(value):
        return f'new-word-{value}'

    row = live_row(
        started_at=at(1760000000),
        finished_at=at(1760000005.0),
        transcript_segments=[],
    )
    store = seeded_store([row])
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)], word=word)
    await _run_real(pipeline, tmp_path, target_conversation_id=row['id'])
    assert not (tmp_path / f'{WAV_STEM}.coverage').exists()
    assert len(state.processed_paths) == 1
    assert _read_payload(state.processed_paths[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    texts = _stored_texts(store, row)
    assert sorted(texts) == sorted(word(i) for i in range(10))
    assert state.finish.call_count == 1
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_committed_hole_keeps_prelive_and_new_speech_separately(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _committed_envelope(range(3, 7))
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 2
    payloads = sorted(
        (_read_payload(path) for path in state.vad_seen),
        key=lambda payload: int.from_bytes(payload[:2], 'little', signed=True),
    )
    assert payloads[0] == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (0, 1, 2))
    assert payloads[1] == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (7, 8, 9))


@pytest.mark.asyncio
async def test_half_boundary_proof_rounds_inward(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    source = SourcePositionMap(committed=True)
    for i in range(10):
        source.accept(
            {'capture_root': ROOT, 'clock_epoch': EPOCH, 'source_frame': i},
            sample_start=i * FRAME_SAMPLES,
            sample_count=FRAME_SAMPLES,
            rate_hz=RATE,
            payload=_frame_bytes(i, 4096),
            receipt_wall_time=1760000000.0 + (i + 1) * FRAME_SAMPLES / RATE,
        )
    source.remember_transcripts(
        [
            {
                'id': 's1',
                '_capture_word_ranges': (
                    (3 * FRAME_SAMPLES + FRAME_SAMPLES // 2, 7 * FRAME_SAMPLES - FRAME_SAMPLES // 2),
                ),
            }
        ]
    )
    env = source.committed_snapshot(
        'conv', [SimpleNamespace(id='s1', text='x', start=0.0, end=1.0, audio_alignment=None)]
    )
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 2
    payloads = sorted(
        (_read_payload(path) for path in state.vad_seen),
        key=lambda payload: int.from_bytes(payload[:2], 'little', signed=True),
    )
    assert payloads[0] == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (0, 1, 2, 3))
    assert payloads[1] == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in (6, 7, 8, 9))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mutate',
    [
        lambda e: e.update(version=2),
        lambda e: e['lifetime'].update(complete=False),
        lambda e: e['lifetime'].update(history=[]),
        lambda e: e['runs'][0].update(samples_per_frame=FRAME_SAMPLES + 1),
        lambda e: e['runs'][0].update(receipt_wall_start=e['runs'][0]['receipt_wall_start'] + 5.0),
        lambda e: e['runs'][0].update(clock_epoch=EPOCH + 1),
        lambda e: e.update(proof='receipt_v1'),
    ],
)
async def test_mismatched_committed_evidence_keeps_original(coordinator, monkeypatch, tmp_path, mutate):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    env = _committed_envelope(range(7))
    mutate(env)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert len(state.vad_seen) == 1
    original = state.vad_seen[0]
    assert '.coverage' not in original
    assert _read_payload(original) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_flag_off_keeps_original_bytes_path_and_no_lookup(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch, coverage_flag='off')
    env = _committed_envelope(range(7))
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert state.coverage_calls() == []
    assert len(state.vad_seen) == 1
    original = state.vad_seen[0]
    assert original.endswith(f'{WAV_STEM}.wav')
    assert _read_payload(original) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_flag_typo_keeps_original_bytes_path_and_no_lookup(coordinator, monkeypatch, tmp_path):
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch, coverage_flag='treu')
    env = _committed_envelope(range(7))
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)])
    await _run_batch(module, stubs, tmp_path)
    assert state.coverage_calls() == []
    assert len(state.vad_seen) == 1
    original = state.vad_seen[0]
    assert original.endswith(f'{WAV_STEM}.wav')
    assert _read_payload(original) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


@pytest.mark.asyncio
async def test_committed_bounded_context_and_short_new_tail_saved(real_pipeline, monkeypatch, tmp_path):
    """Short frames: context budget keeps <=0.25s of covered neighbors, tail saved."""
    pipeline = real_pipeline
    _coverage_env(monkeypatch)
    env = _committed_envelope(range(9), spf=SMALL_FRAME_SAMPLES)

    def word(value):
        return f'live-word-{value}' if value < 9 else 'new-word-9'

    row = live_row(
        started_at=at(1760000000),
        finished_at=at(1760000004.5),
        transcript_segments=_live_segments(word, 9),
    )
    store = seeded_store([row])
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(
        pipeline,
        monkeypatch,
        tmp_path,
        lineage_rows=[generation(1, capture_evidence=env)],
        word=word,
        wav_writer=_write_short_frame_wav,
        frame_samples=SMALL_FRAME_SAMPLES,
    )
    await _run_real(pipeline, tmp_path, target_conversation_id=row['id'])
    assert len(state.processed_paths) == 1
    assert _read_payload(state.processed_paths[0]) == b''.join(_frame_bytes(v, SMALL_FRAME_SAMPLES) for v in (8, 9))
    texts = _stored_texts(store, row)
    assert texts.count('new-word-9') == 1
    assert sorted(texts) == sorted([word(i) for i in range(9)] + ['live-word-8', 'new-word-9'])
    assert state.finish.call_count == 1
    assert state.outcomes[-1].value == 'success'


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
async def test_clock_skewed_filename_still_preserves_receipt_only_audio(coordinator, monkeypatch, tmp_path):
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
        'job-coverage-skew', 'uid', [f'/tmp/{skewed}.bin'], 'omi', False, str(wav_dir / 'job'), **kwargs
    )
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


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
    assert batch['wav_paths'] == [str(wav_path)]
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
    expected = sorted([word(i) for i in range(7)] + [word(i) for i in range(10)])
    assert sorted(texts) == expected
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


def test_receipt_only_saved_transcript_contains_new_word(real_pipeline, monkeypatch, tmp_path):
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
    assert batch['status'] == 'applied' and batch['wav_paths'] == [str(wav_path)]
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
    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *a, **k: [{'start': 0, 'end': 2.0}])
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


def test_receipt_only_full_coverage_preserves_the_wal_untouched(real_pipeline, monkeypatch, tmp_path):
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
    assert batch['suppressed_all'] is False
    assert batch['wav_paths'] == [str(wav_path)]
    assert batch['retired_paths'] == []
    assert batch['stats']['dropped_seconds'] == 0.0
    assert _read_payload(str(wav_path)) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))


_WHOLE_BATCH_ARGS = ('uid', ORIGIN, 'omi', 'pendant', False, 1759999000.0, 1760000100.0)
_WHOLE_BATCH_ARGS_REAL = ('u', ORIGIN, 'omi', 'pendant', False, 1759999000.0, 1760000100.0)


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'claims',
    [
        None,
        {},
        {BIN_NAME: {**_claim(), 'capture_root': 'not-a-uuid'}},
        {'foreign.bin': _claim()},
        {BIN_NAME: {key: value for key, value in _claim().items() if key != 'codec'}},
        {BIN_NAME: {key: value for key, value in _claim().items() if key != 'capture_root'}},
        {BIN_NAME: {key: value for key, value in _claim().items() if key != 'frame_count'}},
        ['not', 'a', 'mapping'],
    ],
    ids=[
        'absent',
        'empty',
        'invalid',
        'wrong-filename',
        'missing-codec',
        'missing-root',
        'missing-count',
        'nonmapping-list',
    ],
)
async def test_s1_required_keeps_pre_lineage_binding_without_claims(coordinator, monkeypatch, tmp_path, claims):
    """Default-on S1 gate: an admitted upload without a complete validated claim
    set keeps the pre-lineage whole-batch resolver and never reaches the
    per-segment planner — the identical route the lineage kill switch takes."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path, claims=claims)
    assert spies.plan_calls == []
    assert spies.resolver_calls == [_WHOLE_BATCH_ARGS]
    assert len(state.vad_seen) == 1
    assert _read_payload(state.vad_seen[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    assert len(state.processed) == 1
    assert state.outcomes[-1].value == 'success'
    gated = (
        list(state.vad_seen),
        list(state.processed),
        [outcome.value for outcome in state.outcomes],
    )
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'off')
    await _run_batch(module, stubs, tmp_path, claims=None)
    assert spies.plan_calls == []
    assert spies.resolver_calls == [_WHOLE_BATCH_ARGS] * 2
    assert state.vad_seen == gated[0] * 2
    assert state.processed == gated[1] * 2
    assert [outcome.value for outcome in state.outcomes] == gated[2] * 2


@pytest.mark.asyncio
async def test_s1_valid_claims_bind_each_segment_to_planned_target(coordinator, monkeypatch, tmp_path):
    """A complete validated claim set admits real per-segment planning: the
    whole-batch resolver is skipped and each segment gets the planner's id."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    resolver_calls = []
    monkeypatch.setattr(
        pipeline,
        'resolve_recording_session_sync_target',
        lambda *args, **kwargs: resolver_calls.append(args) or 'resolved-target',
    )
    planned = []
    monkeypatch.setattr(
        pipeline,
        'plan_segment_targets',
        lambda segment_list, *args, **kwargs: planned.append(list(segment_list))
        or {path: f'planned-{i}' for i, path in enumerate(segment_list)},
    )
    bound_targets = []
    fake_process = pipeline.process_segment

    def tracking_process(path, uid, response, lock, errors, *args, **kwargs):
        bound_targets.append(args[4] if len(args) > 4 else None)
        return fake_process(path, uid, response, lock, errors, *args, **kwargs)

    pipeline.process_segment = tracking_process
    await _run_batch(module, stubs, tmp_path)
    assert resolver_calls == []
    assert len(planned) == 1
    assert len(planned[0]) == len(state.processed)
    assert bound_targets == [f'planned-{i}' for i in range(len(state.processed))]
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['off', 'disabled-typo'])
async def test_s1_gate_off_resumes_ungated_lineage(coordinator, monkeypatch, tmp_path, flag):
    """An explicit non-on token — including an unrecognized typo — disables the
    gate and restores the prior ungated lineage path even without claims."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', flag)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path, claims=None)
    assert spies.resolver_calls == []
    assert len(spies.plan_calls) == 1
    assert len(state.processed) == 1
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'env',
    [
        {'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST': 'someone-else'},
        {'SYNC_LINEAGE_RESOLVE_ENABLED': 'off'},
    ],
    ids=['uid-outside-allowlist', 'master-kill-switch'],
)
async def test_s1_gate_never_widens_cohort_or_bypasses_master(coordinator, monkeypatch, tmp_path, env):
    """Valid claims cannot rescue a uid outside the allowlist, and cannot bypass
    the master SYNC_LINEAGE_RESOLVE_ENABLED kill switch."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path)
    assert spies.plan_calls == []
    assert spies.resolver_calls == [_WHOLE_BATCH_ARGS]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'claim',
    [
        {**_claim(), 'capture_root': 'not-a-uuid'},
        {**_claim(), 'rate_hz': 8000},
        {**_claim(), 'codec': 'aac'},
        {**_claim(), 'channel': 'stereo'},
        {**_claim(), 'codec': 'opus'},
        _claim(frame_count=5),
    ],
    ids=['wrong-root', 'wrong-rate', 'wrong-codec', 'wrong-channel', 'decoded-format-mismatch', 'under-counted-map'],
)
async def test_s1_malformed_or_incomplete_claims_never_bind(coordinator, monkeypatch, tmp_path, claim):
    """Wrong root/rate/codec/channel claims fail admission; a claim whose
    declared geometry cannot map the decoded WAV fails the post-decode fence.
    Both take the whole-batch resolver and never bind segments."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path, claims={BIN_NAME: claim})
    assert spies.plan_calls == []
    assert spies.resolver_calls == [_WHOLE_BATCH_ARGS]
    assert len(state.processed) == 1
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'claims', [None, {BIN_NAME: {**_claim(), 'capture_root': 'not-a-uuid'}}], ids=['absent', 'invalid']
)
async def test_s1_no_claims_saves_rows_identically_to_feature_off(real_pipeline, monkeypatch, tmp_path, claims):
    """Real coordinator and intake: without claims the S1 gate lands the same
    whole-batch target, saved rows, finish call, and outcome as the lineage
    feature switched off."""
    pipeline = real_pipeline
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)

    def word(value):
        return f'word-{value}'

    resolved = [live_row(started_at=at(1760000000), finished_at=at(1760000005), transcript_segments=[])]
    store = seeded_store([resolved[0]])
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(pipeline, monkeypatch, tmp_path, lineage_rows=[], word=word)
    monkeypatch.setattr(pipeline, 'lineage_resolution_requested', recording_lineage.lineage_resolution_requested)
    resolver_calls = []
    monkeypatch.setattr(
        pipeline,
        'resolve_recording_session_sync_target',
        lambda *args: resolver_calls.append(args) or resolved[-1]['id'],
    )
    plan_calls = []
    monkeypatch.setattr(pipeline, 'plan_segment_targets', lambda *a, **k: plan_calls.append(a) or {})
    await _run_real(pipeline, tmp_path, claims=claims)
    gated_texts = _stored_texts(store, resolved[0])
    assert sorted(gated_texts) == sorted(word(i) for i in range(10))
    assert plan_calls == []
    assert resolver_calls == [_WHOLE_BATCH_ARGS_REAL]
    assert state.finish.call_count == 1
    assert state.finish.call_args.args[1]['id'] == resolved[0]['id']
    assert state.outcomes[-1].value == 'success'

    off_row = live_row(started_at=at(1760000000), finished_at=at(1760000005), transcript_segments=[])
    store.rows[('users', 'u', 'conversations', off_row['id'])] = off_row
    resolved.append(off_row)
    resolver_calls.clear()
    state.finish.reset_mock()
    state.outcomes.clear()
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'off')
    await _run_real(pipeline, tmp_path, claims=None)
    assert _stored_texts(store, off_row) == gated_texts
    assert resolver_calls == [_WHOLE_BATCH_ARGS_REAL]
    assert plan_calls == []
    assert state.finish.call_count == 1
    assert state.finish.call_args.args[1]['id'] == off_row['id']
    assert state.outcomes[-1].value == 'success'


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


@pytest.mark.asyncio
async def test_s1_valid_claims_without_dark_write_take_whole_batch(coordinator, monkeypatch, tmp_path):
    """Even a complete valid claim set cannot admit per-segment binding while
    S1 capture admission (CAPTURE_EVIDENCE_V1_DARK_WRITE) is off."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'false')
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path)
    assert spies.plan_calls == []
    assert spies.resolver_calls == [_WHOLE_BATCH_ARGS]
    assert len(state.processed) == 1
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_s1_declared_prefix_claim_still_binds_per_segment(coordinator, monkeypatch, tmp_path):
    """A claim declaring more frames than the WAL decoded (a valid prefix) is a
    complete observed mapping, so per-segment binding still applies."""
    module, stubs = coordinator
    pipeline = stubs['pipeline']
    _coverage_env(monkeypatch)
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1)])
    spies = _s1_spies(pipeline, monkeypatch)
    await _run_batch(module, stubs, tmp_path, claims={BIN_NAME: _claim(frame_count=12)})
    assert spies.resolver_calls == []
    assert len(spies.plan_calls) == 1
    assert len(state.processed) == 1
    assert state.outcomes[-1].value == 'success'


def _word_envelope_via_real_translator(word_ranges, *, wall0=1760000000.0, frames=10):
    """Committed envelope produced by the real timeline/send-map/translator path.

    Ten half-second WAL frames are receipted and sent; the provider segment
    spans the whole stream while only `word_ranges` count as evidence.
    """
    timeline = CaptureTimeline(sample_rate=RATE)
    source = SourcePositionMap(committed=True)
    epoch = ProviderEpochTranslator(timeline, RATE)
    for i in range(frames):
        payload = _frame_bytes(i, FRAME_SAMPLES)
        timeline.accept(payload, wall0 + (i + 1) * FRAME_SAMPLES / RATE, float(i))
        source.accept(
            {'capture_root': ROOT, 'clock_epoch': EPOCH, 'source_frame': i},
            sample_start=i * FRAME_SAMPLES,
            sample_count=FRAME_SAMPLES,
            rate_hz=RATE,
            payload=payload,
            receipt_wall_time=wall0 + (i + 1) * FRAME_SAMPLES / RATE,
        )
        epoch.note_accepted(i * FRAME_SAMPLES, FRAME_SAMPLES)
    segment = {
        'id': 'live-seg',
        'speaker': 'SPEAKER_00',
        'start': 0.0,
        'end': frames * FRAME_SAMPLES / RATE,
        'text': 'live words',
        'is_user': False,
    }
    if word_ranges is not None:
        segment['_provider_word_ranges'] = list(word_ranges)
    translated = epoch.translate([segment])
    assert len(translated) == 1
    source.remember_transcripts(translated)
    return source.committed_snapshot(
        'conv', [SimpleNamespace(id='live-seg', text='live words', start=0.0, end=5.0, audio_alignment=None)]
    )


@pytest.mark.asyncio
async def test_omitted_middle_phrase_survives_committed_word_coverage(real_pipeline, monkeypatch, tmp_path):
    """Word evidence proves only what was transcribed: a live segment spanning
    0..5s whose recognized words cover 0..1.5s and 3.5..5s proves frames 0-2
    and 7-9 only, so the omitted middle phrase reaches the provider and saves."""
    pipeline = real_pipeline
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    _coverage_env(monkeypatch)
    env = _word_envelope_via_real_translator([(0.0, 1.5), (3.5, 5.0)])

    def word(value):
        return f'new-word-{value}' if 3 <= value <= 6 else f'live-word-{value}'

    row = live_row(
        started_at=at(1760000000),
        finished_at=at(1760000005.0),
        transcript_segments=[
            {
                'start': 0.0,
                'end': 5.0,
                'text': 'live words',
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'is_user': False,
            }
        ],
    )
    store = seeded_store([row])
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)], word=word)
    await _run_real(pipeline, tmp_path, target_conversation_id=row['id'])

    texts = _stored_texts(store, row)
    for omitted in (3, 4, 5, 6):
        assert f'new-word-{omitted}' in texts
    assert 'live words' in texts
    assert len(state.processed_paths) == 1
    payload = _read_payload(state.processed_paths[0])
    for omitted in (3, 4, 5, 6):
        assert _frame_bytes(omitted, FRAME_SAMPLES) in payload
    assert env is not None and env.get('proof') == 'committed_transcript_v1'
    assert [(r['source_frame_start'], r['source_frame_end']) for r in env['runs']] == [(0, 3), (7, 10)]
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_span_only_live_result_retains_all_wal_audio(real_pipeline, monkeypatch, tmp_path):
    """A live segment carrying no recognized-word intervals cannot prove
    anything: the committed snapshot abstains, the unknown envelope keeps
    every WAL frame for the provider, and all new words persist."""
    pipeline = real_pipeline
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    _coverage_env(monkeypatch)
    env = _word_envelope_via_real_translator(None) or unknown_envelope('missing_source_position', origin='live')

    def word(value):
        return f'new-word-{value}'

    row = live_row(started_at=at(1760000000), finished_at=at(1760000005.0), transcript_segments=[])
    store = seeded_store([row])
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    state = _wire_real(pipeline, monkeypatch, tmp_path, lineage_rows=[generation(1, capture_evidence=env)], word=word)
    await _run_real(pipeline, tmp_path, target_conversation_id=row['id'])

    texts = _stored_texts(store, row)
    assert sorted(texts) == sorted(word(i) for i in range(10))
    assert len(state.processed_paths) == 1
    assert _read_payload(state.processed_paths[0]) == b''.join(_frame_bytes(v, FRAME_SAMPLES) for v in range(10))
    assert env.get('proof') != 'committed_transcript_v1'
    assert state.outcomes[-1].value == 'success'
