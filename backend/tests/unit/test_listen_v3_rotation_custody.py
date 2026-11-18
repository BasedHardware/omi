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

    async def create_successor(*, rollover=False, supersede=None):
        assert supersede == 'current'
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
    published = []
    # The custody ACK checkpoints frame sequence per channel, not conversation, so a retargeted
    # frame is covered exactly like any other.
    await archive.defer_ack('client', AsyncMock(side_effect=lambda: published.append(dict(archive.sequence))))
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
    assert len(published) == 1 and published[0][0] >= len(times) - 1 and not archive.pending_acks
    # Timing skew: the successor's window starts at its first retargeted frame, which is the next
    # frame after the sealed window (never inside it), and its started_at follows that frame.
    successor = db.rows[_key('next')]
    assert successor['started_at'].timestamp() == successor['server_batch_audio_start']
    assert old_end <= successor['server_batch_audio_start'] <= old_end + 0.02
    assert old['v3_rotation_cap_seconds'] == 300.0
    assert 'current' not in controller._batch_producer_tokens


@pytest.mark.asyncio
async def test_retarget_chains_follow_the_newest_successor_and_stay_bounded():
    h = archive_host()
    archive = LiveAudioArchive(h)
    await archive.retarget('a', 'b')
    await archive.retarget('b', 'c')
    assert archive.retargets == {'a': 'c', 'b': 'c'}
    for index in range(70):
        await archive.retarget(f'r{index}', f'r{index + 1}')
    assert len(archive.retargets) == 64
    assert archive.retargets['r69'] == 'r70' and 'a' not in archive.retargets
    # Chained ids that were still kept all name the newest successor.
    assert archive.retargets['r10'] == 'r70'


from tests.unit.test_conversation_quiet_finalization import (  # noqa: E402
    ROW as QUIET_ROW,
    _advance,
    checks as quiet_checks,
    quiet,
    store as quiet_store,  # noqa: F401 (fixture)
)


def test_a_rotation_orphan_is_left_for_listen_stale_recovery_not_the_quiet_check(
    quiet_store, monkeypatch
):  # noqa: F811
    """A v3 recording carries terminal_no_derived_effects, so the quiet check its create armed
    never admits it (recovery_admission_refusal: terminal_no_derived). The owning recovery is
    LiveConversationController.recover_stale_in_progress (below)."""
    quiet_store.rows[QUIET_ROW].update(
        record_lane_owner='batch_live_v1',
        external_data={server_batch.MARKER: True, 'recording_session_id': 'recording-old'},
        recording=True,
        terminal_no_derived_effects=True,
        transcript_segments=[],
        has_content=True,
        server_batch_audio_start=1000.0,
        server_batch_audio_end=1180.0,
        server_batch_audio_received=True,
    )
    assert quiet.arm('synthetic', 'old', 120, firestore_client=quiet_store)
    _advance(monkeypatch, 481)
    job = quiet_checks.quiet_check_id('synthetic', 'old')
    generation = quiet_store.rows[('conversation_finalization_jobs', job)]['dispatch_generation']
    assert quiet.run(job, generation, firestore_client=quiet_store) != 'queued'
    assert 'finalization_revision' not in quiet_store.rows[QUIET_ROW]


@pytest.mark.asyncio
async def test_a_rotation_orphan_is_sealed_by_stale_recovery_on_a_later_connection(monkeypatch):
    host = SimpleNamespace(
        state=SimpleNamespace(current_conversation_id='fresh', active=True),
        request=SimpleNamespace(uid='owner'),
        persistence=SimpleNamespace(call=AsyncMock(return_value=[{'id': 'orphan'}, {'id': 'fresh'}])),
    )
    controller = LiveConversationController(host)
    finalized = []

    async def finalize(fn, conversation_id, *, stage):
        finalized.append((fn, conversation_id, stage))

    controller._finalize_isolated = finalize
    await controller.recover_stale_in_progress()
    assert finalized == [(controller.process_conversation, 'orphan', 'stale_in_progress')]


@pytest.mark.asyncio
async def test_runtime_teardown_drains_pending_rotations(monkeypatch):
    from starlette.websockets import WebSocketState

    from routers.listen.contracts import ListenRequest
    from routers.listen.runtime import ListenSessionRuntime
    from unittest.mock import MagicMock

    order = []
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = ListenRequest(websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED), uid='owner')
    runtime.state = SimpleNamespace(
        shutdown_event=asyncio.Event(),
        active=True,
        stt_terminal_failure=False,
        close_code=1000,
        current_conversation_id=None,
        finalization_reason=None,
    )
    runtime.conversation_creation_timeout = 120
    runtime.task_supervisor = SimpleNamespace(end_session=MagicMock(), drain_all=AsyncMock())
    runtime._finish_live_transcription = MagicMock()
    runtime._record_session_transcript_outcome = MagicMock()
    runtime.transcripts = SimpleNamespace(flush_translations=AsyncMock(), clear=MagicMock())
    runtime.receiver = SimpleNamespace(finish=MagicMock(), flush_multi_channel_tail=AsyncMock(), clear=MagicMock())
    runtime._flush_usage = AsyncMock()
    runtime.is_multi_channel = False
    runtime.language_observations = runtime.pusher_close = runtime.onboarding_handler = None
    runtime.speakers = SimpleNamespace(clear=MagicMock())
    runtime.conversations = SimpleNamespace(drain_rotations=AsyncMock(side_effect=lambda: order.append('drain')))

    async def persist(fn, *args, **kwargs):
        return False if getattr(fn, '__name__', '') == '_account_deletion_blocks_owner_persistence' else None

    runtime.persistence = SimpleNamespace(call=persist)
    await runtime._teardown_components()
    runtime.conversations.drain_rotations.assert_awaited_once_with()
    assert order == ['drain']
