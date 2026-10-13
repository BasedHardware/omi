"""Synthetic dual-writer regression: clock skew, recovery gaps and 190 repeats.

Every phrase and audio sample is synthetic; no incident customer data.
"""

import asyncio
from unittest.mock import MagicMock
import wave

import numpy as np
import pytest

from utils.sync import safety_wal_coverage as coverage
from utils.sync.merge_dedupe import dedupe_segments_for_merge

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
    return dict(text=text, timestamp=timestamp, start=timestamp - T, end=timestamp - T + duration)


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
    assert skipped == pytest.approx(26)
    assert saved == 26 * 32000
    # One-second margins retain initial/end edges and the actual ten-second gap.
    assert len(outputs) == 3
    middle = outputs[1]
    assert coverage.get_timestamp_from_path(middle) == pytest.approx(T + 35 + 19)
    with wave.open(middle, 'rb') as source:
        assert source.readframes(source.getnframes()) == pcm[19 * 32000 : 31 * 32000]


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
    assert (
        dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, text_match_slop_seconds=60)
        == incoming[1:]
    )
    assert (
        dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=False, text_match_slop_seconds=60) == incoming
    )


def test_explicit_offset_is_used_in_overlap_match():
    live = [segment('Please bring the blue notebook to our planning meeting', T)]
    incoming = [segment('please bring a blue notebook to our planning meeting', T + 80)]
    assert not dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, estimated_offset_seconds=-80)
    assert dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, text_match_slop_seconds=60) == incoming


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
def test_legacy_audio_trim_nested_chunk_does_not_rewind_clock(storage, monkeypatch, fill_gaps):
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    data = {T: b'\x01\x00' * 16000 * 10, T + 2: b'\x02\x00' * 16000 * 2, T + 8: b'\x03\x00' * 16000 * 5}
    chunks = [dict(timestamp=t, path=f'{t}.bin') for t in data]
    result = storage.download_audio_chunks_and_merge(
        'synthetic',
        'live',
        list(data),
        fill_gaps=fill_gaps,
        listed_chunks=chunks,
        chunk_loader=lambda p: data[float(p.rsplit('/', 1)[-1][:-4])] if p.endswith('.bin') else None,
    )
    assert result == data[T] + data[T + 8][2 * 32000 :]
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'off')
    old = storage.download_audio_chunks_and_merge(
        'synthetic',
        'live',
        list(data),
        fill_gaps=fill_gaps,
        listed_chunks=chunks,
        chunk_loader=lambda p: data[float(p.rsplit('/', 1)[-1][:-4])] if p.endswith('.bin') else None,
    )
    assert len(old) > len(result)


def test_batch_provider_stamp():
    from utils.stt.pre_recorded import postprocess_words

    words = [
        dict(text=word, timestamp=[i, i + 0.5], speaker='SPEAKER_0')
        for i, word in enumerate('we should finish this synthetic task tomorrow'.split())
    ]
    segments = postprocess_words(words, 0, stt_provider='parakeet')
    assert segments and all(segment.stt_provider == 'parakeet' for segment in segments)


def test_revision_does_not_zero_live_slop(monkeypatch):
    from tests.unit.test_sync_cross_job_assignment import chunk, intake
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'true')
    store = StrictFirestore()
    live = chunk('live', T, text='We should deliver the revised project plan tomorrow.')
    live.update(sync_live_target=True, sync_content_revision=5)
    store.rows[('users', 'u', 'conversations', 'live')] = live
    incoming = chunk('wal', T + 35, text='we should deliver a revised project plan tomorrow')
    result, created, survivors = intake(store, incoming, target_id='live')
    assert not created and not survivors
    assert len(result['transcript_segments']) == 1


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

    def cut(uid, candidate, source):
        assert candidate is row
        outputs = coverage._materialize(source, [(19, 31)], 35)
        return outputs, 'energy_match', 28, 28 * 32000

    monkeypatch.setattr(coverage, 'cut_live_coverage', cut)

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
    incoming = [segment('we should deliver a revised project plan tomorrow after checking all requirements', T + 35)]
    assert not dedupe_segments_for_merge(T, live, incoming, fuzzy_live_overlap=True, text_match_slop_seconds=60)
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
