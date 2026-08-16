"""Hermetic native-listen wire contracts for STT and the pusher bridge.

These tests deliberately keep the HTTP route, listen runtime, provider socket,
and ``ListenPusherSession`` real. Only auth/storage and remote WebSocket peers
are controlled by the hermetic E2E harness.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

import pytest

from fakes.firestore import get_mock_firestore
from fakes.listen_pusher_wire import (
    PUSHER_PROCESS_CONVERSATION,
    PUSHER_TRANSCRIPT,
    RejectingParakeetPeer,
    ScriptedModulatePeer,
    ScriptedParakeetPeer,
    ScriptedPusherPeer,
    clear_finalization_jobs,
    complete_finalization_job,
    finalization_jobs_for_uid,
    install_deterministic_listen_timing,
    install_fake_firestore_transactions,
    terminalize_finalization_job,
)
from listen_test_helpers import is_conversation_session_event, is_ready_event, receive_until, seed_listen_user

NATIVE_LISTEN_URL = (
    '/v4/listen?language=en&sample_rate=8000&codec=pcm8&source=omi&stt_service=parakeet&vad_gate=disabled'
)
NATIVE_AUTH_HEADERS = {'Authorization': 'Bearer dev-token'}
PARAKEET_TRANSCRIPT = 'Parakeet wire-contract transcript.'
MODULATE_TRANSCRIPT = 'Modulate wire-contract transcript.'
PCM8_AUDIO_FRAME = b'\x80' * 480
MULTI_LANGUAGE_PARAKEET_LISTEN_URL = (
    '/v4/listen?language=es&sample_rate=8000&codec=pcm8&source=omi&stt_service=parakeet&vad_gate=disabled'
)


def _configure_live_wire_contract(monkeypatch: Any, pusher: ScriptedPusherPeer, parakeet_api_url: str) -> None:
    """Point only the production network clients at deterministic loopback peers."""

    import routers.listen.runtime as listen_runtime
    import utils.pusher as pusher_client

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', parakeet_api_url)
    monkeypatch.setattr(listen_runtime, 'PUSHER_ENABLED', True)
    monkeypatch.setattr(pusher_client, 'PusherAPI', pusher.api_url)

    # The pusher breaker is process-global.  Reset its transport-only state so
    # another hermetic test cannot make this route skip its loopback peer.
    breaker = pusher_client.get_circuit_breaker()
    breaker._state = pusher_client.CircuitState.CLOSED  # type: ignore[reportPrivateUsage]
    breaker._failures.clear()  # type: ignore[reportPrivateUsage]
    breaker._probe_in_progress = False  # type: ignore[reportPrivateUsage]


def _configure_modulate_loopback(monkeypatch: Any, modulate: ScriptedModulatePeer) -> None:
    """Route only Velma-2's real WebSocket client to the deterministic peer."""

    import utils.stt.streaming as streaming

    original_connect = streaming.websockets.connect

    async def connect_loopback(uri: str, *args: Any, **kwargs: Any) -> Any:
        parsed = urlsplit(uri)
        if parsed.hostname == 'modulate-developer-apis.com' and parsed.path == '/api/velma-2-stt-streaming':
            loopback_uri = f'{modulate.api_url}{parsed.path}'
            if parsed.query:
                loopback_uri = f'{loopback_uri}?{parsed.query}'
            return await original_connect(loopback_uri, *args, **kwargs)
        return await original_connect(uri, *args, **kwargs)

    monkeypatch.setenv('MODULATE_API_KEY', 'loopback-modulate-key')
    monkeypatch.setattr(streaming, 'stt_service_models', ('parakeet', 'modulate-velma-2'))
    monkeypatch.setattr(streaming.websockets, 'connect', connect_loopback)


def _open_native_listen(websocket: Any) -> dict[str, Any]:
    """Assert native dependency auth reaches the real accepted-socket runtime."""

    session = receive_until(websocket, is_conversation_session_event)
    ready = receive_until(websocket, is_ready_event)
    assert session['status'] == 'in_progress'
    assert ready['status'] == 'ready'
    return session


def _receive_parakeet_segment(websocket: Any) -> list[dict[str, Any]]:
    segments = receive_until(
        websocket,
        lambda payload: isinstance(payload, list) and bool(payload) and payload[0].get('text') == PARAKEET_TRANSCRIPT,
    )
    assert segments[0]['stt_provider'] == 'parakeet-wire-peer'
    return segments


def _receive_modulate_segment(websocket: Any) -> list[dict[str, Any]]:
    segments = receive_until(
        websocket,
        lambda payload: isinstance(payload, list) and bool(payload) and payload[0].get('text') == MODULATE_TRANSCRIPT,
    )
    assert segments[0]['speaker'] == 'SPEAKER_00'
    return segments


def _make_live_conversation_stale(uid: str, conversation_id: str) -> None:
    """Advance persisted state; the test releases the real lifecycle loop explicitly."""

    get_mock_firestore().collection('users').document(uid).collection('conversations').document(conversation_id).update(
        {'finished_at': datetime.now(timezone.utc) - timedelta(minutes=3)}
    )


def _assert_durable_finalization_identity(payload: dict[str, Any], conversation_id: str) -> None:
    assert payload['conversation_id'] == conversation_id
    assert payload['language'] == 'en'
    assert payload['byok_keys'] == {}
    assert isinstance(payload['finalization_job_id'], str) and payload['finalization_job_id']
    assert payload['dispatch_generation'] == 1


def test_listen_pusher_wire_contract_native_happy_path_and_explicit_parakeet_route(
    client, test_uid, monkeypatch, fake_firestore
):
    """Native auth -> real Parakeet dispatch -> client segment -> production pusher transcript frame."""

    async def pusher_success(_peer, _frame, _websocket):
        return None

    parakeet = ScriptedParakeetPeer(segment_text=PARAKEET_TRANSCRIPT).start()
    pusher = ScriptedPusherPeer(pusher_success).start()
    try:
        _configure_live_wire_contract(monkeypatch, pusher, parakeet.api_url)
        clear_finalization_jobs(fake_firestore, test_uid)
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=True)

        with client.websocket_connect(NATIVE_LISTEN_URL, headers=NATIVE_AUTH_HEADERS) as websocket:
            session = _open_native_listen(websocket)
            pusher.wait_for_connections(1)
            websocket.send_bytes(PCM8_AUDIO_FRAME)
            parakeet.wait_for_audio(1)
            _receive_parakeet_segment(websocket)
            transcript = pusher.wait_for_frames(PUSHER_TRANSCRIPT, 1)[0]

        # Explicit native query routing reached the real Parakeet /v3 stream,
        # rather than the default language-based Deepgram selection.
        assert parakeet.paths == ['/v3/stream?sample_rate=8000']
        assert pusher.paths[0].startswith('/v1/trigger/listen?')
        assert 'uid=123' in pusher.paths[0]
        assert 'sample_rate=8000' in pusher.paths[0]
        assert transcript.connection == 1
        assert transcript.payload['memory_id'] == session['conversation_id']
        assert transcript.payload['segments'][0]['id'] == 'parakeet-wire-1'
        assert transcript.payload['segments'][0]['text'] == PARAKEET_TRANSCRIPT
        assert [frame.header_type for frame in pusher.frames] == [PUSHER_TRANSCRIPT]
    finally:
        clear_finalization_jobs(fake_firestore, test_uid)
        pusher.close()
        parakeet.close()


def test_listen_pusher_wire_contract_multilingual_explicit_parakeet_routes_to_modulate(
    client, test_uid, monkeypatch, fake_firestore
):
    """An explicit Parakeet preference cannot bypass streaming language capability."""

    async def pusher_success(_peer, _frame, _websocket):
        return None

    parakeet = ScriptedParakeetPeer(segment_text=PARAKEET_TRANSCRIPT).start()
    modulate = ScriptedModulatePeer(segment_text=MODULATE_TRANSCRIPT).start()
    pusher = ScriptedPusherPeer(pusher_success).start()
    try:
        _configure_live_wire_contract(monkeypatch, pusher, parakeet.api_url)
        _configure_modulate_loopback(monkeypatch, modulate)
        clear_finalization_jobs(fake_firestore, test_uid)
        seed_listen_user(test_uid, uses_custom_stt=False)

        with client.websocket_connect(MULTI_LANGUAGE_PARAKEET_LISTEN_URL, headers=NATIVE_AUTH_HEADERS) as websocket:
            session = _open_native_listen(websocket)
            pusher.wait_for_connections(1)
            websocket.send_bytes(PCM8_AUDIO_FRAME)
            modulate.wait_for_audio(1)
            _receive_modulate_segment(websocket)
            transcript = pusher.wait_for_frames(PUSHER_TRANSCRIPT, 1)[0]

        # The live Modulate API represents automatic multi-language selection
        # by omitting ``language``. The full route reaches that real wire
        # boundary, while the configured Parakeet peer remains untouched.
        assert modulate.connection_count == 1
        modulate_request = urlsplit(modulate.paths[0])
        assert modulate_request.path == '/api/velma-2-stt-streaming'
        assert 'language=' not in modulate_request.query
        assert 'sample_rate=8000' in modulate_request.query
        assert parakeet.connection_count == 0
        assert parakeet.paths == []
        assert transcript.payload['memory_id'] == session['conversation_id']
        assert transcript.payload['segments'][0]['text'] == MODULATE_TRANSCRIPT
    finally:
        clear_finalization_jobs(fake_firestore, test_uid)
        pusher.close()
        modulate.close()
        parakeet.close()


def test_listen_pusher_wire_contract_reconnect_replays_one_durable_finalization(
    client, test_uid, monkeypatch, fake_firestore
):
    """A lost pusher transport replays exactly the same durable request on reconnect."""

    async def disconnect_then_ack(peer, frame, websocket):
        if frame.connection == 1:
            await websocket.close(code=1012, reason='scripted pusher reconnect')
            return
        complete_finalization_job(fake_firestore, frame.payload['finalization_job_id'])
        await peer.send_result(websocket, {'conversation_id': frame.payload['conversation_id'], 'success': True})

    parakeet = ScriptedParakeetPeer(segment_text=PARAKEET_TRANSCRIPT).start()
    pusher = ScriptedPusherPeer(disconnect_then_ack).start()
    try:
        _configure_live_wire_contract(monkeypatch, pusher, parakeet.api_url)
        timing = install_deterministic_listen_timing(monkeypatch)
        install_fake_firestore_transactions(monkeypatch, fake_firestore)
        clear_finalization_jobs(fake_firestore, test_uid)
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=True)

        with client.websocket_connect(NATIVE_LISTEN_URL, headers=NATIVE_AUTH_HEADERS) as websocket:
            try:
                session = _open_native_listen(websocket)
                websocket.send_bytes(PCM8_AUDIO_FRAME)
                _receive_parakeet_segment(websocket)
                pusher.wait_for_frames(PUSHER_TRANSCRIPT, 1)
                _make_live_conversation_stale(test_uid, session['conversation_id'])
                timing.trigger_lifecycle_tick()

                finalizations = pusher.wait_for_frames(PUSHER_PROCESS_CONVERSATION, 2)
                pusher.wait_for_finalization_actions(2)

                # The second observed finalization is a protocol replay, not a new
                # lifecycle/fanout.  Its durable identity must be byte-for-byte the
                # same logical request across the real session reconnect.
                first, replay = finalizations
                frame_types = [frame.header_type for frame in pusher.frames]
                assert frame_types.index(PUSHER_TRANSCRIPT) < frame_types.index(PUSHER_PROCESS_CONVERSATION)
                _assert_durable_finalization_identity(first.payload, session['conversation_id'])
                assert replay.connection == 2
                assert replay.payload == first.payload
                jobs = finalization_jobs_for_uid(fake_firestore, test_uid)
                assert len(jobs) == 1
                assert jobs[0]['job_id'] == first.payload['finalization_job_id']
                assert jobs[0]['dispatch_generation'] == first.payload['dispatch_generation']
                assert len(pusher.frames_of_type(PUSHER_PROCESS_CONVERSATION)) == 2
            finally:
                timing.close()

        assert pusher.connection_count == 2
        assert len(pusher.frames_of_type(PUSHER_PROCESS_CONVERSATION)) == 2
        jobs_after_teardown = finalization_jobs_for_uid(fake_firestore, test_uid)
        assert len(jobs_after_teardown) == 1
        assert jobs_after_teardown[0]['status'] == 'completed'
    finally:
        clear_finalization_jobs(fake_firestore, test_uid)
        pusher.close()
        parakeet.close()


@pytest.mark.parametrize(
    ('terminal_result', 'case'),
    [
        ({'error': 'attempt_budget_exhausted', 'terminal': True}, 'terminal'),
        ({'fenced': True}, 'fenced'),
    ],
)
def test_listen_pusher_wire_contract_terminal_or_fenced_response_is_not_replayed(
    client, test_uid, monkeypatch, fake_firestore, terminal_result, case
):
    """A terminal 201 is consumed before a later transcript forces a real pusher reconnect."""

    async def reply_then_disconnect(peer, frame, websocket):
        if frame.connection != 1:
            return
        terminalize_finalization_job(
            fake_firestore,
            frame.payload['finalization_job_id'],
            fenced=bool(terminal_result.get('fenced')),
        )
        await peer.send_result(websocket, {'conversation_id': frame.payload['conversation_id']} | terminal_result)
        await websocket.close(code=1012, reason=f'scripted {case} transport close')

    parakeet = ScriptedParakeetPeer(segment_text=PARAKEET_TRANSCRIPT).start()
    pusher = ScriptedPusherPeer(reply_then_disconnect).start()
    try:
        _configure_live_wire_contract(monkeypatch, pusher, parakeet.api_url)
        timing = install_deterministic_listen_timing(monkeypatch)
        install_fake_firestore_transactions(monkeypatch, fake_firestore)
        clear_finalization_jobs(fake_firestore, test_uid)
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=True)

        with client.websocket_connect(NATIVE_LISTEN_URL, headers=NATIVE_AUTH_HEADERS) as websocket:
            try:
                session = _open_native_listen(websocket)
                websocket.send_bytes(PCM8_AUDIO_FRAME)
                _receive_parakeet_segment(websocket)
                pusher.wait_for_frames(PUSHER_TRANSCRIPT, 1)
                _make_live_conversation_stale(test_uid, session['conversation_id'])
                timing.trigger_lifecycle_tick()

                pusher.wait_for_frames(PUSHER_PROCESS_CONVERSATION, 1)
                pusher.wait_for_finalization_actions(1)

                # The closed peer forces the real pusher receiver through its
                # production reconnect path.  A terminal 201 must have removed
                # the durable request before that second transport is opened.
                websocket.send_bytes(PCM8_AUDIO_FRAME)
                _receive_parakeet_segment(websocket)
                parakeet.wait_for_audio(2)
                pusher.wait_for_connections(2)
                finalizations = pusher.frames_of_type(PUSHER_PROCESS_CONVERSATION)
                assert len(finalizations) == 1
                _assert_durable_finalization_identity(finalizations[0].payload, session['conversation_id'])
            finally:
                timing.close()

        assert pusher.connection_count == 2
    finally:
        clear_finalization_jobs(fake_firestore, test_uid)
        pusher.close()
        parakeet.close()


def test_listen_pusher_wire_contract_provider_connect_failure_is_terminal(
    client, test_uid, monkeypatch, fake_firestore
):
    """A provider-connect failure sends bounded stt_failed/1011 before pusher work exists."""

    async def unexpected_finalization(_peer, _frame, _websocket):
        raise AssertionError('provider startup failure must not reach pusher finalization')

    parakeet = RejectingParakeetPeer().start()
    pusher = ScriptedPusherPeer(unexpected_finalization).start()
    try:
        _configure_live_wire_contract(monkeypatch, pusher, parakeet.api_url)
        install_fake_firestore_transactions(monkeypatch, fake_firestore)
        clear_finalization_jobs(fake_firestore, test_uid)
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=True)

        with client.websocket_connect(NATIVE_LISTEN_URL, headers=NATIVE_AUTH_HEADERS) as websocket:
            failed = receive_until(
                websocket,
                lambda payload: isinstance(payload, dict)
                and payload.get('type') == 'service_status'
                and payload.get('status') == 'stt_failed',
            )
            assert failed['provider'] == 'parakeet'
            assert failed['reason'] == 'initialization_failed'
            assert failed['outcome'] in {'upstream_error', 'config_error'}
            close_message = websocket.receive()
            assert close_message['type'] == 'websocket.close'
            assert close_message['code'] == 1011

        assert pusher.connection_count == 0
        assert pusher.frames == []
    finally:
        clear_finalization_jobs(fake_firestore, test_uid)
        pusher.close()
        parakeet.close()


def test_listen_pusher_wire_contract_provider_send_failure_is_terminal_after_pusher_connects(
    client, test_uid, monkeypatch, fake_firestore
):
    """A real provider death latch stops the live route before transcript or finalization work."""

    async def unexpected_finalization(_peer, _frame, _websocket):
        raise AssertionError('provider send failure must not reach pusher finalization')

    # The first production Parakeet send is accepted by its local queue; the
    # scripted remote closes immediately, and the next real audio delivery must
    # observe the death latch through send_live_stt_audio.
    parakeet = ScriptedParakeetPeer(close_after_audio=1).start()
    pusher = ScriptedPusherPeer(unexpected_finalization).start()
    try:
        _configure_live_wire_contract(monkeypatch, pusher, parakeet.api_url)
        install_fake_firestore_transactions(monkeypatch, fake_firestore)
        clear_finalization_jobs(fake_firestore, test_uid)
        seed_listen_user(test_uid, uses_custom_stt=False, single_language_mode=True)

        with client.websocket_connect(NATIVE_LISTEN_URL, headers=NATIVE_AUTH_HEADERS) as websocket:
            _open_native_listen(websocket)
            pusher.wait_for_connections(1)
            websocket.send_bytes(PCM8_AUDIO_FRAME)
            parakeet.wait_for_audio(1)
            parakeet.wait_for_forced_close()
            websocket.send_bytes(PCM8_AUDIO_FRAME)
            websocket.send_bytes(PCM8_AUDIO_FRAME)

            failed = receive_until(
                websocket,
                lambda payload: isinstance(payload, dict)
                and payload.get('type') == 'service_status'
                and payload.get('status') == 'stt_failed',
            )
            assert failed['provider'] == 'parakeet'
            assert failed['reason'] in {'connection_lost', 'send_failed'}
            close_message = websocket.receive()
            assert close_message['type'] == 'websocket.close'
            assert close_message['code'] == 1011

        assert pusher.connection_count == 1
        assert pusher.frames == []
        assert finalization_jobs_for_uid(fake_firestore, test_uid) == []
    finally:
        clear_finalization_jobs(fake_firestore, test_uid)
        pusher.close()
        parakeet.close()
