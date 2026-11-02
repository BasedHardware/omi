"""Seal CAS behavior with versioning off and per-part receipt independence."""

from contextlib import nullcontext

import pytest

from utils.other import audio_outbox, audio_seal_index as seals, storage
from utils.other.live_audio_archive import LiveAudioArchive
from tests.unit.test_audio_durable_outbox import remote, host, Socket, _window_harness, _audio_frames, pusher
from tests.unit.test_audio_custody_frames import frame, _sent_receipts


def writer(remote, source='source', protection='standard'):
    return seals.ConversationSealIndex(remote, 'owner', source, protection, lambda *a: nullcontext(), lambda conv: [])


def part(remote, sequence=0, start=1000):
    pcm = bytes([sequence, 1]) * 160
    frames = [frame(pcm, start, sequence)]
    receipt = audio_outbox.commit_pcm_window(
        'owner', pcm, 'conversation', start, 16000, 'root', sequence, frames, framed=True
    )
    return receipt, frames


@pytest.mark.parametrize('protection', ['standard', 'enhanced'])
def test_seal_is_separate_from_receipt_and_reopen_invalidates_previous_snapshot(remote, protection):
    index = writer(remote, protection=protection)
    index.begin('conversation')
    receipt, frames = part(remote)
    index.add(receipt.to_dict(), frames)
    # Receipt already proves custody before the index exists in sealed form.
    assert audio_outbox.read_pcm('owner', receipt) == bytes([0, 1]) * 160
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
    index.seal('conversation')
    result = seals.sealed_entries(remote, 'owner', 'conversation')
    assert len(result) == 1 and result[0]['generation'] == int(receipt.generation)
    assert index.versioning_checked and remote.versioning_enabled is False
    index.begin('conversation')
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
    later, frames = part(remote, 1, 1003)
    index.add(later.to_dict(), frames)
    index.seal('conversation')
    assert len(seals.sealed_entries(remote, 'owner', 'conversation')) == 2
    assert len(remote.list_blobs('audio-outbox/owner/conversation/seals/')) == 2


def test_two_writers_cannot_close_each_others_uncommitted_tail(remote):
    first, second = writer(remote, 'one'), writer(remote, 'two')
    first.begin('conversation')
    second.begin('conversation')
    receipt, frames = part(remote)
    first.add(receipt.to_dict(), frames)
    first.seal('conversation')
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
    # The second process dies; its open writer prevents a truncated snapshot.
    assert audio_outbox.read_pcm('owner', receipt)


def test_old_close_cannot_seal_newly_accepted_uncommitted_frames(remote):
    index = writer(remote)
    index.begin('conversation')
    index.accept('conversation', 320)
    receipt, frames = part(remote)
    index.add(receipt.to_dict(), frames)
    index.seal('conversation')
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
    later, frames = part(remote, 1, 1003)
    index.add(later.to_dict(), frames)
    index.seal('conversation')
    assert len(seals.sealed_entries(remote, 'owner', 'conversation')) == 2


def test_oversized_frame_manifest_never_issues_an_unreadable_receipt(remote, monkeypatch):
    monkeypatch.setattr(audio_outbox, 'MAX_MANIFEST_BYTES', 1)
    with pytest.raises(ValueError):
        part(remote)
    assert len(remote.list_blobs('raw-live/')) == 1
    assert not remote.list_blobs('audio-outbox/')


def test_part_cap_seals_deterministically_without_releasing_or_holding_receipts(remote, monkeypatch):
    monkeypatch.setattr(seals, 'PART_BYTES', 640)
    index = writer(remote)
    index.begin('conversation')
    for number in range(3):
        receipt, frames = part(remote, number, 1000 + number)
        index.add(receipt.to_dict(), frames)
        assert audio_outbox.read_pcm('owner', receipt)
    assert len(remote.list_blobs('audio-outbox/owner/conversation/seals/')) == 1
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
    index.seal('conversation')
    assert len(seals.sealed_entries(remote, 'owner', 'conversation')) == 3


@pytest.mark.asyncio
async def test_listen_emits_part_ack_before_index_failure_and_leaves_prefix_fallback(remote, monkeypatch):
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    monkeypatch.setattr(seals, 'PART_BYTES', 320)
    h = host()
    archive = LiveAudioArchive(h)
    await archive.append(b'\x01\x02' * 160, 'conversation', 1000, 160)
    coverage_acks = []

    async def publish():
        coverage_acks.append(True)

    await archive.defer_ack('conversation', publish)
    real_put = archive.seal_index._put

    def fail_seal(path, value, generation):
        if '/seals/' in path:
            assert h.events, 'part ACK must already exist before index write'
            assert coverage_acks, 'coverage WAL release must also precede index write'
            raise OSError('injected seal write failure')
        return real_put(path, value, generation)

    monkeypatch.setattr(archive.seal_index, '_put', fail_seal)
    await archive.close()
    assert len(h.events) == 1
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
    receipt = audio_outbox.AudioReceipt(**h.events[0].receipt)
    assert audio_outbox.read_pcm('owner', receipt) == b'\x01\x02' * 160


@pytest.mark.asyncio
async def test_pusher_disconnect_seals_frames_and_existing_pcm_projection_paths(remote, monkeypatch):
    _window_harness(remote, monkeypatch)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    monkeypatch.setattr(pusher, 'upload_audio_chunks_batch', storage.upload_audio_chunks_batch)
    monkeypatch.setattr(pusher.conversations_db, 'create_audio_files_from_chunks', lambda *args: [])
    sock = Socket(_audio_frames('conversation', [b'\x01\x02' * 160, b'\x03\x04' * 160], step=3.01))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_timeline=2, audio_custody=1)
    assert len(_sent_receipts(sock)) == 1
    result = seals.sealed_entries(remote, 'owner', 'conversation')
    assert [item['timestamp'] for item in result] == [1000, 1003.01]
    root, _ = seals._read(remote, 'owner', seals.index_path('owner', 'conversation'))
    receipts = [item for part in root['parts'].values() for item in part['receipts']]
    assert receipts[0]['projections'] == [blob.name for blob in remote.list_blobs('chunks/')]


@pytest.mark.asyncio
async def test_legacy_writer_invalidates_an_existing_seal_without_inventing_capture_positions(remote, monkeypatch):
    index = writer(remote)
    index.begin('conversation')
    receipt, frames = part(remote)
    index.add(receipt.to_dict(), frames)
    index.seal('conversation')
    assert seals.sealed_entries(remote, 'owner', 'conversation')
    _window_harness(remote, monkeypatch)
    monkeypatch.setenv('AUDIO_CUSTODY_FRAMED_PERCENT', '100')
    sock = Socket(_audio_frames('conversation', [b'\x03\x04' * 160], start=2000))
    await pusher._websocket_util_trigger(sock, 'owner', 16000, audio_custody=1)
    assert len(_sent_receipts(sock)) == 1
    with pytest.raises(ValueError):
        seals.sealed_entries(remote, 'owner', 'conversation')
