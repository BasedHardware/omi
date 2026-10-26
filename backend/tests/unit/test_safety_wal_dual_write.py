"""Synthetic dual-writer regression: clock skew, recovery gaps and 190 repeats.

Every phrase and audio sample is synthetic; no incident customer data.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import wave

import numpy as np
import pytest

from utils.sync import safety_wal_coverage as coverage
from utils.sync.merge_dedupe import dedupe_segments_for_merge, fuzzy_live_match
from tests.unit.test_sync_cross_job_assignment import independent_job_pipeline
from tests.unit.test_wal_audio_coverage_pipeline import coordinator

T = 1760000000.0


@pytest.fixture(scope='module', autouse=True)
def load_dependencies():
    from utils.stt import pre_recorded
    from utils.sync import assignment


def pcm_envelope(seed, seconds=20):
    rng = np.random.default_rng(seed)
    amplitudes = rng.integers(100, 14000, seconds * 10).astype('<i2')
    return np.repeat(amplitudes, coverage.HOP).tobytes()


def wav_file(tmp_path, pcm, timestamp=T):
    path = tmp_path / f'wal_{timestamp}.wav'
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(coverage.RATE)
        out.writeframes(pcm)
    return str(path)


def segment(text, timestamp, duration=8):
    return dict(
        text=text, timestamp=timestamp, start=timestamp - T, end=timestamp - T + duration, person_id='synthetic-person'
    )


@pytest.mark.parametrize('skew', [-35, 0, 35])
def test_energy_probe_recovers_clock_skew(skew):
    wal = coverage.energy_envelope(pcm_envelope(1))
    assert coverage.estimate_offset(wal, T, [(T + skew, wal)]) == pytest.approx(skew)
    assert coverage.uncovered_intervals(T, 20, [(T + skew - 2, T + skew + 22)], skew) == []


def test_ambiguous_or_silent_probes_preserve_audio():
    wal = coverage.energy_envelope(pcm_envelope(2))
    assert coverage.estimate_offset(wal, T, [(T, wal), (T + 20, wal)]) is None
    assert coverage.estimate_offset(np.zeros(100), T, [(T, np.zeros(100))]) is None
    assert coverage.uncovered_intervals(T, 10, [(T, T + 100)], None) == [(0, 10)]


def test_real_gap_and_adjacent_chunk_boundaries_are_kept():
    # Coverage is unioned before erosion; there is no fake hole at +10.
    assert coverage.uncovered_intervals(T, 40, [(T - 2, T + 10), (T + 10, T + 20), (T + 30, T + 42)], 0) == [(19, 31)]
    assert coverage.uncovered_intervals(T, 10, [(T - 30, T - 5)], 0) == [(0, 10)]


@pytest.fixture
def storage(monkeypatch):
    from utils.other import storage

    monkeypatch.setattr(storage, 'storage_client', MagicMock())
    return storage


@pytest.mark.parametrize('spans', [True, False])
def test_cut_uses_span_or_decoded_duration_and_keeps_recovery_gap(tmp_path, storage, monkeypatch, spans):
    pcm = pcm_envelope(3, 40)
    path = wav_file(tmp_path, pcm)
    chunks = [dict(timestamp=T + 35, path='one', size=100), dict(timestamp=T + 65, path='two', size=100)]
    payloads = {'one': pcm[: 20 * 32000], 'two': pcm[30 * 32000 :]}
    if spans:
        for chunk in chunks:
            chunk['span'] = dict(start=chunk['timestamp'], samples=len(payloads[chunk['path']]) // 2, sample_rate=16000)
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda *args, **kwargs: chunks)
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', lambda bucket, path, *args, **kwargs: payloads[path])
    outputs, reason, skipped, saved = coverage.cut_live_coverage('synthetic', {'id': 'live'}, path)
    assert reason == 'energy_match'
    assert skipped == pytest.approx(20)
    assert saved == 20 * 32000
    # One-second margins retain initial/end edges and the actual ten-second gap.
    assert len(outputs) == 3
    middle = outputs[1]
    assert coverage.get_timestamp_from_path(middle) == pytest.approx(T + 35 + 17)
    with wave.open(middle, 'rb') as source:
        assert source.readframes(source.getnframes()) == pcm[17 * 32000 : 31 * 32000]


def test_unreliable_probe_never_discards_genuine_gap(tmp_path, storage, monkeypatch):
    path = wav_file(tmp_path, pcm_envelope(4, 10))
    monkeypatch.setattr(
        storage, 'list_audio_chunks', lambda *args, **kwargs: [dict(timestamp=T, path='other', size=10)]
    )
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', lambda *args, **kwargs: pcm_envelope(5, 10))
    assert coverage.cut_live_coverage('synthetic', {'id': 'live'}, path) == ([path], 'unreliable_clock', 0, 0)


def test_fuzzy_parakeet_modulate_with_gap_and_short_phrase():
    live = [segment('We should deliver the revised project plan tomorrow.', T)]
    incoming = [
        segment('we should deliver a revised project plan tomorrow', T + 35),
        segment('A completely new discussion about gardening begins here', T + 50),
        segment('yeah okay', T + 36),
    ]
    # Neither a one-word change nor one line alone is sufficient evidence.
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True) == incoming
    assert (
        dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=-35) == incoming
    )


def test_explicit_offset_is_used_in_overlap_match():
    text = 'Please bring the blue notebook to our planning meeting'
    live, incoming = [segment(text, T)], [segment(text.lower(), T + 80)]
    assert not dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=-80)
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True) == incoming


def test_synthetic_october_01_shape_190_segments():
    # Distinct synthetic utterances across a long conversation; provider punctuation
    # and one article differ, with the observed +35-second skew.
    live, wal = [], []
    for i in range(190):
        text = f'Please archive synthetic folder {i} with label code{i} after checking item{i}'
        live.append(segment(text + '.', T + i * 12))
        wal.append(segment(text.replace('the ', 'a ').lower(), T + i * 12 + 35))
    assert not dedupe_segments_for_merge(T, live, wal, fuzzy_live_overlap=True, text_match_slop_seconds=60)


@pytest.mark.parametrize('fill_gaps', [True, False])
@pytest.mark.parametrize('wal_offset', [40, 80, 110])
def test_legacy_playback_keeps_gap_speech_even_at_overlapping_timestamps(storage, monkeypatch, fill_gaps, wal_offset):
    data = {T: b'\x01\x00' * 16000 * 30, T + 70: b'\x02\x00' * 16000 * 50, T + wal_offset: b'\x03\x00' * 16000 * 20}
    chunks = [dict(timestamp=t, path=f'{t}.bin') for t in data]
    results = []
    for flag in ('off', 'true'):
        monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', flag)
        results.append(
            storage.download_audio_chunks_and_merge(
                'synthetic',
                'live',
                sorted(data),
                fill_gaps=fill_gaps,
                listed_chunks=chunks,
                chunk_loader=lambda p: data[float(p.rsplit('/', 1)[-1][:-4])] if p.endswith('.bin') else None,
            )
        )
    assert results[0] == results[1]
    assert data[T + wal_offset] in results[1]


@pytest.mark.parametrize('flag, expected', [('true', 'parakeet'), ('off', None)])
def test_batch_provider_stamp(independent_job_pipeline, monkeypatch, flag, expected):
    import threading
    from tests.unit.test_sync_cross_job_assignment import intake
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', flag)
    pipeline, transcript_segment, lifecycle = independent_job_pipeline
    store = StrictFirestore()
    pipeline.get_syncing_file_temporal_signed_url = lambda path: path
    pipeline.get_prerecorded_service = lambda language: ('test', None, 'parakeet')
    pipeline.prerecorded = lambda *a, **kw: ([{}], 'en')
    pipeline.postprocess_words = lambda *a: [
        transcript_segment.TranscriptSegment(
            text='This narrated chapter describes our synthetic history.',
            start=0,
            end=9.5,
            speaker='SPEAKER_00',
            is_user=False,
        )
    ]
    pipeline.identify_speakers_for_segments = lambda *a, **kw: None
    pipeline.get_timestamp_from_path = float
    pipeline.get_wav_duration = lambda path: 60
    pipeline.get_closest_conversation_to_timestamps = lambda *args: None
    lifecycle.ingest_sync_conversation = lambda uid, incoming, **kw: intake(store, incoming, **kw)
    assert pipeline.process_segment(
        str(T), 'u', {'new_memories': set(), 'updated_memories': set()}, threading.Lock(), []
    )
    rows = [value for key, value in store.rows.items() if key[2] == 'conversations']
    assert rows[0]['transcript_segments'][0].get('stt_provider') == expected


def test_revision_does_not_zero_live_slop(monkeypatch):
    from tests.unit.test_sync_cross_job_assignment import chunk, intake
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    store = StrictFirestore()
    first = 'Please bring the blue notebook to our planning meeting'
    second = 'Our synthetic budget discussion needs a separate exact transcript anchor'
    live = chunk('live', T, text=first)
    live.update(sync_live_target=True, sync_content_revision=5)
    live['transcript_segments'] = [
        dict(segment(first, T), start=0, end=8),
        dict(segment(second, T + 10), start=10, end=18),
    ]
    store.rows[('users', 'u', 'conversations', 'live')] = live
    incoming = chunk('wal', T + 35, text=first)
    incoming['transcript_segments'] = [
        dict(segment(first.lower(), T + 35), start=0, end=8),
        dict(segment(second.lower(), T + 45), start=10, end=18),
    ]
    result, created, survivors = intake(store, incoming, target_id='live')
    assert not created and not survivors
    assert len(result['transcript_segments']) == 2


@pytest.mark.parametrize('flag', ['off', 'typo', 'false'])
def test_kill_switch_preserves_original_path(tmp_path, monkeypatch, flag):
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', flag)
    path = wav_file(tmp_path, pcm_envelope(6, 10))

    async def forbidden(*args, **kwargs):
        raise AssertionError('kill switch must not perform lookups')

    assert asyncio.run(
        coverage.apply_safety_wal_coverage(
            'synthetic',
            [path],
            'live',
            run_blocking=forbidden,
            db_executor=None,
            storage_executor=None,
            job_ref='synthetic',
        )
    ) == ([path], set())


def test_pre_stt_orchestration_only_publishes_uncovered_paths(tmp_path, monkeypatch, caplog):
    from database import conversations
    from utils.sync.safety_wal_metrics import WAL_SECONDS_SKIPPED, AUDIO_BYTES_NOT_STORED

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    pcm = pcm_envelope(7, 40)
    path = wav_file(tmp_path, pcm)
    row = dict(id='live', source='omi', client_device_id='pendant', is_locked=False)
    monkeypatch.setattr(conversations, 'get_conversation', lambda *args: row)

    def cut(uid, candidate, source, snapshot):
        assert candidate is row
        outputs = coverage._materialize(source, [(19, 31)], 35)
        return outputs, 'energy_match', 28, 28 * 32000

    monkeypatch.setattr(coverage, 'cut_live_coverage', cut)
    monkeypatch.setattr(coverage, 'load_live_coverage', lambda *args: coverage.LiveCoverage())

    async def worker(pool, fn, *args):
        return fn(*args)

    seconds = WAL_SECONDS_SKIPPED.labels(reason='energy_match')._value.get()
    saved = AUDIO_BYTES_NOT_STORED.labels(reason='energy_match')._value.get()
    with caplog.at_level('INFO'):
        outputs, generated = asyncio.run(
            coverage.apply_safety_wal_coverage(
                'synthetic',
                [path],
                'live',
                run_blocking=worker,
                db_executor=None,
                storage_executor=None,
                job_ref='synthetic',
                capture_partition=row,
            )
        )
    assert path not in outputs and generated == set(outputs)
    assert coverage.get_wav_duration(outputs[0]) == 12
    assert WAL_SECONDS_SKIPPED.labels(reason='energy_match')._value.get() - seconds == 28
    assert AUDIO_BYTES_NOT_STORED.labels(reason='energy_match')._value.get() - saved == 28 * 32000
    assert 'event=sync_safety_wal_coverage job_ref=synthetic' in caplog.text


def test_incompatible_target_is_never_coverage_authority(tmp_path, monkeypatch):
    from database import conversations

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    path = wav_file(tmp_path, pcm_envelope(8, 10))
    row = dict(id='live', source='desktop', client_device_id='other', is_locked=False)
    monkeypatch.setattr(conversations, 'get_conversation', lambda *args: row)

    def forbidden(*args):
        raise AssertionError('incompatible capture cannot authorize coverage')

    monkeypatch.setattr(coverage, 'cut_live_coverage', forbidden)

    async def worker(pool, fn, *args):
        return fn(*args)

    assert asyncio.run(
        coverage.apply_safety_wal_coverage(
            'synthetic',
            [path],
            'live',
            run_blocking=worker,
            db_executor=None,
            storage_executor=None,
            job_ref='synthetic',
            capture_partition=dict(source='omi', client_device_id='pendant', is_locked=False),
        )
    ) == ([path], set())


def test_fuzzy_match_spans_two_live_segment_boundaries():
    live = [
        segment('We should deliver the revised project', T, 4),
        segment('plan tomorrow after checking all requirements', T + 4, 4),
    ]
    incoming = [segment('we should deliver the revised project plan tomorrow after checking all requirements', T + 35)]
    assert not dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=-35)
    # A pause cannot turn separate unrelated lines into one lexical match.
    live[1]['timestamp'] += 30
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, text_match_slop_seconds=60) == incoming


def test_spanless_batch_cannot_hide_internal_recovery_gap(tmp_path, storage, monkeypatch):
    pcm = pcm_envelope(9, 10)
    path = wav_file(tmp_path, pcm)
    monkeypatch.setattr(
        storage, 'list_audio_chunks', lambda *args, **kwargs: [dict(timestamp=T, path='batch', size=10, is_batch=True)]
    )
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', lambda *args, **kwargs: pcm)
    assert coverage.cut_live_coverage('synthetic', {'id': 'live'}, path) == ([path], 'unreliable_clock', 0, 0)


def test_partial_transcript_drop_counts_unstored_pcm_bytes(tmp_path):
    from utils.sync.safety_wal_metrics import suppressed_pcm_bytes

    path = wav_file(tmp_path, pcm_envelope(10, 10))
    with open(path, 'rb') as source:
        audio = source.read()
    assert suppressed_pcm_bytes(audio, [dict(start=6, end=10)]) == 6 * 32000
    assert suppressed_pcm_bytes(audio, []) == 10 * 32000
    assert suppressed_pcm_bytes(b'invalid wav', []) == 0


@pytest.mark.parametrize(
    'live_text, incoming_text',
    [
        ('Send the revised project plan tomorrow.', 'Send the revised project plan today.'),
        ('Please confirm the budget before Friday noon', 'Please confirm the budget before Friday morning'),
        (
            'Please bring the blue notebook to our planning meeting',
            'Please bring the red notebook to our planning meeting',
        ),
    ],
)
def test_one_word_change_is_kept_even_with_locked_offset(live_text, incoming_text):
    live, incoming = [segment(live_text, T)], [segment(incoming_text, T)]
    assert not fuzzy_live_match(live_text, incoming_text)
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=0) == incoming


@pytest.mark.parametrize('times', [[30], [5, 40]])
def test_later_saying_and_two_repeats_are_kept(times):
    text = 'Please bring the blue notebook to our planning meeting'
    live, incoming = [segment(text, T)], [segment(text, T + offset) for offset in times]
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True) == incoming
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=0) == incoming


def test_each_live_line_absorbs_at_most_one_incoming_line():
    text = 'Please bring the blue notebook to our planning meeting'
    live, incoming = [segment(text, T)], [segment(text, T + 35), segment(text, T + 35.5)]
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True) == incoming
    assert (
        dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=-35)
        == incoming[1:]
    )


@pytest.mark.parametrize('person', ['other-person', None])
def test_different_or_unknown_speakers_are_kept(person):
    text = 'Please bring the blue notebook to our planning meeting'
    live, incoming = [segment(text, T)], [dict(segment(text, T), person_id=person)]
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=0) == incoming


def test_two_inconsistent_text_offsets_preserve_all_speech():
    first = 'Please bring the blue notebook to our planning meeting'
    second = 'Our synthetic budget discussion needs a separate exact transcript anchor'
    live = [segment(first, T), segment(second, T + 10)]
    incoming = [segment(first, T + 35), segment(second, T + 50)]
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True) == incoming


@pytest.mark.parametrize('middle', ['silence', 'different_speech'])
def test_opening_match_does_not_suppress_unmatched_middle(tmp_path, storage, monkeypatch, middle):
    wal = pcm_envelope(20, 60)
    live = bytearray(wal)
    live[24 * 32000 : 36 * 32000] = bytes(12 * 32000) if middle == 'silence' else pcm_envelope(21, 12)
    path = wav_file(tmp_path, wal)
    monkeypatch.setattr(
        storage,
        'list_audio_chunks',
        lambda *a, **k: [
            dict(timestamp=T + 35, path='live', size=10, span=dict(start=T + 35, samples=60 * 16000, sample_rate=16000))
        ],
    )
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', lambda *a, **k: bytes(live))
    outputs, reason, skipped, _ = coverage.cut_live_coverage('synthetic', {'id': 'live'}, path)
    assert reason == 'energy_match' and 0 < skipped < 60
    # Every differing sample remains, with margins, despite the strong opening.
    payloads = []
    for output in outputs:
        with wave.open(output, 'rb') as source:
            payloads.append(source.readframes(source.getnframes()))
    assert any(wal[24 * 32000 : 36 * 32000] in payload for payload in payloads)
    assert outputs, 'the new coverage path must never authorize suppress-all success'


def test_future_slice_abstains_without_publishing_derivatives(tmp_path, storage, monkeypatch):
    now = datetime.now(timezone.utc).timestamp()
    start = now - 20
    pcm = pcm_envelope(22, 30)
    path = wav_file(tmp_path, pcm, start)
    monkeypatch.setattr(
        storage, 'list_audio_chunks', lambda *a, **k: [dict(timestamp=start + 35, path='live', size=10)]
    )
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', lambda *a, **k: pcm)
    assert coverage.cut_live_coverage('synthetic', {'id': 'live'}, path) == ([path], 'unreliable_clock', 0, 0)
    assert not list(tmp_path.glob('safety-coverage/**/*'))


def test_job_reuses_one_listing_and_probe_but_abstains_per_file(tmp_path, storage, monkeypatch):
    from database import conversations

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    row = dict(id='live', source='omi', client_device_id='pendant', is_locked=False)
    get = MagicMock(return_value=row)
    monkeypatch.setattr(conversations, 'get_conversation', get)
    pcm = pcm_envelope(23, 24)
    paths = [
        wav_file(tmp_path, pcm[: 12 * 32000], T),
        wav_file(tmp_path, pcm[12 * 32000 :], T + 12),
        wav_file(tmp_path, pcm_envelope(24, 12), T + 24),
    ]
    listing = MagicMock(return_value=[dict(timestamp=T + 35, path='live', size=10)])
    download = MagicMock(return_value=pcm)
    monkeypatch.setattr(storage, 'list_audio_chunks', listing)
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', download)

    async def worker(pool, fn, *args):
        return fn(*args)

    outputs, generated = asyncio.run(
        coverage.apply_safety_wal_coverage(
            'synthetic',
            paths,
            'live',
            run_blocking=worker,
            db_executor=None,
            storage_executor=None,
            job_ref='synthetic',
            capture_partition=row,
        )
    )
    listing.assert_called_once()
    download.assert_called_once()
    get.assert_called_once()
    assert paths[0] not in outputs and paths[1] not in outputs
    assert paths[2] in outputs and generated


def test_all_matching_audio_still_retains_boundary_paths(tmp_path, storage, monkeypatch):
    pcm = pcm_envelope(25, 24)
    path = wav_file(tmp_path, pcm)
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda *a, **k: [dict(timestamp=T + 35, path='live', size=10)])
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', lambda *a, **k: pcm)
    outputs, reason, skipped, _ = coverage.cut_live_coverage('synthetic', {'id': 'live'}, path)
    assert reason == 'energy_match' and skipped == 22
    assert len(outputs) == 2
    assert sum(coverage.get_wav_duration(output) for output in outputs) == 2


def test_word_order_change_is_not_a_duplicate():
    text = 'First send the revised project plan and then cancel the old delivery request'
    reordered = 'First cancel the revised project plan and then send the old delivery request'
    live, incoming = [segment(text, T)], [segment(reordered, T)]
    assert not fuzzy_live_match(text, reordered)
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=0) == incoming


def test_bad_wav_does_not_abort_other_job_files(tmp_path, storage, monkeypatch):
    from database import conversations

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    bad = str(tmp_path / f'wal_{T - 12}.wav')
    Path(bad).write_bytes(b'bad header')
    good = wav_file(tmp_path, pcm_envelope(26, 12))
    monkeypatch.setattr(conversations, 'get_conversation', lambda *a: {'id': 'live'})
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda *a, **k: [])

    async def worker(pool, fn, *args):
        return fn(*args)

    outputs, generated = asyncio.run(
        coverage.apply_safety_wal_coverage(
            'synthetic',
            [bad, good],
            'live',
            run_blocking=worker,
            db_executor=None,
            storage_executor=None,
            job_ref='synthetic',
        )
    )
    assert outputs == [bad, good] and not generated


@pytest.mark.asyncio
async def test_empty_cut_cannot_acknowledge_a_fully_suppressed_job(coordinator, monkeypatch, tmp_path):
    from unittest.mock import AsyncMock
    from tests.unit.test_wal_audio_coverage_pipeline import _wire, _run_batch

    module, stubs = coordinator
    pipeline = stubs['pipeline']
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'false')
    state = _wire(pipeline, monkeypatch, tmp_path, lineage_rows=[])
    cut = AsyncMock(return_value=([], set()))
    monkeypatch.setattr(pipeline, 'apply_safety_wal_coverage', cut)
    await _run_batch(module, stubs, tmp_path, claims=None, session=None)
    cut.assert_awaited_once()
    assert len(state.vad_seen) == 1 and len(state.processed) == 1
    assert state.outcomes[-1].value == 'success'  # Only after actual VAD/STT intake.
