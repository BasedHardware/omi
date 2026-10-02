"""Synthetic sample-identifiable PCM through the actual storage iterator and clip reader."""

from types import SimpleNamespace

import numpy as np
import pytest

from utils import speaker_audio
from tests.unit.fixtures.audio_chunk_storage import memory_bucket
from utils.other import storage
from utils.other import audio_chunks
from utils.speaker_tag_prompts import clips

RATE = 100
ORIGIN = 1700000000.0


def pcm(start, end):
    return np.arange(round(start * RATE), round(end * RATE), dtype=np.int16).tobytes()


@pytest.fixture
def blobs(monkeypatch):
    entries = []
    reads = []
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: object()))
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda *a, **kwargs: entries)

    def decode(bucket, path, uid, rate, **kwargs):
        assert rate == RATE
        reads.append(path)
        return next(entry['pcm'] for entry in entries if entry['path'] == path)

    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', decode)

    def add(start, end, *, missing=False, batch=False):
        path = (
            f'chunks/synthetic-user/synthetic/{ORIGIN + start:.3f}-{ORIGIN + end:.3f}.batch.bin'
            if batch
            else f'synthetic/{start}.bin'
        )
        entries.append(
            {
                'timestamp': ORIGIN + start,
                'path': path,
                'pcm': None if missing else pcm(start, end),
                'is_batch': batch,
                'size': len(pcm(start, end)),
            }
        )

    return add, reads


def extract(start, end):
    return speaker_audio.legacy_speaker_clip_pcm(
        'synthetic-user', 'synthetic-conversation', ORIGIN + start, ORIGIN + end, RATE
    )


def test_overlap_does_not_repeat_samples_or_shift_later_voice(blobs):
    add, reads = blobs
    add(0, 8)
    add(5, 14)
    assert extract(3, 13) == pcm(3, 13)
    assert len(reads) == 2


def test_legacy_batch_keeps_main_timing_without_claiming_verified_coverage(blobs):
    add, reads = blobs
    add(0, 30, batch=True)
    conv = {
        'id': 'synthetic',
        'started_at': ORIGIN,
        'audio_files': [{'chunk_timestamps': [ORIGIN, ORIGIN + 10, ORIGIN + 20], 'duration': 30}],
    }
    assert clips.conversation_clip_pcm('synthetic-user', conv, 2, 12, RATE) == pcm(2, 12)
    assert len(reads) == 1


@pytest.mark.parametrize('case', ['leading', 'interior', 'trailing', 'missing_blob', 'all_missing'])
def test_incomplete_windows_never_yield_partial_or_padded_audio(blobs, case):
    add, _ = blobs
    if case == 'leading':
        add(4, 15)
    elif case == 'interior':
        add(0, 7)
        add(8, 15)
    elif case == 'trailing':
        add(0, 12)
    elif case == 'missing_blob':
        add(0, 7)
        add(7, 15, missing=True)
    else:
        add(0, 15, missing=True)
    assert extract(3, 13) is None


def test_small_gap_is_not_rounded_into_continuous_speech(blobs):
    add, _ = blobs
    add(0, 7)
    add(7.01, 15)
    assert extract(3, 13) is None


def test_far_windows_skip_unrelated_blobs_and_stop_after_complete_coverage(blobs):
    add, reads = blobs
    for start in [0, 100, 200, 300, 305, 400]:
        add(start, start + 20)
    assert extract(302, 312) == pcm(302, 312)
    assert reads == ['synthetic/305.bin', 'synthetic/300.bin']


def test_overlap_is_trimmed_on_integer_sample_grid(blobs):
    add, _ = blobs
    add(0, 5.03)
    add(5.01, 15)
    assert extract(3.01, 13.01) == pcm(3.01, 13.01)


@pytest.mark.parametrize('start,end', [(0, 13), (5, 5), (5, 4), (float('nan'), 5), (0, float('inf'))])
def test_invalid_windows_do_no_storage_work(blobs, start, end):
    _, reads = blobs
    assert extract(start, end) is None
    assert not reads


def test_outcomes_have_only_bounded_labels(blobs):
    add, _ = blobs
    add(0, 8)
    add(9, 20)
    counter = speaker_audio.OMI_SPEAKER_CLIP_COVERAGE_TOTAL
    before = {
        outcome: counter.labels(
            outcome=outcome,
            reason={'covered': 'complete', 'gap': 'gap', 'missing': 'missing_blob'}[outcome],
            caller='unknown',
        )._value.get()
        for outcome in ['covered', 'gap', 'missing']
    }
    assert extract(0, 5) is not None
    assert extract(3, 13) is None
    assert extract(19, 21) is None
    assert all(
        counter.labels(
            outcome=outcome,
            reason={'covered': 'complete', 'gap': 'gap', 'missing': 'missing_blob'}[outcome],
            caller='unknown',
        )._value.get()
        == value + 1
        for outcome, value in before.items()
    )


def test_earlier_long_blob_fills_coverage_after_shorter_newer_blob(blobs):
    add, reads = blobs
    add(0, 15)
    add(5, 8)
    assert extract(7, 12) == pcm(7, 12)
    assert reads == ['synthetic/5.bin', 'synthetic/0.bin']


def test_missing_downloads_are_bounded(blobs):
    add, reads = blobs
    for start in range(40):
        add(start, start + 10, missing=True)
    assert extract(40, 50) is None
    assert len(reads) <= speaker_audio.MAX_SPEAKER_CLIP_BLOBS


def test_unverified_batch_direct_reader_keeps_main_compatibility(blobs):
    add, reads = blobs
    add(0, 15, batch=True)
    assert extract(7, 12) == pcm(7, 12)
    assert len(reads) == 1


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_real_live_uploader_batches_remain_readable(memory_bucket, protection):
    parts = [
        {'timestamp': ORIGIN + offset, 'data': np.full(16000 * 5, offset + 1, dtype=np.int16).tobytes()}
        for offset in (0, 5, 10)
    ]
    paths = storage.upload_audio_chunks_batch(parts, 'synthetic-user', 'synthetic', data_protection_level=protection)
    conv = {
        'id': 'synthetic',
        'started_at': ORIGIN,
        'audio_files': [{'chunk_timestamps': [p['timestamp'] for p in parts], 'duration': 15}],
    }
    expected = storage.download_audio_chunks_and_merge('synthetic-user', 'synthetic', [p['timestamp'] for p in parts])
    assert clips.conversation_clip_pcm('synthetic-user', conv, 2, 12) == expected[2 * 32000 : 12 * 32000]


@pytest.mark.parametrize('enhanced', [False, True])
@pytest.mark.parametrize('span', [False, True])
@pytest.mark.parametrize('fraction', [0.1234, 0.1236])
def test_16khz_boundary_aligned_rounded_filename(memory_bucket, enhanced, span, fraction):
    start = ORIGIN + fraction
    data = memory_bucket.add(start, 10, enhanced=enhanced, span=span)
    result = speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', start, start + 10)
    # Historical timestamp-only windows may lose <= 0.5ms at a boundary, never gain silence.
    assert result is not None
    assert len(data) - 16 <= len(result) <= len(data)
    assert result in data


def test_missing_window_download_count_base_vs_head(memory_bucket):
    for offset in range(40):
        memory_bucket.add(ORIGIN + offset * 20, 5)
    # Main chooses the nearest predecessor, rather than all 40 old blobs.
    storage.download_audio_chunks_and_merge('synthetic-user', 'synthetic', [ORIGIN + 780])
    base_count = len(memory_bucket.reads)
    memory_bucket.reads.clear()
    assert speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', ORIGIN + 800, ORIGIN + 810) is None
    head_count = len(memory_bucket.reads)
    assert (base_count, head_count) == (4, 0)  # main probes opus.enc, enc, opus, bin


def test_failure_reason_and_caller_labels(memory_bucket):
    counter = speaker_audio.OMI_SPEAKER_CLIP_COVERAGE_TOTAL
    before = counter.labels(outcome='missing', reason='missing_blob', caller='preview')._value.get()
    assert (
        speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', ORIGIN, ORIGIN + 10, caller='preview')
        is None
    )
    assert counter.labels(outcome='missing', reason='missing_blob', caller='preview')._value.get() == before + 1


def test_shared_listing_cache_and_download_semaphore(memory_bucket, monkeypatch):
    data = memory_bucket.add(ORIGIN, 20)
    held = []

    class Semaphore:
        def acquire(self, **kwargs):
            assert not held
            held.append(True)
            return True

        def release(self):
            assert held.pop()

    monkeypatch.setattr(storage, '_STORAGE_CHUNK_SEM', Semaphore())
    blob = next(iter(memory_bucket.objects.values()))
    real_download = blob.download_as_bytes

    def download(**kwargs):
        assert held == [True]
        assert kwargs['retry'] is None
        assert 0 < kwargs['timeout'] <= audio_chunks.MAX_SPEAKER_READ_SECONDS
        return real_download(**kwargs)

    monkeypatch.setattr(blob, 'download_as_bytes', download)
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    for start in (0, 5, 10):
        result = speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user', 'synthetic', ORIGIN + start, ORIGIN + start + 5, session=session, caller='teaching'
        )
        assert result == data[start * 32000 : (start + 5) * 32000]
    assert len(memory_bucket.listings) == len(memory_bucket.reads) == 1
    assert session.downloads == 1 and session.bytes == len(data)
    assert not held


@pytest.mark.parametrize('limit', ['downloads', 'bytes', 'time'])
def test_search_limits_do_not_remove_main_clips(memory_bucket, monkeypatch, limit):
    data = memory_bucket.add(ORIGIN, 10)
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    if limit == 'downloads':
        monkeypatch.setattr(audio_chunks, 'MAX_SPEAKER_DOWNLOADS', 0)
    elif limit == 'bytes':
        monkeypatch.setattr(audio_chunks, 'MAX_SPEAKER_BYTES', len(data) - 1)
    else:
        session.deadline = 0
    # New search is bounded. The explicitly measured main-selected path is the
    # compatibility exception demanded by the governing no-clip-loss rule.
    path = next(iter(memory_bucket.objects))
    assert session.fetch(path) is None
    assert session.reason == 'download_limit'
    assert not memory_bucket.reads
    result = speaker_audio.legacy_speaker_clip_pcm(
        'synthetic-user',
        'synthetic',
        ORIGIN,
        ORIGIN + 10,
        session=session,
        timestamps=[ORIGIN],
        caller='teaching',
    )
    assert result == data
    assert len(memory_bucket.reads) == 1 and session.compatibility_escape


def test_decode_failure_distinguished_from_missing_and_unverified_batch(memory_bucket):
    memory_bucket.add(ORIGIN, 10, enhanced=True)
    blob = next(iter(memory_bucket.objects.values()))
    blob.data = b'invalid ciphertext'
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    assert session.fetch(blob.name) is None
    assert session.reason == 'decode_failed'
    counter = speaker_audio.OMI_SPEAKER_CLIP_COVERAGE_TOTAL
    label = counter.labels(outcome='compatibility', reason='unverified_batch', caller='owner_confirmation')
    before = label._value.get()
    parts = [{'timestamp': ORIGIN, 'data': b'\x01\x00' * 160000}]
    storage.upload_audio_chunks_batch(parts, 'synthetic-user', 'synthetic', data_protection_level='standard')
    assert (
        speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user',
            'synthetic',
            ORIGIN,
            ORIGIN + 10,
            timestamps=[ORIGIN],
            caller='owner_confirmation',
        )
        == parts[0]['data']
    )
    assert label._value.get() == before + 1


def test_authoritative_truncation_is_not_timestamp_uncertainty(memory_bucket):
    start = ORIGIN + 0.1234
    memory_bucket.add(start, 10 - 6 / 16000, span=True)
    assert speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', start, start + 10) is None


def test_16khz_adjacent_rounded_chunks_do_not_insert_silence(memory_bucket):
    start = ORIGIN + 0.1234
    first = memory_bucket.add(start, 4.0002)
    second = memory_bucket.add(start + 4.0002, 6)
    result = speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', start, start + 10.0002)
    assert result is not None
    assert len(first + second) - 32 <= len(result) <= len(first + second)
    assert b'\x00\x00' not in [result[i : i + 2] for i in range(0, len(result), 2)]
