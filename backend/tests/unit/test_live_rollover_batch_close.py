"""A live rollover must seal and clean the generation it displaces.

Incident 2026-11-17: a mobile server-batch session that rolled over while the
socket stayed live never published the archive-close barrier for the displaced
generation (``close_batch_archive`` skipped the seal whenever
``host.state.active`` was true) and never cleaned its empty row
(``process_conversation`` refused the delete for the same reason). The row kept
``server_batch_audio_received`` without ``server_batch_audio_closed``, so empty
cleanup refused it forever, the recording-session binding stayed pinned to it,
and every reconnect rolled into a fresh empty generation every ~120 s.
"""

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from database import conversation_quiet_checks as checks
from database import server_batch_audio
from routers.listen import batch_close as close
from routers.listen.conversations import LiveConversationController
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_conversation_quiet_finalization import (  # noqa: F401
    NOW,
    ROW as QUIET_ROW,
    SESSION as QUIET_SESSION,
    _advance,
    store,
)
from utils.conversations import quiet_finalization as quiet

ROW = ('users', 'owner', 'conversations', 'conversation')


def capture(**changes):
    return {
        'id': 'conversation',
        'record_lane_owner': 'batch_live_v1',
        'external_data': {'server_batch_only': True},
        'server_batch_audio_received': True,
        'server_batch_audio_closed': None,
        'server_batch_audio_start': None,
        'server_batch_audio_end': None,
        'has_content': None,
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'enhanced',
        'source': 'omi',
        'client_platform': 'ios',
        'status': 'in_progress',
        'transcript_segments': [],
        **changes,
    }


def live_host(row, *, active=True, archive=True):
    async def persisted(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    return SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        state=SimpleNamespace(current_conversation_id='conversation', active=active),
        receiver=SimpleNamespace(raw_archive=SimpleNamespace(close=AsyncMock())) if archive else None,
        persistence=SimpleNamespace(call=persisted),
        recording_session_id='session',
        recording_session_ids_by_conversation={'conversation': 'session'},
    )


@pytest.mark.asyncio
async def test_displaced_rollover_seals_the_archive_while_the_session_is_live(monkeypatch):
    row = capture()
    seal = Mock(return_value=True)
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))
    host = live_host(row)

    assert await close.close_batch_archive(host, 'conversation', row, displaced=True) is not None
    host.receiver.raw_archive.close.assert_awaited_once()
    seal.assert_called_once_with('owner', 'conversation')


@pytest.mark.asyncio
async def test_displaced_generation_after_the_swap_commits_only_its_own_packs(monkeypatch):
    """A create-then-finalize rollover no longer owns the archive; seal it anyway."""
    row = capture()
    seal = Mock(return_value=True)
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))
    host = live_host(row)
    host.state.current_conversation_id = 'successor'
    host.receiver.raw_archive.finish_recording = AsyncMock()

    assert await close.close_batch_archive(host, 'conversation', row, displaced=True) is not None
    host.receiver.raw_archive.finish_recording.assert_awaited_once_with('conversation')
    host.receiver.raw_archive.close.assert_not_awaited()
    seal.assert_called_once_with('owner', 'conversation')


@pytest.mark.asyncio
async def test_live_capture_target_still_skips_the_close_barrier(monkeypatch):
    """The guard that protects the generation still receiving audio is unchanged."""
    row = capture()
    seal = Mock(side_effect=AssertionError('the live capture target is not sealed'))
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))
    host = live_host(row)

    assert await close.close_batch_archive(host, 'conversation', row) == row
    host.receiver.raw_archive.close.assert_awaited_once()
    seal.assert_not_called()


@pytest.mark.asyncio
async def test_displaced_empty_generation_is_deleted_while_the_session_is_live(monkeypatch):
    row = capture(server_batch_audio_closed=True)
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))
    monkeypatch.setattr(close, 'close_server_batch_audio', Mock(return_value=True))
    deleted = Mock(return_value=True)
    monkeypatch.setattr('routers.listen.conversations.lifecycle_service.delete_empty_recording_conversation', deleted)
    host = live_host(row)
    controller = LiveConversationController(host)

    assert await controller.process_conversation('conversation', displaced=True) is True
    deleted.assert_called_once()
    assert deleted.call_args.kwargs['allow_empty_server_batch'] is True


@pytest.mark.asyncio
async def test_live_capture_target_still_refuses_empty_cleanup(monkeypatch):
    row = capture(server_batch_audio_closed=True)
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))
    monkeypatch.setattr(close, 'close_server_batch_audio', Mock(return_value=True))
    deleted = Mock(side_effect=AssertionError('a live capture target cannot certify no input'))
    monkeypatch.setattr('routers.listen.conversations.lifecycle_service.delete_empty_recording_conversation', deleted)
    host = live_host(row)
    controller = LiveConversationController(host)

    assert await controller.process_conversation('conversation') is False
    deleted.assert_not_called()


def test_sealed_archive_without_a_committed_window_clears_the_first_frame_marker():
    """A sealed archive with no retained window is provably empty, not received."""
    db = StrictFirestore({ROW: capture()})
    assert server_batch_audio.close_server_batch_audio('owner', 'conversation', firestore_client=db)
    assert db.rows[ROW]['server_batch_audio_closed'] is True
    assert db.rows[ROW]['server_batch_audio_received'] is False


def test_sealed_archive_with_a_committed_window_keeps_the_received_marker():
    db = StrictFirestore(
        {ROW: capture(server_batch_audio_start=1000.0, server_batch_audio_end=1060.0, has_content=True)}
    )
    assert server_batch_audio.close_server_batch_audio('owner', 'conversation', firestore_client=db)
    assert db.rows[ROW]['server_batch_audio_closed'] is True
    assert db.rows[ROW]['server_batch_audio_received'] is True


def test_quiet_check_seals_a_producer_less_empty_batch_capture(store, monkeypatch):  # noqa: F811
    """The quiet check is the only actor left once a legacy socket is gone."""
    row = store.rows[QUIET_ROW]
    row.update(
        record_lane_owner='batch_live_v1',
        external_data={'server_batch_only': True, 'recording_session_id': 'recording-old'},
        server_batch_audio_received=True,
        server_batch_audio_start=None,
        server_batch_audio_end=None,
        has_content=None,
        transcript_segments=[],
    )
    store.rows[QUIET_SESSION]['lease_expires_at'] = NOW - timedelta(seconds=1)
    quiet.arm('synthetic', 'old', 120, firestore_client=store)
    _advance(monkeypatch, 200)

    quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store)

    assert row['server_batch_audio_closed'] is True
    assert row['server_batch_audio_received'] is False


# --- Drop hold re-gate and stale-row recovery (2026-11-17 storm follow-up) -------------------------


def _teardown_runtime(monkeypatch, row):
    import asyncio

    from routers.listen import runtime as runtime_module
    from starlette.websockets import WebSocketState

    runtime = object.__new__(runtime_module.ListenSessionRuntime)
    runtime.request = SimpleNamespace(
        websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED),
        uid='owner',
        source='omi',
        owner_persistence_blocked=asyncio.Event(),
    )
    runtime.state = SimpleNamespace(
        shutdown_event=asyncio.Event(),
        active=True,
        stt_terminal_failure=False,
        close_code=1006,
        current_conversation_id='conversation',
        finalization_reason=None,
    )
    runtime.client_device_context = SimpleNamespace(client_device_id='phone', platform='ios')
    runtime.client_conversation_id = 'origin'
    runtime.recording_session_id = 'session'
    runtime.recording_session_ids_by_conversation = {'conversation': 'session'}
    runtime.conversation_creation_timeout = 120
    runtime.task_supervisor = SimpleNamespace(end_session=Mock(), drain_all=AsyncMock())
    runtime._finish_live_transcription = Mock()
    runtime._record_session_transcript_outcome = Mock()
    runtime.transcripts = SimpleNamespace(
        flush_translations=AsyncMock(), flush_speaker_assignments=AsyncMock(), clear=Mock()
    )
    runtime.receiver = SimpleNamespace(
        finish=Mock(),
        flush_multi_channel_tail=AsyncMock(),
        clear=Mock(),
        raw_archive=SimpleNamespace(close=AsyncMock()),
    )
    runtime._flush_usage = AsyncMock()
    runtime.is_multi_channel = False
    runtime.language_observations = runtime.pusher_close = runtime.onboarding_handler = None
    runtime.speakers = SimpleNamespace(clear=Mock())

    async def persist(fn, *args, **kwargs):
        name = getattr(fn, '__name__', '')
        if name == '_account_deletion_blocks_owner_persistence':
            return False
        if name == 'get_conversation':
            return deepcopy(row)
        if name == 'get_in_progress_conversation_id':
            return None
        return True

    runtime.persistence = SimpleNamespace(call=persist)
    runtime.conversations = SimpleNamespace(
        disconnect_batch_producer=AsyncMock(return_value='legacy'),
        process_conversation=AsyncMock(return_value=True),
    )
    hold = AsyncMock(return_value=True)
    monkeypatch.setattr(runtime_module, 'resumable_after_drop', hold)
    monkeypatch.setattr(runtime_module.quiet_finalization, 'enabled', lambda: False)
    return runtime, hold


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [None, 'false'])
async def test_legacy_drop_finalizes_when_the_reconnect_protocol_is_off(monkeypatch, enabled):
    """With LISTEN_BATCH_RECONNECT_ENABLED unset/false a drop must not hold the capture open.

    Holding it with the protocol off strands the row: no producer exists to drain, the quiet check
    cannot end it, and every reconnect rolls into a new empty generation (the 22:06Z storm).
    """
    if enabled is None:
        monkeypatch.delenv('LISTEN_BATCH_RECONNECT_ENABLED', raising=False)
    else:
        monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', enabled)
    runtime, hold = _teardown_runtime(monkeypatch, capture())
    await runtime._teardown_components()
    hold.assert_not_awaited()
    runtime.conversations.process_conversation.assert_awaited_once_with('conversation')


@pytest.mark.asyncio
async def test_legacy_drop_hold_stays_available_behind_the_protocol_switch(monkeypatch):
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true')
    runtime, hold = _teardown_runtime(monkeypatch, capture())
    await runtime._teardown_components()
    hold.assert_awaited_once()
    runtime.conversations.process_conversation.assert_not_awaited()


CUTOFF = NOW - timedelta(hours=1)


@pytest.mark.parametrize(
    'changes,expected',
    [
        ({'finished_at': CUTOFF - timedelta(hours=5)}, True),  # empty rollover stub
        (
            {
                'finished_at': CUTOFF - timedelta(hours=5),
                'server_batch_audio_end': (CUTOFF - timedelta(hours=5)).timestamp(),
            },
            True,
        ),
        (
            {
                'finished_at': CUTOFF - timedelta(hours=5),
                'server_batch_audio_end': (CUTOFF + timedelta(minutes=5)).timestamp(),
            },
            False,
        ),
        ({'finished_at': CUTOFF + timedelta(minutes=1)}, False),
        ({'finished_at': None}, False),
        ({'finished_at': CUTOFF - timedelta(hours=5), 'status': 'processing'}, False),
        (
            {
                'finished_at': CUTOFF - timedelta(hours=5),
                'listen_batch_producer': {'version': 1, 'token': 't', 'phase': 'active'},
            },
            False,
        ),
        ({'finished_at': CUTOFF - timedelta(hours=5), 'record_lane_owner': None, 'external_data': {}}, False),
    ],
)
def test_stale_server_batch_row_requires_no_recent_committed_audio(changes, expected):
    from routers.listen.conversations import stale_server_batch_row

    assert stale_server_batch_row(capture(**changes), CUTOFF) is expected


@pytest.mark.asyncio
async def test_stale_recovery_on_a_live_socket_seals_and_deletes_an_empty_stub(monkeypatch):
    """Stale recovery used to refuse every server-batch row while its own socket was live."""
    from routers.listen import conversations as module

    row = capture(id='stub', finished_at=CUTOFF - timedelta(hours=5))
    host = live_host(row)
    host.state.current_conversation_id = 'conversation'
    host.receiver.raw_archive.finish_recording = AsyncMock()
    seal = Mock(return_value=True)
    delete = Mock(return_value=True)
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(close.conversations, 'get_conversation', lambda *a, **kw: deepcopy(row))
    monkeypatch.setattr(module.conversations_db, 'get_conversation', lambda *a, **kw: deepcopy(row))
    monkeypatch.setattr(module.lifecycle_service, 'delete_empty_recording_conversation', delete)
    controller = object.__new__(LiveConversationController)
    controller.host = host
    controller._batch_producer_tokens = {}
    controller.schedule_finalization = AsyncMock(side_effect=AssertionError('an empty stub is not finalized'))
    controller._should_report_no_audio_teardown = lambda: False

    assert await controller.process_conversation('stub', stale_cutoff=CUTOFF) is True
    host.receiver.raw_archive.finish_recording.assert_awaited_once_with('stub')
    seal.assert_called_once_with('owner', 'stub')
    assert delete.call_args.kwargs == {'allow_empty_server_batch': True}


@pytest.mark.asyncio
async def test_stale_recovery_still_refuses_a_row_with_recent_committed_audio(monkeypatch):
    from routers.listen import conversations as module

    row = capture(
        id='busy',
        finished_at=CUTOFF - timedelta(hours=5),
        server_batch_audio_start=(CUTOFF - timedelta(hours=5)).timestamp(),
        server_batch_audio_end=(NOW - timedelta(minutes=1)).timestamp(),
    )
    host = live_host(row)
    seal = Mock(side_effect=AssertionError('a row still receiving audio is not sealed'))
    monkeypatch.setattr(close, 'close_server_batch_audio', seal)
    monkeypatch.setattr(module.conversations_db, 'get_conversation', lambda *a, **kw: deepcopy(row))
    delete = Mock(side_effect=AssertionError('not deleted'))
    monkeypatch.setattr(module.lifecycle_service, 'delete_empty_recording_conversation', delete)
    controller = object.__new__(LiveConversationController)
    controller.host = host
    controller._batch_producer_tokens = {}
    controller.schedule_finalization = AsyncMock(return_value=True)
    controller._should_report_no_audio_teardown = lambda: False

    await controller.process_conversation('busy', stale_cutoff=CUTOFF)
    seal.assert_not_called()
