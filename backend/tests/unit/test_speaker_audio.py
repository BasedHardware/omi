"""Synthetic sample-identifiable PCM through the actual storage iterator and clip reader."""

import time
from types import SimpleNamespace

import numpy as np
import pytest
from google.api_core.exceptions import RetryError, ServiceUnavailable

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

    class Blob:
        def __init__(self, path):
            self.path = path

        def download_as_bytes(self, **kwargs):
            data = next(entry['pcm'] for entry in entries if entry['path'] == self.path)
            if data is None:
                raise storage.NotFound('synthetic missing blob')
            return data

    monkeypatch.setattr(
        storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: SimpleNamespace(blob=Blob))
    )
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
            else f'chunks/synthetic-user/synthetic-conversation/{ORIGIN + start:.3f}.bin'
        )
        entries.append(
            {
                'timestamp': ORIGIN + start,
                'path': path,
                'pcm': None if missing else pcm(start, end),
                'is_batch': batch,
                'size': len(pcm(start, end)),
                **(
                    {'span': {'start': ORIGIN + start, 'samples': round((end - start) * RATE), 'sample_rate': RATE}}
                    if not batch
                    else {}
                ),
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
    assert reads == [f'chunks/synthetic-user/synthetic-conversation/{ORIGIN + offset:.3f}.bin' for offset in (305, 300)]


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
    assert extract(7, 12) is None  # main selected only the shorter newer blob
    assert reads == [f'chunks/synthetic-user/synthetic-conversation/{ORIGIN + 5:.3f}.bin']


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
    result = speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', start, start + 10, timestamps=[start])
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
    assert (base_count, head_count) == (4, 1)  # main probes opus.enc, enc, opus, bin


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
        assert kwargs['retry'] is None  # outer SDK retry refreshes the leaf budget
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
def test_resource_limits_return_no_clip(memory_bucket, monkeypatch, limit):
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
    assert result is None
    assert not memory_bucket.reads
    assert session.limit_hit


def test_decode_failure_distinguished_from_missing_and_unverified_batch(memory_bucket):
    memory_bucket.add(ORIGIN, 10, enhanced=True)
    blob = next(iter(memory_bucket.objects.values()))
    blob.data = b'invalid ciphertext'
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    assert session.fetch(blob.name) is None
    assert session.reason == 'decode_failed'
    counter = speaker_audio.OMI_SPEAKER_CLIP_COVERAGE_TOTAL
    label = counter.labels(outcome='compatibility', reason='uncertain_timing', caller='owner_confirmation')
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


def test_16khz_adjacent_rounded_chunks_equal_main(memory_bucket):
    start = ORIGIN + 0.1234
    first = memory_bucket.add(start, 4.0002)
    second = memory_bucket.add(start + 4.0002, 6)
    result = speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', start, start + 10.0002)
    assert result is not None
    timestamps = [round(start, 3), round(start + 4.0002, 3)]
    merged = storage.download_audio_chunks_and_merge('synthetic-user', 'synthetic', timestamps)
    offset = round(start * 16000) - round(timestamps[0] * 16000)
    sample_count = round((start + 10.0002) * 16000) - round(start * 16000)
    assert result == merged[offset * 2 : (offset + sample_count) * 2]


def test_clip_sample_count_rounds_start_and_end_independently(memory_bucket):
    start = ORIGIN + 0.0001
    memory_bucket.add(ORIGIN, 11, span=True)
    result = speaker_audio.legacy_speaker_clip_pcm(
        'synthetic-user', 'synthetic', start, start + 10.00004, sample_rate=16000
    )
    assert result is not None
    assert len(result) // 2 == round((start + 10.00004) * 16000) - round(start * 16000) == 160000


@pytest.mark.parametrize('enhanced', [False, True])
def test_exact_ten_second_rounded_multi_chunk_equals_main(memory_bucket, enhanced):
    start = ORIGIN + 0.1234
    first = memory_bucket.add(start, 64003 / 16000, enhanced=enhanced)
    second_start = start + 64003 / 16000
    second = memory_bucket.add(second_start, 95997 / 16000, enhanced=enhanced)
    timestamps = [start, second_start]
    main = storage.download_audio_chunks_and_merge('synthetic-user', 'synthetic', timestamps)
    result = speaker_audio.legacy_speaker_clip_pcm(
        'synthetic-user',
        'synthetic',
        start,
        start + 10,
        timestamps=timestamps,
    )
    assert result == main == first + second
    assert len(result) // 2 == 160000


@pytest.mark.parametrize('authoritative', [False, True])
def test_real_one_ms_gap_is_never_reported_covered(memory_bucket, authoritative):
    memory_bucket.add(ORIGIN, 4, span=authoritative)
    memory_bucket.add(ORIGIN + 4.001, 6, span=authoritative)
    counter = speaker_audio.OMI_SPEAKER_CLIP_COVERAGE_TOTAL
    covered = counter.labels(outcome='covered', reason='complete', caller='unknown')
    compatibility = counter.labels(outcome='compatibility', reason='uncertain_timing', caller='unknown')
    before = covered._value.get(), compatibility._value.get()
    result = speaker_audio.legacy_speaker_clip_pcm('synthetic-user', 'synthetic', ORIGIN, ORIGIN + 10)
    assert covered._value.get() == before[0]
    if authoritative:
        assert result is None
    else:
        main = storage.download_audio_chunks_and_merge('synthetic-user', 'synthetic', [ORIGIN, ORIGIN + 4.001])
        assert result == main[:320000]
        assert compatibility._value.get() == before[1] + 1


@pytest.mark.parametrize('exhausted', [False, True])
def test_authoritative_gap_never_uses_budget_escape(memory_bucket, exhausted):
    memory_bucket.add(ORIGIN, 4, span=True)
    memory_bucket.add(ORIGIN + 5, 5, span=True)
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    if exhausted:
        session.downloads = audio_chunks.MAX_SPEAKER_DOWNLOADS
    assert (
        speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user',
            'synthetic',
            ORIGIN,
            ORIGIN + 10,
            session=session,
        )
        is None
    )
    if exhausted:
        assert session.limit_hit
        assert not memory_bucket.reads


def test_transient_503_retries_and_yields_clip(memory_bucket, monkeypatch):
    from google.api_core.exceptions import ServiceUnavailable

    data = memory_bucket.add(ORIGIN, 10)
    blob = next(iter(memory_bucket.objects.values()))
    download = blob.download_as_bytes
    attempts = []

    def transient(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise ServiceUnavailable('synthetic transient 503')
        return download(**kwargs)

    monkeypatch.setattr(blob, 'download_as_bytes', transient)
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    assert (
        speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user',
            'synthetic',
            ORIGIN,
            ORIGIN + 10,
            session=session,
        )
        == data
    )
    assert len(attempts) == session.downloads == 2
    assert session.bytes == len(data) * 2
    assert session.cache[blob.name][0] == data


def test_transient_failure_is_not_negative_cached(memory_bucket, monkeypatch):
    data = memory_bucket.add(ORIGIN, 10)
    blob = next(iter(memory_bucket.objects.values()))
    download = blob.download_as_bytes
    monkeypatch.setattr(
        blob, 'download_as_bytes', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('transient transport'))
    )
    session = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    assert session.fetch(blob.name) is None
    assert blob.name not in session.cache
    monkeypatch.setattr(blob, 'download_as_bytes', download)
    assert session.fetch(blob.name) == data


def test_listing_retry_exhaustion_is_bounded_and_retryable_in_new_session(memory_bucket, monkeypatch):
    data = memory_bucket.add(ORIGIN, 10, span=True)
    bucket = memory_bucket.bucket
    real_list_blobs = bucket.list_blobs
    calls = []
    attempts = []
    retry_errors = []

    def transient_listing(prefix, *, timeout=None, retry=None, **kwargs):
        calls.append(prefix)

        def list_once():
            attempts.append(prefix)
            if len(calls) == 1:
                raise ServiceUnavailable('synthetic transient listing 503')
            return real_list_blobs(prefix, **kwargs)

        try:
            return retry(list_once)()
        except RetryError as exc:
            retry_errors.append(exc)
            raise

    monkeypatch.setattr(bucket, 'list_blobs', transient_listing)
    failed = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    failed.deadline = time.monotonic() + 0.05
    limit_label = speaker_audio.OMI_SPEAKER_CLIP_COVERAGE_TOTAL.labels(
        outcome='missing', reason='download_limit', caller='teaching'
    )
    before = limit_label._value.get()
    assert (
        speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user', 'synthetic', ORIGIN, ORIGIN + 10, session=failed, caller='teaching'
        )
        is None
    )
    assert failed.reason == 'download_limit'
    assert failed.limit_hit
    assert failed.cache == {}
    assert limit_label._value.get() == before + 1
    assert retry_errors and attempts

    succeeded = audio_chunks.AudioChunkReadSession('synthetic-user', 'synthetic')
    assert (
        speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user', 'synthetic', ORIGIN, ORIGIN + 10, session=succeeded, caller='teaching'
        )
        == data
    )
    assert len(calls) >= 2


def test_authoritative_placement_never_recovers_main_rejected_window(memory_bucket):
    # Metadata places a blob far after its legacy manifest timestamp. Main's
    # absolute trim rejects it; strict placement alone would otherwise recover it.
    data = memory_bucket.add(ORIGIN, 10, span=True)
    blob = next(iter(memory_bucket.objects.values()))
    blob.metadata = storage.span_blob_metadata({'start': ORIGIN + 100, 'samples': len(data) // 2, 'sample_rate': 16000})
    assert (
        speaker_audio.legacy_speaker_clip_pcm(
            'synthetic-user',
            'synthetic',
            ORIGIN + 100,
            ORIGIN + 110,
            timestamps=[ORIGIN],
        )
        is None
    )
