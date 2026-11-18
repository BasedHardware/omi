"""Custody across a v3 recording rotation: every frame lands in exactly one recording window."""

import asyncio
import struct
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import server_batch
from config.listen_reconnect import FIELD as PRODUCER
from database import conversations, server_batch_audio
from routers.listen import conversations as conversation_module
from routers.listen.conversations import LiveConversationController
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_audio_durable_outbox import remote, host as archive_host  # noqa: F401 (fixture)
from utils.other import live_audio_archive
from utils.other.live_audio_archive import LiveAudioArchive


def _row(cid, reconnect):
    row = dict(
        id=cid,
        source='omi',
        client_platform='ios',
        language='en',
        private_cloud_sync_enabled=True,
        uses_custom_stt=False,
        data_protection_level='standard',
        record_lane_owner='batch_live_v1',
        external_data={server_batch.MARKER: True},
        status='in_progress',
        recording=True,
        transcript_segments=[],
        created_at=datetime(2026, 11, 18, tzinfo=timezone.utc),
    )
    if reconnect:
        row[PRODUCER] = {'version': 1, 'token': 'token-' + cid, 'phase': 'active'}
    return row


def _key(cid):
    return ('users', 'owner', 'conversations', cid)


@pytest.mark.asyncio
@pytest.mark.parametrize('reconnect', [False, True])
async def test_frames_in_flight_across_a_rotation_land_in_exactly_one_window(
    remote, monkeypatch, reconnect
):  # noqa: F811
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true' if reconnect else 'false')
    db = StrictFirestore({_key('current'): _row('current', reconnect)})
    monkeypatch.setattr(
        live_audio_archive,
        'note_server_batch_audio',
        lambda uid, cid, start, end, **kw: server_batch_audio.note_server_batch_audio(
            uid, cid, start, end, firestore_client=db, **kw
        ),
    )
    monkeypatch.setattr(
        live_audio_archive,
        'note_server_batch_audio_received',
        lambda uid, cid, **kw: server_batch_audio.note_server_batch_audio_received(uid, cid, firestore_client=db, **kw),
    )

    def get_conversation(uid, cid, **kw):
        return dict(db.rows[_key(cid)]) if _key(cid) in db.rows else None

    def update_conversation(uid, cid, patch):
        db.rows[_key(cid)] = {**db.rows[_key(cid)], **patch}

    monkeypatch.setattr(conversations, 'get_conversation', get_conversation)
    monkeypatch.setattr(conversation_module.conversations_db, 'update_conversation', update_conversation)

    h = archive_host()
    h.server_batch_only = True
    h.state = SimpleNamespace(current_conversation_id='current', active=True, first_audio_byte_timestamp=None)
    h.recording_session_ids_by_conversation = {}
    h.recording_session_id = 'session-1'
    h.transcripts = SimpleNamespace(flush_speaker_assignments=AsyncMock())

    async def call(fn, *args, **kwargs):
        kwargs.pop('read_site', None)
        return fn(*args, **kwargs)

    h.persistence = SimpleNamespace(call=call)
    controller = LiveConversationController(h)
    h.conversations = controller
    archive = LiveAudioArchive(h)
    h.receiver = SimpleNamespace(raw_archive=archive)
    if reconnect:
        controller._batch_producer_tokens['current'] = 'token-current'

    committed = []
    write = archive._write

    async def recording_write(pack, channel):
        starts = [frame['start'] for frame in archive.frames.get(id(pack), [])]
        await write(pack, channel)
        committed.append((pack.conversation_id, starts))

    archive._write = recording_write
    sealed = {}

    async def schedule_finalization(cid):
        row = db.rows[_key(cid)]
        sealed[cid] = (row['server_batch_audio_start'], row['server_batch_audio_end'])
        db.rows[_key(cid)] = {**row, 'status': 'processing'}
        return True

    controller.schedule_finalization = schedule_finalization
    switched = asyncio.Event()

    async def create_successor(*, rollover=False):
        # Firestore round trips: frames keep arriving for the current recording meanwhile.
        for _ in range(5):
            await asyncio.sleep(0)
        db.rows[_key('next')] = _row('next', reconnect)
        if reconnect:
            controller._batch_producer_tokens['next'] = 'token-next'
        h.state.current_conversation_id = 'next'
        switched.set()

    controller.create_new_in_progress_conversation = create_successor
    times = [1000 + index * 0.01 for index in range(120)]

    async def produce():
        for index, at in enumerate(times):
            bound = h.state.current_conversation_id  # the receiver binds before append can yield
            await asyncio.sleep(0)
            packet = struct.pack('<160h', *[index] * 160)
            await archive.append(packet, bound, at, 160, decoded=packet)

    async def rotate():
        while len(archive.sequence) == 0 or archive.sequence.get(0, 0) < 40:
            await asyncio.sleep(0)
        await controller._rotate_v3_recording('current')

    await asyncio.gather(produce(), rotate())
    # A frame the receiver bound to the old id before the switch, appended after the seal.
    late = times[-1] + 0.01
    times.append(late)
    packet = struct.pack('<160h', *[7] * 160)
    await archive.append(packet, 'current', late, 160, decoded=packet)
    await archive.close()

    assert switched.is_set() and set(sealed) == {'current'}
    landed = sorted(start for _, starts in committed for start in starts)
    assert landed == times  # every frame once, none dropped or duplicated
    owners = {start: cid for cid, starts in committed for start in starts}
    old_start, old_end = sealed['current']
    old = db.rows[_key('current')]
    # The sealed window never grows after its seal decision.
    assert (old['server_batch_audio_start'], old['server_batch_audio_end']) == (old_start, old_end)
    for start, cid in owners.items():
        row = db.rows[_key(cid)]
        assert row['server_batch_audio_start'] <= start < row['server_batch_audio_end']
    assert max(s for s, c in owners.items() if c == 'current') < min(s for s, c in owners.items() if c == 'next')
    assert not archive.uncommitted and not archive.failed
    assert old['v3_rotation_cap_seconds'] == 300.0
    assert 'current' not in controller._batch_producer_tokens
