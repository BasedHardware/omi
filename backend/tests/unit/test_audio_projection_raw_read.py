"""Framed PCM reads use the receipt table without false single-span hash misses."""

from unittest.mock import MagicMock

from utils.other import audio_outbox, raw_audio_read, storage
from utils.other.audio_raw_read_metrics import RAW_READ
from utils.other.audio_chunks import iter_audio_chunk_pcm
from utils.other.audio_frame_table import entries
import pytest
from tests.unit.test_audio_custody_frames import frame, remote


def test_framed_projection_reads_fresh_raw_without_synthetic_span_failure(remote, monkeypatch):
    first, second = b'\x01\x02' * 160, b'\x03\x04' * 160
    pcm = first + second
    frames = [frame(first, 1000), frame(second, 1003.01, 1, len(first), True)]
    receipt = audio_outbox.commit_pcm_window('owner', pcm, 'conversation', 1000, 16000, 'root', 0, frames, framed=True)
    paths = storage.upload_audio_chunks_batch(
        [{'data': pcm, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )
    before = RAW_READ.labels(result='identity_mismatch')._value.get()
    fresh = MagicMock(wraps=raw_audio_read._read_pack)
    monkeypatch.setattr(raw_audio_read, '_read_pack', fresh)
    assert storage.download_and_decode_chunk_blob(remote, paths[0], 'owner', 16000) == pcm
    assert fresh.call_count == 1 and fresh.call_args.args[1] == receipt.path
    assert RAW_READ.labels(result='identity_mismatch')._value.get() == before


def test_playback_merger_and_download_limit_read_one_object_for_two_spans(remote, monkeypatch):
    first, second = b'\x01\x02' * 160, b'\x03\x04' * 160
    pcm = first + second
    frames = [frame(first, 1000), frame(second, 1003.01, 1, len(first), True)]
    receipt = audio_outbox.commit_pcm_window('owner', pcm, 'conversation', 1000, 16000, 'root', 0, frames, framed=True)
    storage.upload_audio_chunks_batch(
        [{'data': pcm, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )
    listed = storage.list_audio_chunks('owner', 'conversation')
    download = MagicMock(wraps=storage.download_and_decode_chunk_blob)
    monkeypatch.setattr(storage, 'download_and_decode_chunk_blob', download)
    assert (
        storage.download_audio_chunks_and_merge(
            'owner',
            'conversation',
            [1000, 1003.01],
            fill_gaps=False,
            listed_chunks=listed,
            strict_sources=True,
        )
        == pcm
    )
    assert download.call_count == 1
    download.reset_mock()
    assert list(iter_audio_chunk_pcm('owner', 'conversation', lambda *args: True, max_downloads=1)) == [
        (1000, first),
        (1003.01, second),
    ]
    assert download.call_count == 1


def test_optional_forward_archive_keeps_captured_ranges_instead_of_a_synthetic_span(remote, monkeypatch):
    first, second = b'\x01\x02' * 160, b'\x03\x04' * 160
    pcm = first + second
    frames = [frame(first, 1000), frame(second, 1003.01, 1, len(first), True)]
    receipt = audio_outbox.commit_pcm_window('owner', pcm, 'conversation', 1000, 16000, 'root', 0, frames, framed=True)
    archive = MagicMock()
    monkeypatch.setattr(storage.audio_packs, 'enabled', lambda: True)
    monkeypatch.setattr(storage, '_archive_pusher_capture', archive)
    storage.upload_audio_chunks_batch(
        [{'data': pcm, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )
    archived = archive.call_args.args[0]
    assert [item['data'] for item in archived] == [first, second]
    assert [item['span']['start'] for item in archived] == [1000, 1003.01]


def test_contiguous_frame_table_stays_bounded_without_changing_original_frames():
    frames = [frame(b'\x01\x02' * 160, 1800000000 + number * 0.01, number, number * 320) for number in range(500)]
    original = [dict(item) for item in frames]
    listed = entries(frames, 16000, {'path': 'source'})
    assert len(listed) == 1 and listed[0]['span']['samples'] == 80000
    assert frames == original


@pytest.mark.parametrize('conflict', [False, True])
def test_rebatched_projection_preserves_independent_replay_proof(remote, conflict):
    first = b'\x01\x02' * 160
    old = audio_outbox.commit_pcm_window(
        'owner', first, 'conversation', 1000, 16000, 'old', 0, [frame(first, 1000)], framed=True
    )
    storage.upload_audio_chunks_batch(
        [{'data': first, 'timestamp': 1000, 'custody_receipt': old.to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )
    replay = b'\x05\x06' * 160 if conflict else first
    tail = b'\x03\x04' * 160
    frames = [frame(replay, 1000), frame(tail, 1003.01, 1, len(replay), True)]
    new = audio_outbox.commit_pcm_window(
        'owner', replay + tail, 'conversation', 1000, 16000, 'new', 0, frames, framed=True
    )
    chunks = [{'data': replay + tail, 'timestamp': 1000, 'custody_receipt': new.to_dict()}]
    if conflict:
        with pytest.raises(storage.AudioChunkContentConflict):
            storage.upload_audio_chunks_batch(chunks, 'owner', 'conversation', 'standard', sample_rate=16000)
        assert len(remote.list_blobs('chunks/')) == 1
    else:
        storage.upload_audio_chunks_batch(chunks, 'owner', 'conversation', 'standard', sample_rate=16000)
        assert len(remote.list_blobs('chunks/')) == 2
    assert audio_outbox.read_pcm('owner', new) == replay + tail
