"""Synthetic sample-identifiable PCM through the actual storage iterator and clip reader."""

from types import SimpleNamespace

import numpy as np
import pytest

from utils import speaker_audio
from utils.other import storage
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
    monkeypatch.setattr(storage, 'list_audio_chunks', lambda *a: entries)

    def decode(bucket, path, uid, rate):
        assert rate == RATE
        reads.append(path)
        return next(entry['pcm'] for entry in entries if entry['path'] == path)

    monkeypatch.setattr(storage, '_download_and_decode_chunk_blob', decode)

    def add(start, end, *, missing=False, batch=False):
        path = f'synthetic/{start}-{end}.batch.bin' if batch else f'synthetic/{start}.bin'
        entries.append({'timestamp': ORIGIN + start, 'path': path, 'pcm': None if missing else pcm(start, end)})

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


def test_clip_inside_batch_uses_blob_origin_not_interior_chunk_timestamp(blobs):
    add, reads = blobs
    add(0, 30, batch=True)
    conv = {
        'id': 'synthetic',
        'started_at': ORIGIN,
        'audio_files': [{'chunk_timestamps': [ORIGIN, ORIGIN + 10, ORIGIN + 20], 'duration': 30}],
    }
    assert clips.conversation_clip_pcm('synthetic-user', conv, 12, 22, RATE) == pcm(12, 22)
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
    assert reads == ['synthetic/300.bin']


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
    before = {outcome: counter.labels(outcome=outcome)._value.get() for outcome in ['covered', 'gap', 'missing']}
    assert extract(0, 5) is not None
    assert extract(3, 13) is None
    assert extract(19, 21) is None
    assert all(counter.labels(outcome=outcome)._value.get() == value + 1 for outcome, value in before.items())
