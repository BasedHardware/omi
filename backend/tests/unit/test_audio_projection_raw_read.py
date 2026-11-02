"""Framed PCM reads use the receipt table without false single-span hash misses."""

from unittest.mock import MagicMock

from utils.other import audio_outbox, raw_audio_read, storage
from utils.other.audio_raw_read_metrics import RAW_READ
from utils.other.audio_chunks import iter_audio_chunk_pcm
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
