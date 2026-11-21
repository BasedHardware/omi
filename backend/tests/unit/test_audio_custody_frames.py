"""Framed custody failure boundaries and fresh-decode PCM fidelity."""

import hashlib
import json
import struct

import pytest

from config.audio_custody import framed_pack
from utils.other import audio_outbox, audio_outbox_metrics, raw_audio_read, storage
from utils.other.audio_chunks import iter_audio_chunk_pcm
from utils.other import audio_frame_table
from utils.pusher_protocol import ByteBudget
from utils.pusher_record_finish import RecordProjectionQueue
from tests.unit.test_audio_durable_outbox import (
    remote,
    Socket,
    _window_harness,
    _audio_frames,
    pusher,
)


def _sent_receipts(sock):
    return [
        audio_outbox.AudioReceipt(**json.loads(message[4:])['receipt'])
        for message in sock.sent
        if struct.unpack('<I', message[:4])[0] == 203
    ]


def frame(pcm, start, sequence=0, offset=0, gap=False):
    return {
        'sequence': sequence,
        'byte_offset': offset,
        'bytes': len(pcm),
        'samples': len(pcm) // 2,
        'start': start,
        'gap_before': gap,
        'sha256': hashlib.sha256(pcm).hexdigest(),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('overlap', [0.0005, 0.001])
async def test_pusher_tolerated_overlap_commits_all_samples_and_receipt(remote, monkeypatch, overlap):
    _window_harness(remote, monkeypatch)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    captured = [b'\x01\x02' * 160, b'\x03\x04' * 160]
    sock = Socket(_audio_frames('conversation', captured, step=0.01 - overlap))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    receipts = _sent_receipts(sock)
    assert len(receipts) == 1
    assert audio_outbox.read_pcm('owner', receipts[0]) == b''.join(captured)
    manifest = json.loads(remote.blob(receipts[0].manifest_path).data)
    assert [row['start'] for row in manifest['frames']] == [1000, 1000.01 - overlap]
    assert [row['samples'] for row in manifest['frames']] == [160, 160]
    paths = storage.upload_audio_chunks_batch(
        [{'data': b''.join(captured), 'timestamp': 1000, 'custody_receipt': receipts[0].to_dict()}],
        'owner',
        'conversation',
        'standard',
        sample_rate=16000,
    )
    assert remote.blob(paths[0]).data == b''.join(captured)


@pytest.mark.parametrize(
    'value,admitted', [(None, False), ('0', False), ('bad', False), ('nan', False), ('101', False), ('100', True)]
)
def test_framed_percent_is_independent_and_fail_closed(monkeypatch, value, admitted):
    monkeypatch.setenv('AUDIO_ARCHIVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ROLLOUT_COHORTS', 'audio-archive')
    if value is None:
        monkeypatch.delenv('AUDIO_CUSTODY_FRAMED_PERCENT', raising=False)
    else:
        monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', value)
    assert framed_pack('owner') is admitted


@pytest.mark.asyncio
async def test_media_put_without_manifest_holds_wal_retry_issues_one_receipt(remote, monkeypatch):
    pcm = b'\x01\x02' * 160
    frames = [frame(pcm, 1000), frame(pcm, 1003.01, 1, len(pcm), True)]
    payload = pcm * 2
    sock = Socket([])
    queue = RecordProjectionQueue(maxsize=20)
    budget = ByteBudget(16 * 1024 * 1024)
    budget.reserve(len(payload))
    real_write = storage.archive_capture_bytes
    fail_manifest = True

    def write(*args, **kwargs):
        if args[2] == 'audio-outbox' and fail_manifest:
            raise OSError('injected death after media PUT')
        return real_write(*args, **kwargs)

    monkeypatch.setattr(storage, 'archive_capture_bytes', write)
    options = dict(
        uid='owner',
        payload=payload,
        frames=frames,
        conversation_id='conversation',
        start=1000,
        sample_rate=16000,
        custody_root='root',
        protection_level='standard',
        audio_custody=1,
        timeline_v2=True,
        websocket=sock,
        durable_queue=queue,
        budget=budget,
        queue_wait_timeout=1,
        framed=True,
    )
    before = audio_outbox_metrics.CUSTODY_COMMITS._value.get()
    with pytest.raises(OSError):
        await pusher._commit_durable_audio_window(**options)
    assert not sock.sent and queue.empty() and budget.used == len(payload)
    assert len(remote.list_blobs('raw-live/')) == 1
    assert not remote.list_blobs('audio-outbox/')
    raw_audio_read.invalidate_pack_index(remote, 'owner', 'conversation')
    assert raw_audio_read.list_packs(remote, 'owner', 'conversation') == [], 'orphan cannot be played'
    assert audio_outbox_metrics.CUSTODY_COMMITS._value.get() == before
    fail_manifest = False
    receipt = await pusher._commit_durable_audio_window(**options)
    assert receipt and len(sock.sent) == 1 and budget.used == 0
    assert all((receipt.generation, receipt.manifest_generation, receipt.sha256, receipt.manifest_sha256))
    assert audio_outbox_metrics.CUSTODY_COMMITS._value.get() == before + 1
    assert len(remote.list_blobs('raw-live/')) == len(remote.list_blobs('audio-outbox/')) == 1
    assert audio_outbox.read_pcm('owner', receipt) == payload


@pytest.mark.asyncio
@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
async def test_three_second_gap_is_two_spans_one_object_and_fresh_decode_matches(remote, monkeypatch, protection):
    _window_harness(remote, monkeypatch)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    monkeypatch.setattr(storage.users_db, 'get_data_protection_level', lambda uid: protection)
    captured = [struct.pack('<160h', *range(160)), struct.pack('<160h', *range(160, 320))]
    sock = Socket(_audio_frames('conversation', captured, step=3.01))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    receipts = _sent_receipts(sock)
    assert len(receipts) == 1
    receipt = receipts[0]
    manifest_raw = remote.blob(receipt.manifest_path).data
    if protection == 'enhanced':
        manifest_raw = storage.encryption.decrypt_audio_file(manifest_raw, 'owner')
    manifest = json.loads(manifest_raw)
    assert [(f['start'], f['samples'], f['gap_before']) for f in manifest['frames']] == [
        (1000, 160, False),
        (1003.01, 160, True),
    ]
    # This exercises a fresh decoder and compares captured bytes, not pcm_sha256 metadata.
    assert raw_audio_read.read_pack(remote, receipt.path, 'owner') == b''.join(captured)
    packs = raw_audio_read.list_packs(remote, 'owner', 'conversation')
    assert len(packs) == 2 and {p['path'] for p in packs} == {receipt.path}
    assert [
        raw_audio_read.select_raw_pcm(raw_audio_read.read_pack(remote, p['path'], 'owner'), p, 16000) for p in packs
    ] == captured
    chunks = [
        {'timestamp': f['start'], 'data': pcm, 'span': {'start': f['start'], 'samples': 160, 'sample_rate': 16000}}
        for f, pcm in zip(manifest['frames'], captured)
    ]
    assert raw_audio_read.verified_pcm_paths(remote, 'owner', 'conversation', chunks, 16000) == [receipt.path]
    storage.upload_audio_chunks_batch(
        [{'data': b''.join(captured), 'timestamp': 1000, 'custody_receipt': receipt.to_dict()}],
        'owner',
        'conversation',
        protection,
        sample_rate=16000,
    )
    assert len(remote.list_blobs('chunks/')) == 1
    listed = storage.list_audio_chunks('owner', 'conversation')
    assert [c['timestamp'] for c in listed] == [1000, 1003.01]
    played = list(iter_audio_chunk_pcm('owner', 'conversation', lambda *args: True))
    assert played == [(1000, captured[0]), (1003.01, captured[1])]


@pytest.mark.asyncio
async def test_mid_window_death_leaves_tail_held_and_prior_part_released(remote, monkeypatch):
    _window_harness(remote, monkeypatch, chunk_duration=0.01)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    real_commit = pusher.commit_pcm_window
    calls = 0

    def commit(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('injected tail death')
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(pusher, 'commit_pcm_window', commit)
    captured = [b'\x01\x02' * 160, b'\x03\x04' * 160]
    sock = Socket(_audio_frames('conversation', captured))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    receipts = _sent_receipts(sock)
    assert len(receipts) == 1 and audio_outbox.read_pcm('owner', receipts[0]) == captured[0]
    assert receipts[0].samples == 160 and sock.close_code == 1011
    assert len(remote.list_blobs('raw-live/')) == len(remote.list_blobs('audio-outbox/')) == 1


def test_oversized_frame_manifest_never_issues_an_unreadable_receipt(remote, monkeypatch):
    # The writer must honor the reader bound before issuing a custody receipt.
    monkeypatch.setattr(audio_outbox, 'MAX_MANIFEST_BYTES', 1, raising=False)
    pcm = b'\x01\x02' * 160
    before = audio_outbox_metrics.CUSTODY_COMMITS._value.get()
    with pytest.raises(ValueError, match='frame manifest exceeds reader bound'):
        audio_outbox.commit_pcm_window(
            'owner', pcm, 'conversation', 1000, 16000, 'root', 0, [frame(pcm, 1000)], framed=True
        )
    assert len(remote.list_blobs('raw-live/')) == 1
    assert not remote.list_blobs('audio-outbox/')
    assert audio_outbox_metrics.CUSTODY_COMMITS._value.get() == before


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
@pytest.mark.parametrize('headroom', [0, 31, 32])
def test_manifest_receipt_bound_includes_actual_encryption_envelope(remote, monkeypatch, protection, headroom):
    pcm = b'\x01\x02' * 160

    def commit():
        return audio_outbox.commit_pcm_window(
            'owner',
            pcm,
            'conversation',
            1000,
            16000,
            'root',
            0,
            [frame(pcm, 1000)],
            framed=True,
            data_protection_level=protection,
        )

    original = commit()
    stored = remote.blob(original.manifest_path).data
    plaintext = storage.encryption.decrypt_audio_file(stored, 'owner') if protection == 'enhanced' else stored
    bound = len(plaintext) + headroom
    monkeypatch.setattr(audio_outbox, 'MAX_MANIFEST_BYTES', bound)
    monkeypatch.setattr(audio_frame_table, 'MAX_MANIFEST_BYTES', bound)
    before = audio_outbox_metrics.CUSTODY_COMMITS._value.get()
    if len(stored) > bound:
        with pytest.raises(ValueError, match='frame manifest exceeds reader bound'):
            commit()
        assert audio_outbox_metrics.CUSTODY_COMMITS._value.get() == before
    else:
        receipt = commit()
        assert audio_frame_table.receipt_frames(remote, 'owner', receipt.to_dict()) == ([frame(pcm, 1000)], 16000)
    assert audio_outbox.read_pcm('owner', original) == pcm
