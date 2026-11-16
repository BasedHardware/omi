"""Synthetic disconnects use real custody metadata and finalization transactions."""

import asyncio

from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketException
from starlette.websockets import WebSocketState

from config import listen_reconnect as config
from config.server_batch import MARKER
from database import listen_batch_reconnect as reconnect, server_batch_audio, recording_sessions
from database import conversation_quiet_checks as checks
from routers.listen.conversations import LiveConversationController
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from tests.unit.test_conversation_quiet_finalization import store, NOW, ROW, SESSION, _advance, _job
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline.live import register_recording, record_identity
from utils.conversations import quiet_finalization as quiet


@pytest.fixture
def batch(store, monkeypatch):
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true')
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'true')
    row = store.rows[ROW]
    row.update(
        id='old',
        source='omi',
        client_device_id='phone',
        started_at=NOW,
        created_at=NOW,
        record_lane_owner='batch_live_v1',
        private_cloud_sync_enabled=True,
        language='en',
        server_batch_audio_start=NOW.timestamp(),
        server_batch_audio_end=NOW.timestamp() + 1,
        server_batch_audio_received=True,
    )
    row['external_data'].update({MARKER: True, 'recording_origin_id': 'origin'})
    store.rows[('users', 'synthetic')] = {'time_zone': 'UTC', 'private_cloud_sync_enabled': True}
    return store


def claim(db, token, at=NOW, **extra):
    return reconnect.claim(
        'synthetic',
        'old',
        'recording-old',
        token=token,
        origin_id=extra.get('origin_id', 'origin'),
        source=extra.get('source', 'omi'),
        device_id=extra.get('device_id', 'phone'),
        now=at,
        timeout=1800,
        firestore_client=db,
    )


def disconnect(db, token, at=NOW, *, timeout=1800, terminal=False):
    return reconnect.disconnect(
        'synthetic',
        'old',
        'recording-old',
        token,
        disconnected_at=at,
        now=at,
        timeout=timeout,
        terminal=terminal,
        firestore_client=db,
    )


def test_eighteen_sockets_in_an_hour_keep_one_chapter_and_one_work_obligation(batch, monkeypatch):
    previous = None
    for i in range(18):
        at = NOW + timedelta(seconds=i * 195)
        token = f'producer-{i}'
        assert claim(batch, token, at) == 'claimed'
        if previous:
            assert disconnect(batch, previous, at) == 'fenced'
            assert not server_batch_audio.note_server_batch_audio(
                'synthetic', 'old', at.timestamp(), at.timestamp() + 1, producer_token=previous, firestore_client=batch
            )
        finish = at + timedelta(seconds=120)
        assert server_batch_audio.note_server_batch_audio(
            'synthetic', 'old', at.timestamp(), finish.timestamp(), producer_token=token, firestore_client=batch
        )
        assert disconnect(batch, token, finish) == 'held'
        _advance(monkeypatch, (finish - NOW).total_seconds())
        quiet.arm('synthetic', 'old', 1800, firestore_client=batch)
        assert batch.rows[ROW]['status'] == 'in_progress'
        assert 'finalization_job_id' not in batch.rows[ROW]
        previous = token
    assert len([p for p in batch.rows if p[:3] == ('users', 'synthetic', 'conversations')]) == 1
    expiry = finish + timedelta(seconds=120)
    _advance(monkeypatch, (expiry - NOW).total_seconds())
    assert (
        quiet.run(checks.quiet_check_id('synthetic', 'old'), _job(batch)['dispatch_generation'], firestore_client=batch)
        == 'queued'
    )
    assert batch.rows[ROW]['server_batch_audio_closed'] is True
    assert batch.rows[ROW]['finalization_revision'] == 1
    assert (
        quiet.run(checks.quiet_check_id('synthetic', 'old'), _job(batch)['dispatch_generation'], firestore_client=batch)
        == 'done'
    )
    assert batch.rows[ROW]['finalization_revision'] == 1
    jobs = MemoryStore()
    for _ in range(3):
        assert register_recording('synthetic', deepcopy(batch.rows[ROW]), store=jobs, now=expiry.timestamp())
    _, segment = record_identity('synthetic', 'old')
    assert list(jobs.rows) == [('jobs', segment)]


@pytest.mark.parametrize('seconds,expected', [(119, 'claimed'), (120, 'expired'), (121, 'expired')])
def test_exact_grace_boundary(batch, seconds, expected):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a') == 'held'
    assert claim(batch, 'b', NOW + timedelta(seconds=seconds)) == expected


def test_durable_deadline_replay_and_reconnect_against_stale_check(batch, monkeypatch):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a') == 'held'
    quiet.arm('synthetic', 'old', 1800, firestore_client=batch)
    original = deepcopy(batch.rows[ROW][config.FIELD])
    assert disconnect(batch, 'a', NOW + timedelta(seconds=50)) == 'held'
    assert batch.rows[ROW][config.FIELD] == original
    assert claim(batch, 'b', NOW + timedelta(seconds=80)) == 'claimed'
    _advance(monkeypatch, 120)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=batch) == 'deferred'
    assert batch.rows[ROW]['status'] == 'in_progress'
    assert not batch.rows[ROW].get('server_batch_audio_closed')


def controller_for(db, token):
    async def call(fn, *args, **kwargs):
        return fn(*args, firestore_client=db, **kwargs)

    host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic', source='omi'),
        client_conversation_id='origin',
        client_device_context=SimpleNamespace(client_device_id='phone', platform='ios'),
        is_multi_channel=False,
        recording_session_id='recording-old',
        recording_session_ids_by_conversation={'old': 'recording-old'},
        conversation_creation_timeout=1800,
        persistence=SimpleNamespace(call=call),
        receiver=SimpleNamespace(raw_archive=SimpleNamespace(close=AsyncMock())),
    )
    controller = LiveConversationController(host, clock=lambda: NOW)
    controller._batch_producer_tokens['old'] = token
    return controller


@pytest.mark.parametrize('reason', sorted(config.TERMINAL_REASONS))
@pytest.mark.asyncio
async def test_explicit_end_never_gets_grace(batch, reason):
    assert claim(batch, 'a') == 'claimed'
    controller = controller_for(batch, 'a')
    assert await controller.disconnect_batch_producer('old', reason=reason) == 'ended'
    controller.host.receiver.raw_archive.close.assert_awaited_once()
    assert claim(batch, 'b', NOW + timedelta(seconds=1)) == 'expired'


def test_real_quiet_timeout_wins_over_grace(batch, monkeypatch):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a', NOW + timedelta(seconds=110), timeout=120) == 'held'
    _advance(monkeypatch, 110)
    quiet.arm('synthetic', 'old', 120, firestore_client=batch)
    assert _job(batch)['due_at'] == NOW + timedelta(seconds=120)
    _advance(monkeypatch, 120)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=batch) == 'queued'


@pytest.mark.parametrize('status', ['processing', 'completed', 'failed'])
def test_terminal_obligation_stays_immutable_and_separate(batch, status):
    assert claim(batch, 'a') == 'claimed'
    batch.rows[ROW].update(status=status, finalization_job_id='immutable-job', finalization_revision=7)
    before = deepcopy(batch.rows[ROW])
    assert claim(batch, 'b') == 'refused'
    assert disconnect(batch, 'a') == 'fenced'
    assert batch.rows[ROW] == before


def test_competing_socket_and_aba_teardown_are_fenced(batch):
    assert claim(batch, 'a') == 'claimed'
    assert claim(batch, 'b') == 'busy'
    assert disconnect(batch, 'a') == 'held'
    assert claim(batch, 'b', NOW + timedelta(seconds=5)) == 'claimed'
    assert disconnect(batch, 'a', NOW + timedelta(seconds=6)) == 'fenced'
    assert not reconnect.renew(
        'synthetic', 'old', 'recording-old', 'a', now=NOW + timedelta(seconds=6), firestore_client=batch
    )
    assert batch.rows[ROW][config.FIELD]['token'] == 'b'
    assert not server_batch_audio.close_server_batch_audio(
        'synthetic', 'old', producer_token='a', firestore_client=batch
    )


def test_expired_producer_late_frames_cannot_mutate_replacement(batch):
    assert claim(batch, 'a') == 'claimed'
    assert claim(batch, 'b', NOW + timedelta(seconds=120)) == 'claimed'
    before = deepcopy(batch.rows[ROW])
    assert not server_batch_audio.note_server_batch_audio_received(
        'synthetic', 'old', producer_token='a', firestore_client=batch
    )
    assert not server_batch_audio.note_server_batch_audio(
        'synthetic', 'old', NOW.timestamp(), NOW.timestamp() + 5, producer_token='a', firestore_client=batch
    )
    assert disconnect(batch, 'a') == 'fenced'
    assert batch.rows[ROW] == before


@pytest.mark.parametrize('identity', [{'origin_id': 'other'}, {'device_id': 'other'}, {'source': 'phone'}])
def test_identity_partition(batch, identity):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a') == 'held'
    assert claim(batch, 'b', NOW + timedelta(seconds=10), **identity) in {'expired', 'refused'}


@pytest.mark.parametrize('boundary', ['day', 'span', 'calendar'])
def test_boundaries_cannot_be_extended(batch, boundary):
    if boundary == 'day':
        batch.rows[ROW]['started_at'] = NOW - timedelta(seconds=10)
    elif boundary == 'span':
        batch.rows[ROW]['started_at'] = NOW - timedelta(hours=4)
    else:
        batch.rows[ROW]['external_data']['calendar_meeting_context'] = {
            'start_time': NOW - timedelta(hours=1),
            'end_time': NOW,
            'calendar_event_id': 'synthetic-event',
        }
    assert claim(batch, 'a') == 'expired'


@pytest.mark.parametrize('guard', ['deleted', 'discarded', 'is_locked'])
def test_privacy_and_lock_do_not_reopen(batch, guard):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a') == 'held'
    batch.rows[ROW][guard] = True
    before = deepcopy(batch.rows[ROW])
    if guard == 'deleted':
        with pytest.raises(Exception):
            claim(batch, 'b')
    else:
        assert claim(batch, 'b') == 'refused'
    assert batch.rows[ROW] == before


def test_session_open_and_legacy_lease_renew_cannot_extend_grace(batch):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a') == 'held'
    expiry = batch.rows[SESSION]['lease_expires_at']
    recording_sessions.create_or_get_recording_session('synthetic', 'recording-old', 'old', firestore_client=batch)
    assert batch.rows[SESSION]['lease_expires_at'] == expiry
    assert not recording_sessions.renew_recording_session_lease(
        'synthetic', 'recording-old', 'old', firestore_client=batch
    )


@pytest.mark.asyncio
async def test_failed_archive_drain_does_not_publish_grace_or_close(batch):
    assert claim(batch, 'a') == 'claimed'
    controller = controller_for(batch, 'a')
    controller.host.receiver.raw_archive.close.side_effect = TimeoutError('synthetic commit pending')
    with pytest.raises(TimeoutError):
        await controller.disconnect_batch_producer('old', reason=None)
    assert batch.rows[ROW][config.FIELD]['phase'] == 'active'
    assert not batch.rows[ROW].get('server_batch_audio_closed')


@pytest.mark.asyncio
async def test_kill_switch_restores_immediate_finalization_choice(batch, monkeypatch):
    assert claim(batch, 'a') == 'claimed'
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'off')
    assert await controller_for(batch, 'a').disconnect_batch_producer('old', reason=None) == 'ended'
    assert batch.rows[ROW][config.FIELD]['deadline_at'] == NOW


def test_dark_rollout_switch_and_bounded_configuration(monkeypatch):
    monkeypatch.delenv('LISTEN_BATCH_RECONNECT_ENABLED', raising=False)
    assert not config.enabled()
    for value in ('false', 'off', '0', '', 'typo', 'yes'):
        monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', value)
        assert not config.enabled()
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', ' TRUE ')
    assert config.enabled()
    for value, expected in [('75', 75), ('9999', 120), ('-1', 1), ('bad', 120)]:
        monkeypatch.setenv('LISTEN_BATCH_RECONNECT_GRACE_SECONDS', value)
        assert config.grace_seconds() == expected


@pytest.mark.asyncio
async def test_controller_claim_rejects_competing_socket(batch):
    assert claim(batch, 'a') == 'claimed'
    controller = controller_for(batch, 'b')
    with pytest.raises(WebSocketException) as error:
        await controller._claim_batch_producer('old', deepcopy(batch.rows[ROW]))
    assert error.value.code == 1013
    assert batch.rows[ROW][config.FIELD]['token'] == 'a'


@pytest.mark.asyncio
@pytest.mark.parametrize('close_code', [1000, 1001, 1006, 1011])
@pytest.mark.parametrize(
    'reason,enabled,finalizes', [(None, True, False), ('user_stop', True, True), (None, False, True)]
)
async def test_real_teardown_routes_close_stop_and_kill(batch, monkeypatch, close_code, reason, enabled, finalizes):
    assert claim(batch, 'a') == 'claimed'
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = ListenRequest(
        websocket=SimpleNamespace(client_state=WebSocketState.DISCONNECTED), uid='synthetic'
    )
    runtime.state = SimpleNamespace(
        shutdown_event=asyncio.Event(),
        active=True,
        stt_terminal_failure=False,
        close_code=close_code,
        current_conversation_id='old',
        finalization_reason=reason,
    )
    runtime.client_device_context = SimpleNamespace(client_device_id='phone', platform='ios')
    runtime.client_conversation_id = 'origin'
    runtime.recording_session_id = 'recording-old'
    runtime.recording_session_ids_by_conversation = {'old': 'recording-old'}
    runtime.conversation_creation_timeout = 1800
    runtime.task_supervisor = SimpleNamespace(end_session=MagicMock(), drain_all=AsyncMock())
    runtime._finish_live_transcription = MagicMock()
    runtime._record_session_transcript_outcome = MagicMock()
    runtime.transcripts = SimpleNamespace(
        flush_translations=AsyncMock(), flush_speaker_assignments=AsyncMock(), clear=MagicMock()
    )
    runtime.receiver = SimpleNamespace(
        finish=MagicMock(),
        flush_multi_channel_tail=AsyncMock(),
        clear=MagicMock(),
        raw_archive=SimpleNamespace(close=AsyncMock()),
    )
    runtime._flush_usage = AsyncMock()
    runtime.is_multi_channel = False
    runtime.language_observations = runtime.pusher_close = runtime.onboarding_handler = None
    runtime.speakers = SimpleNamespace(clear=MagicMock())

    async def persist(fn, *args, **kwargs):
        name = getattr(fn, '__name__', '')
        if name == '_account_deletion_blocks_owner_persistence':
            return False
        if name == 'get_conversation':
            return deepcopy(batch.rows[ROW])
        if name == 'update_conversation':
            batch.transaction().update(batch.document('/'.join(ROW)), args[2])
            return True
        if name == 'get_in_progress_conversation_id':
            return None
        return fn(*args, firestore_client=batch, **kwargs)

    runtime.persistence = SimpleNamespace(call=persist)
    runtime.conversations = LiveConversationController(runtime, clock=lambda: NOW)
    runtime.conversations._batch_producer_tokens['old'] = 'a'
    process = AsyncMock(return_value=True)
    runtime.conversations.process_conversation = process
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', str(enabled).lower())
    await runtime._teardown_components()
    assert process.await_count == int(finalizes)
    assert batch.rows[ROW][config.FIELD]['phase'] == ('ended' if finalizes else 'disconnected')
    if not finalizes:
        assert _job(batch)['due_at'] == NOW + timedelta(seconds=120)
        assert 'finalization_job_id' not in batch.rows[ROW]


def test_manual_title_during_grace_does_not_strand_the_finite_end(batch, monkeypatch):
    assert claim(batch, 'a') == 'claimed'
    assert disconnect(batch, 'a') == 'held'
    batch.rows[ROW]['user_title'] = 'Synthetic meeting title'
    quiet.arm('synthetic', 'old', 1800, firestore_client=batch)
    _advance(monkeypatch, 120)
    assert quiet.run(checks.quiet_check_id('synthetic', 'old'), 1, firestore_client=batch) == 'queued'
    assert batch.rows[ROW]['finalization_revision'] == 1
    assert batch.rows[ROW]['user_title'] == 'Synthetic meeting title'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [False, RuntimeError('synthetic quiet arm refused')])
async def test_no_durable_quiet_owner_restores_immediate_end(batch, monkeypatch, failure):
    assert claim(batch, 'a') == 'claimed'
    controller = controller_for(batch, 'a')
    monkeypatch.setattr(
        controller,
        '_persist_policy_and_arm_quiet_check',
        AsyncMock(return_value=False) if failure is False else AsyncMock(side_effect=failure),
    )
    assert await controller.disconnect_batch_producer('old', reason=None) == 'ended'
    assert batch.rows[ROW][config.FIELD]['phase'] == 'ended'


@pytest.mark.asyncio
@pytest.mark.parametrize('platform', ['web', 'macos', 'windows', None])
async def test_non_mobile_session_keeps_its_existing_close_protocol(batch, platform):
    controller = controller_for(batch, 'a')
    controller._batch_producer_tokens.clear()
    controller.host.client_device_context.platform = platform
    assert await controller._claim_batch_producer('old', deepcopy(batch.rows[ROW])) is True
    assert config.FIELD not in batch.rows[ROW]


@pytest.mark.asyncio
async def test_disable_between_disconnect_and_reconnect_ends_without_resuming(batch, monkeypatch):
    assert claim(batch, 'original') == 'claimed'
    assert disconnect(batch, 'original') == 'held'
    quiet.arm('synthetic', 'old', 1800, firestore_client=batch)
    assert _job(batch)['due_at'] == NOW + timedelta(seconds=120)
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'false')
    _advance(monkeypatch, 1)
    controller = controller_for(batch, 'replacement')
    controller.clock = lambda: NOW + timedelta(seconds=1)
    from routers.listen import conversations as controller_module

    persist = controller.host.persistence.call

    async def reconnect_call(fn, *args, **kwargs):
        if fn is controller_module.lifecycle_service.open_live_recording_session:
            return {
                'requires_rollover': False,
                'conversation_id': 'old',
                'conversation_snapshot': deepcopy(batch.rows[ROW]),
            }
        return await persist(fn, *args, **kwargs)

    controller.host.persistence.call = reconnect_call
    monkeypatch.setattr(controller_module, 'server_batch_capture_compatible', lambda *_: True)
    monkeypatch.setattr(controller_module, 'server_batch_continuation_language', lambda *_: None)
    # Exercise the real resume path, including its pre-claim continuity filter.
    assert not await controller._resume_continuation(
        {'conversation_id': 'old', 'recording_session_id': 'recording-old'}
    )
    state = batch.rows[ROW][config.FIELD]
    assert state['token'] == 'original'
    assert state['phase'] == 'ended'
    assert state['deadline_at'] == NOW + timedelta(seconds=1)
    assert _job(batch)['due_at'] == NOW + timedelta(seconds=1)
    assert (
        quiet.run(checks.quiet_check_id('synthetic', 'old'), _job(batch)['dispatch_generation'], firestore_client=batch)
        == 'queued'
    )
    assert batch.rows[ROW]['status'] == 'processing'
    assert batch.rows[ROW]['server_batch_audio_closed'] is True
    assert batch.rows[ROW]['finalization_revision'] == 1
    terminal = deepcopy(batch.rows[ROW])
    assert not await controller._claim_batch_producer('old', terminal)
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true')
    assert claim(batch, 'replacement', NOW + timedelta(seconds=2)) == 'refused'
    assert batch.rows[ROW] == terminal


def test_disabled_reader_expires_hold_without_waiting_for_stored_grace(batch, monkeypatch):
    assert claim(batch, 'original') == 'claimed'
    assert disconnect(batch, 'original') == 'held'
    quiet.arm('synthetic', 'old', 1800, firestore_client=batch)
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'false')
    _advance(monkeypatch, 1)
    # A wake can arrive early or be replayed; switch-off beats the stored deadline.
    assert (
        quiet.run(checks.quiet_check_id('synthetic', 'old'), _job(batch)['dispatch_generation'], firestore_client=batch)
        == 'queued'
    )
    assert batch.rows[ROW][config.FIELD]['phase'] == 'ended'
    assert batch.rows[ROW][config.FIELD]['deadline_at'] == NOW + timedelta(seconds=1)
    assert batch.rows[ROW]['finalization_revision'] == 1


@pytest.mark.asyncio
async def test_dark_deploy_is_legacy_until_enable_and_rollback_does_not_steal_live_owner(batch, monkeypatch):
    monkeypatch.delenv('LISTEN_BATCH_RECONNECT_ENABLED')
    controller = controller_for(batch, 'unused')
    controller._batch_producer_tokens.clear()
    before = deepcopy(batch.rows)
    # Default-off code accepts the unmarked legacy path, without installing a token.
    assert await controller._claim_batch_producer('old', deepcopy(batch.rows[ROW]))
    assert claim(batch, 'unused') == 'disabled'
    assert batch.rows == before
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'true')
    assert claim(batch, 'current') == 'claimed'
    monkeypatch.setenv('LISTEN_BATCH_RECONNECT_ENABLED', 'false')
    active = deepcopy(batch.rows)
    assert not await controller._claim_batch_producer('old', deepcopy(batch.rows[ROW]))
    assert batch.rows == active  # Rollback must drain the live owner on the new revision.
    assert disconnect(batch, 'current', terminal=True) == 'ended'
    quiet.arm('synthetic', 'old', 1800, firestore_client=batch)
    assert (
        quiet.run(checks.quiet_check_id('synthetic', 'old'), _job(batch)['dispatch_generation'], firestore_client=batch)
        == 'queued'
    )
    assert batch.rows[ROW]['status'] == 'processing'
