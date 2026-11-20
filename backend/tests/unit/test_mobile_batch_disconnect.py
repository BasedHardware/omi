"""With LISTEN_BATCH_RECONNECT_ENABLED on, a phone socket drop keeps its batch capture open; off, it finalizes."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from starlette.websockets import WebSocketState

from config import server_batch
from models.conversation_enums import ConversationStatus
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from database import conversation_quiet_checks as checks
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_conversation_quiet_finalization import NOW, ROW, _advance, store  # noqa: F401
from tests.unit.test_listen_reconnect_continuity import CaptureHarness
from utils.batch_pipeline.live import record_identity, register_recording
from utils.conversations import finalizer
from utils.conversations import quiet_finalization as quiet


@pytest.fixture(autouse=True)
def batch_env(monkeypatch):
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'true')
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.delenv('SERVER_BATCH_ONLY_ENABLED', raising=False)
    monkeypatch.delenv('SERVER_BATCH_ONLY_MOBILE_PERCENT', raising=False)


def capture(**changes):
    """A batch-owned phone capture whose first socket already committed audio."""
    return {
        'id': 'capture',
        'source': 'omi',
        'client_platform': 'ios',
        'client_device_id': 'phone',
        'language': 'en',
        'status': 'in_progress',
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'standard',
        'uses_custom_stt': False,
        'record_lane_owner': 'batch_live_v1',
        'external_data': {server_batch.MARKER: True, 'recording_session_id': 'recording'},
        'transcript_segments': [],
        'has_content': True,
        'server_batch_audio_received': True,
        'server_batch_audio_start': NOW.timestamp() - 60,
        'server_batch_audio_end': NOW.timestamp(),
        'started_at': NOW - timedelta(seconds=60),
        'finished_at': NOW,
        **changes,
    }


class Teardown:
    """The real mono teardown around one persisted row and the socket's archive."""

    def __init__(self, monkeypatch, row, *, armed=True, finalization_reason=None, tail=None):
        self.row = row
        self.calls = []
        self.arm = (
            MagicMock(return_value=armed) if not isinstance(armed, BaseException) else MagicMock(side_effect=armed)
        )
        monkeypatch.setattr(quiet, 'arm', self.arm)

        async def close():
            # The archive commits this socket's tail, merging the bounds in Firestore.
            self.calls.append('archive_close')
            if tail:
                self.row.update(tail)

        runtime = object.__new__(ListenSessionRuntime)
        runtime.request = ListenRequest(
            websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED), uid='synthetic'
        )
        runtime.state = SimpleNamespace(
            shutdown_event=asyncio.Event(),
            active=False,
            stt_terminal_failure=False,
            close_code=1001,
            current_conversation_id='capture',
            finalization_reason=finalization_reason,
        )
        runtime.conversation_creation_timeout = 120
        runtime.task_supervisor = SimpleNamespace(end_session=MagicMock(), drain_all=AsyncMock())
        runtime._finish_live_transcription = MagicMock()
        runtime._record_session_transcript_outcome = MagicMock()
        runtime.transcripts = SimpleNamespace(
            flush_translations=AsyncMock(), clear=MagicMock(), flush_speaker_assignments=AsyncMock()
        )
        runtime.receiver = SimpleNamespace(
            finish=MagicMock(),
            flush_multi_channel_tail=AsyncMock(),
            clear=MagicMock(),
            raw_archive=SimpleNamespace(close=close),
        )
        runtime.conversations = SimpleNamespace(
            process_conversation=AsyncMock(return_value=True),
            disconnect_batch_producer=AsyncMock(return_value='legacy'),
        )
        runtime._flush_usage = AsyncMock()
        runtime.is_multi_channel = False
        runtime.language_observations = runtime.pusher_close = runtime.onboarding_handler = None
        runtime.speakers = SimpleNamespace(clear=MagicMock())
        runtime.persistence = SimpleNamespace(call=self.call)
        self.runtime = runtime

    async def call(self, fn, *args, **kwargs):
        name = getattr(fn, '__name__', '')
        if name == '_account_deletion_blocks_owner_persistence':
            return False
        if name == 'get_conversation':
            return deepcopy(self.row)
        if fn is self.arm:
            return fn(*args, **kwargs)
        if name in {'update_conversation', 'get_in_progress_conversation_id', 'remove_in_progress_conversation_id'}:
            self.calls.append(name)
            return 'capture' if name == 'get_in_progress_conversation_id' else True
        raise AssertionError(name)

    async def run(self):
        await self.runtime._teardown_components()
        return self.runtime.conversations.process_conversation


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['ios', 'android'])
@pytest.mark.parametrize('source', ['omi', 'phone'])
async def test_phone_socket_drop_keeps_batch_capture_open_and_arms_quiet_check(monkeypatch, platform, source):
    # The hold is part of the reconnect protocol: only with the switch on does a drop keep the capture open.
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true')
    row = capture(client_platform=platform, source=source)
    teardown = Teardown(monkeypatch, row, tail={'server_batch_audio_end': NOW.timestamp() + 2})
    process = await teardown.run()
    process.assert_not_awaited()
    teardown.arm.assert_called_once_with('synthetic', 'capture', 120, requires_byok=False)
    # The tail is committed, the capture stays open, and the live pointer survives the reconnect.
    assert teardown.calls == ['archive_close']
    assert row['status'] == 'in_progress'
    assert row['server_batch_audio_end'] == NOW.timestamp() + 2
    assert 'server_batch_audio_closed' not in row
    teardown.runtime.transcripts.flush_speaker_assignments.assert_awaited_once_with('capture')


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['ios', 'android'])
async def test_phone_socket_drop_finalizes_when_the_reconnect_switch_is_off(monkeypatch, platform):
    # With the switch off nothing can end a hold (no producer to drain), so a held row would never be
    # sealed and every reconnect would roll into a new empty generation (11-16 22:06Z storm).
    monkeypatch.delenv('LISTEN_BATCH_RECONNECT_ENABLED', raising=False)
    row = capture(client_platform=platform)
    teardown = Teardown(monkeypatch, row, tail={'server_batch_audio_end': NOW.timestamp() + 2})
    process = await teardown.run()
    process.assert_awaited_once_with('capture')
    assert 'archive_close' not in teardown.calls  # no hold: process_conversation owns the close barrier


@pytest.mark.asyncio
async def test_desktop_batch_socket_close_still_finalizes_immediately(monkeypatch):
    row = capture(source='desktop', client_platform='macos', client_device_id='mac')
    teardown = Teardown(monkeypatch, row)
    process = await teardown.run()
    process.assert_awaited_once_with('capture')
    teardown.arm.assert_not_called()
    assert 'archive_close' not in teardown.calls  # process_conversation owns the close barrier.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    [
        'quiet_check_refused',
        'quiet_check_unavailable',
        'client_finalization_reason',
        'no_committed_audio',
        'no_quiet_check_source',
        'web_platform',
        'finalized_meanwhile',
    ],
)
async def test_phone_drop_without_a_quiet_owner_or_audio_keeps_immediate_finalization(monkeypatch, case):
    # With the switch on, these guards are what keep the drop hold from engaging.
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true')
    row = capture()
    options = {}
    if case == 'quiet_check_refused':
        options['armed'] = False
    elif case == 'quiet_check_unavailable':
        options['armed'] = RuntimeError('firestore unavailable')
    elif case == 'client_finalization_reason':
        options['finalization_reason'] = 'user_stop'
    elif case == 'no_committed_audio':
        row.update(has_content=False, server_batch_audio_received=False)
        row.pop('server_batch_audio_start')
        row.pop('server_batch_audio_end')
    elif case == 'no_quiet_check_source':
        row['source'] = 'limitless'
    elif case == 'web_platform':
        row['client_platform'] = 'web'
    elif case == 'finalized_meanwhile':
        options['tail'] = {'status': 'processing'}
    teardown = Teardown(monkeypatch, row, **options)
    process = await teardown.run()
    # Never left without a finalization owner: the socket path still closes it.
    process.assert_awaited_once_with('capture')
    assert teardown.arm.call_count == int(case != 'no_quiet_check_source')


def batch_host(controller):
    host = controller.host
    host.private_cloud_sync_enabled = True
    host.pusher_enabled = True
    host.request.language = 'en'
    host.language_profile = SimpleNamespace(primary='en', expected=('en',), source='learned')
    return controller


@pytest.mark.asyncio
@pytest.mark.parametrize('first_socket_close', ['kept_open', 'finalized'])
async def test_phone_reconnect_inside_timeout_resumes_the_same_batch_capture(monkeypatch, first_socket_close):
    harness = CaptureHarness(monkeypatch)
    first = batch_host(harness.connect())
    await first.prepare()
    cid = first.host.state.current_conversation_id
    # The first socket was admitted to server batch and committed a minute of audio.
    harness.rows[cid].update(
        capture(id=cid, started_at=harness.now - timedelta(seconds=60), finished_at=harness.now),
        external_data={**harness.rows[cid]['external_data'], server_batch.MARKER: True},
    )
    if first_socket_close == 'finalized':
        harness.rows[cid]['status'] = 'completed'  # What the drop did before this fix.
    harness.now += timedelta(seconds=35)
    second = batch_host(harness.connect())
    await second.prepare()
    if first_socket_close == 'kept_open':
        assert second.host.state.current_conversation_id == cid
        assert harness.creates == 1
        assert server_batch.owned(second.host.batch_record_capture)
    else:
        assert second.host.state.current_conversation_id != cid
        assert harness.creates == 2


def test_quiet_check_finalizes_an_open_phone_batch_capture_with_committed_audio(store, monkeypatch):
    store.rows[ROW].clear()
    store.rows[ROW].update(
        capture(id='old', external_data={server_batch.MARKER: True, 'recording_session_id': 'recording-old'})
    )
    assert quiet.arm('synthetic', 'old', 120, firestore_client=store) is True
    _advance(monkeypatch, 301)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=store) == 'queued'
    row = store.rows[ROW]
    assert row['status'] == 'processing'
    assert 'server_batch_audio_closed' not in row
    job = store.rows[('conversation_finalization_jobs', row['finalization_job_id'])]
    assert job['processing_trigger'] == 'server_recovery'


@pytest.mark.asyncio
async def test_recovery_finalizer_hands_unclosed_committed_capture_to_batch(monkeypatch):
    row = capture(status=ConversationStatus.processing.value)
    model = SimpleNamespace(status=ConversationStatus.processing, transcript_segments=[])
    monkeypatch.setattr(finalizer, '_load_admitted_conversation', AsyncMock(return_value=(None, row, model)))
    pending = MemoryStore()
    monkeypatch.setattr(
        finalizer, 'register_recording', lambda owner, data: register_recording(owner, data, store=pending, now=1)
    )
    monkeypatch.setattr(
        finalizer.lifecycle_service, 'delete_empty_recording_conversation', Mock(side_effect=AssertionError('audio'))
    )
    completion = Mock(return_value='completed')
    monkeypatch.setattr(finalizer.lifecycle_service, 'complete_server_batch_capture', completion)
    result = await finalizer.finalize_persisted_conversation(
        'synthetic',
        'capture',
        finalization_job_id='job',
        dispatch_generation=1,
        lease_epoch=1,
        trigger=finalizer.ProcessingTrigger.SERVER_RECOVERY,
    )
    assert result is finalizer.ConversationFinalizationDisposition.completed
    assert pending.rows['jobs', record_identity('synthetic', 'capture')[1]]['state'] == 'record_pending'
    completion.assert_called_once_with('synthetic', 'capture', row, 'job', 1, 1)
