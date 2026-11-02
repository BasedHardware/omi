"""Framed PCM reads use the receipt table without false single-span hash misses."""

import json
from unittest.mock import MagicMock
import time

from utils.other import audio_outbox, raw_audio_read, storage
from utils.other.audio_raw_read_metrics import RAW_READ
from utils.other.audio_chunks import iter_audio_chunk_pcm
from utils.other.audio_frame_table import entries
from utils.other.raw_audio import decode_capture
from utils.other import audio_chunk_replay
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


def test_encoded_only_rebuild_inventory_retains_every_framed_span(remote, monkeypatch):
    pcm = b'\x01\x02' * 320
    receipt = audio_outbox.commit_pcm_window(
        'owner',
        pcm,
        'conversation',
        1000,
        16000,
        'root',
        0,
        [frame(pcm[:320], 1000), frame(pcm[320:], 1003.01, 1, 320, True)],
        framed=True,
    )
    storage.upload_audio_chunks_batch(
        [{'data': pcm, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )
    monkeypatch.setattr(
        storage, 'list_packs', MagicMock(side_effect=AssertionError('encoded inventory must not list raw'))
    )
    listed = storage.list_audio_chunks('owner', 'conversation', include_archive=False)
    assert [(row['timestamp'], row['span']['samples']) for row in listed] == [(1000, 160), (1003.01, 160)]
    assert len({row['path'] for row in listed}) == 1


def test_projection_raw_failure_is_counted_once_with_loaded_codec(remote, caplog):
    pcm = b'\x01\x02' * 160
    receipt = audio_outbox.commit_pcm_window(
        'owner', pcm, 'conversation', 1000, 16000, 'root', 0, [frame(pcm, 1000)], framed=True
    )
    remote.blob(receipt.path).data = b'corrupt'
    before = RAW_READ.labels(result='checksum_mismatch')._value.get()
    with pytest.raises(raw_audio_read.ChecksumMismatch):
        raw_audio_read.pcm_for_projection(
            remote, 'owner', {'framed_receipt': json.dumps(receipt.to_dict()), 'pcm_sha256': receipt.pcm_sha256}, 16000
        )
    assert RAW_READ.labels(result='checksum_mismatch')._value.get() == before + 1
    assert caplog.text.count('event=audio_raw_read') == 1
    assert 'result=checksum_mismatch codec=pcm16' in caplog.text


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


@pytest.mark.parametrize('read_enabled', [False, True])
def test_replay_cannot_shadow_raw_receipt_after_projection_failure(remote, monkeypatch, read_enabled):
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *args: read_enabled)
    first = b'\x01\x02' * 160
    old = audio_outbox.commit_pcm_window(
        'owner', first, 'conversation', 1000, 16000, 'old', 0, [frame(first, 1000)], framed=True
    )
    replay, tail = b'\x05\x06' * 160, b'\x03\x04' * 160
    frames = [frame(replay, 1000), frame(tail, 1003.01, 1, len(replay), True)]
    new = audio_outbox.commit_pcm_window(
        'owner', replay + tail, 'conversation', 1000, 16000, 'new', 0, frames, framed=True
    )
    # Model another writer's commit while this process still has an empty TTL index.
    raw_audio_read._indexes[(remote.name, 'owner', 'conversation')] = (time.monotonic() + 120, [])
    reload_blob = remote.blob(old.path).reload

    def sdk_reload(*, timeout, retry, if_generation_match=None):
        assert 0 < timeout <= 10 and retry is None
        reload_blob(timeout=timeout, retry=retry, if_generation_match=if_generation_match)

    monkeypatch.setattr(remote.blob(old.path), 'reload', sdk_reload)
    with pytest.raises(storage.AudioChunkContentConflict):
        storage.upload_audio_chunks_batch(
            [{'data': replay + tail, 'timestamp': 1000, 'custody_receipt': new.to_dict()}],
            'owner',
            'conversation',
            'standard',
            sample_rate=16000,
        )
    assert not remote.list_blobs('chunks/')


def test_raw_playback_keeps_earlier_custody_when_replay_extends_both_ends():
    earlier = {
        'path': 'old',
        'generation': 1,
        'raw_created_at': 1,
        'timestamp': 1000,
        'raw_end': 1000.01,
        'span': {'start': 1000, 'samples': 160, 'sample_rate': 16000},
        'raw_offset_samples': 0,
    }
    replay = {
        'path': 'new',
        'generation': 2,
        'raw_created_at': 2,
        'timestamp': 999.99,
        'raw_end': 1000.02,
        'span': {'start': 999.99, 'samples': 480, 'sample_rate': 16000},
        'raw_offset_samples': 0,
    }
    visible = raw_audio_read.uncovered_raw_packs([replay, earlier], [])
    assert [(row['path'], row['span']['samples'], row['raw_offset_samples']) for row in visible] == [
        ('new', 160, 0),
        ('old', 160, 0),
        ('new', 160, 320),
    ]


def test_bounded_replay_fails_closed_on_raw_listing_error(remote, monkeypatch):
    pcm = b'\x01\x02' * 160
    receipt = audio_outbox.commit_pcm_window(
        'owner', pcm, 'conversation', 1000, 16000, 'root', 0, [frame(pcm, 1000)], framed=True
    )
    real_list = remote.list_blobs

    def list_blobs(prefix, **kwargs):
        if prefix.startswith('raw-live/'):
            raise TimeoutError('injected raw listing failure')
        return real_list(prefix, **kwargs)

    monkeypatch.setattr(remote, 'list_blobs', list_blobs)
    with pytest.raises(TimeoutError):
        storage.upload_audio_chunks_batch(
            [{'data': pcm, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
            'owner',
            'conversation',
            'standard',
            sample_rate=16000,
        )
    assert not real_list('chunks/')


@pytest.mark.parametrize('rate', [8000, 22050, 44100, 48000])
@pytest.mark.parametrize('gap', [False, True])
def test_resampled_frame_fragments_partition_whole_pack(remote, monkeypatch, rate, gap):
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *args: True)
    first, second = b'\x01\x02' * 1024, b'\x03\x04' * 1024
    frames = [frame(first, 1000), frame(second, 1000 + 1024 / rate + (3 if gap else 0), 1, len(first), gap)]
    receipt = audio_outbox.commit_pcm_window(
        'owner', first + second, 'conversation', 1000, rate, 'root', 0, frames, framed=True
    )
    assert audio_outbox.read_pcm('owner', receipt) == first + second
    listed = raw_audio_read.list_packs(remote, 'owner', 'conversation')
    assert len(listed) == (2 if gap else 1)
    for output_rate in (16000, rate):
        decoded = raw_audio_read.read_pack(remote, receipt.path, 'owner', sample_rate=output_rate)
        assert decoded == decode_capture(first + second, remote.blob(receipt.path).metadata, output_rate)
        fragments = [raw_audio_read.select_raw_pcm(decoded, row, output_rate) for row in listed]
        assert b''.join(fragments) == decoded
        played = list(iter_audio_chunk_pcm('owner', 'conversation', lambda *args: True, sample_rate=output_rate))
        assert b''.join(data for _, data in played) == decoded


def test_replay_counts_objects_once_for_many_disjoint_spans(remote, monkeypatch):
    captured = [bytes([index, 0]) * 160 for index in range(65)]
    frames = [frame(data, 1000 + index * 3, index, index * 320, index > 0) for index, data in enumerate(captured)]
    pcm = b''.join(captured)
    receipt = audio_outbox.commit_pcm_window('owner', pcm, 'conversation', 1000, 16000, 'root', 0, frames, framed=True)
    path = storage.upload_audio_chunks_batch(
        [{'data': pcm, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )[0]
    download = MagicMock(wraps=remote.blob(path).download_as_bytes)
    monkeypatch.setattr(remote.blob(path), 'download_as_bytes', download)
    audio_chunk_replay.verify_frame_overlaps(
        'owner',
        'conversation',
        pcm,
        frames,
        16000,
        bucket=remote,
        list_chunks=storage.list_audio_chunks,
        bucket_for=lambda name: remote,
    )
    assert download.call_count == 1


@pytest.mark.parametrize('conflict', [False, True])
@pytest.mark.parametrize('gap', [False, True])
@pytest.mark.parametrize('rate', [8000, 22050, 44100, 48000])
def test_replay_compares_native_rate_raw_capture_in_requested_rendition(remote, conflict, gap, rate):
    captured = b'\x01\x02' * 1024 + b'\x03\x04' * 1024
    second_start = 1000 + 1024 / rate + (3 if gap else 0)
    old = audio_outbox.commit_pcm_window(
        'owner',
        captured,
        'conversation',
        1000,
        rate,
        'native',
        0,
        [frame(captured[:2048], 1000), frame(captured[2048:], second_start, 1, 2048, gap)],
        framed=True,
    )
    rendition = raw_audio_read.read_pack(remote, old.path, 'owner', sample_rate=16000)
    replay = ((b'\xff\x00' + rendition[2:]) if conflict else rendition) + b'\x07\x08' * 160
    # Obtain the boundary from the real decoder, independently of frame-table arithmetic.
    first_size = len(decode_capture(captured[:2048], remote.blob(old.path).metadata, 16000))
    frames = (
        [frame(replay[:first_size], 1000), frame(replay[first_size:], second_start, 1, first_size, True)]
        if gap
        else [frame(replay, 1000)]
    )
    receipt = audio_outbox.commit_pcm_window(
        'owner',
        replay,
        'conversation',
        1000,
        16000,
        'replay',
        0,
        frames,
        framed=True,
    )

    def upload():
        return storage.upload_audio_chunks_batch(
            [{'data': replay, 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
            'owner',
            'conversation',
            'standard',
            sample_rate=16000,
        )

    if conflict:
        with pytest.raises(storage.AudioChunkContentConflict):
            upload()
        assert not remote.list_blobs('chunks/')
    else:
        assert remote.blob(upload()[0]).data == replay
    assert audio_outbox.read_pcm('owner', old) == captured
