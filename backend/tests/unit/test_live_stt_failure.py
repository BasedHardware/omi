from dataclasses import dataclass
from typing import Any
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.message_event import MessageServiceStatusEvent
from utils.stt import live_failure
from utils.stt.live_failure import (
    LIVE_STT_FAILURE_CLOSE_CODE,
    LIVE_STT_FAILURE_CLOSE_REASON,
    flush_live_stt_buffer,
    live_stt_initialization_failure,
    send_live_stt_audio,
    terminate_live_stt_session,
)
from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome
from utils.stt.safe_socket import KeepaliveConfig, SafeDeepgramSocket
from utils.stt.vad_gate import GatedSTTSocket, VADStreamingGate


@dataclass
class FakeSession:
    active: bool = True
    close_code: int = 1001
    stt_terminal_failure: bool = False


class FakeClientSocket:
    def __init__(self, *, reject_status: bool = False) -> None:
        self.reject_status = reject_status
        self.actions: list[tuple[Any, ...]] = []

    async def send_json(self, data: Any) -> None:
        self.actions.append(('status', data))
        if self.reject_status:
            raise RuntimeError('synthetic client send failure')

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.actions.append(('close', code, reason))


class FakeProviderSocket:
    def __init__(
        self,
        *,
        dead: bool = False,
        fail_send: bool = False,
        die_during_send: bool = False,
        reject_send: bool = False,
    ) -> None:
        self.is_connection_dead = dead
        self.fail_send = fail_send
        self.die_during_send = die_during_send
        self.reject_send = reject_send
        self.sent: list[bytes] = []

    def send(self, audio: bytes) -> bool:
        if self.fail_send:
            raise RuntimeError('synthetic provider send failure')
        if self.reject_send:
            return False
        self.sent.append(audio)
        if self.die_during_send:
            self.is_connection_dead = True
            return False
        return True


class BrokenDeathLatchSocket:
    @property
    def is_connection_dead(self) -> bool:
        raise RuntimeError('synthetic unreadable death latch')

    def send(self, _audio: bytes) -> None:
        raise AssertionError('an unreadable death latch must fail before send')


def test_nonterminal_service_status_preserves_the_legacy_payload_shape() -> None:
    assert MessageServiceStatusEvent(status='ready').to_json() == {
        'status': 'ready',
        'type': 'service_status',
    }


@pytest.mark.asyncio
async def test_terminal_live_failure_sends_bounded_status_before_safe_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    websocket = FakeClientSocket()
    session = FakeSession()
    failure = TranscriptionFailure(TranscriptionOutcome.TIMEOUT, provider='deepgram')
    recorded: list[dict[str, Any]] = []
    monkeypatch.setattr(live_failure, 'record_live_stt_failure', lambda **labels: recorded.append(labels))

    sent = await terminate_live_stt_session(
        websocket,
        session,
        failure=failure,
        reason='initialization_failed',
        platform='ios',
    )

    assert sent is True
    assert websocket.actions == [
        (
            'status',
            {
                'status': 'stt_failed',
                'status_text': 'The transcription provider timed out.',
                'outcome': 'timeout',
                'provider': 'deepgram',
                'retryable': True,
                'reason': 'initialization_failed',
                'type': 'service_status',
            },
        ),
        ('close', LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON),
    ]
    assert session.active is False
    assert session.close_code == LIVE_STT_FAILURE_CLOSE_CODE
    assert session.stt_terminal_failure is True
    assert recorded == [
        {
            'provider': 'deepgram',
            'platform': 'ios',
            'outcome': TranscriptionOutcome.TIMEOUT,
            'phase': 'initialization',
        }
    ]

    # Teardown or another channel observing the same outage cannot emit twice.
    assert (
        await terminate_live_stt_session(
            websocket,
            session,
            failure=failure,
            reason='send_failed',
            platform='ios',
        )
        is False
    )
    assert len(websocket.actions) == 2
    assert len(recorded) == 1


@pytest.mark.asyncio
async def test_terminal_live_failure_still_closes_when_status_delivery_fails() -> None:
    websocket = FakeClientSocket(reject_status=True)
    session = FakeSession()

    sent = await terminate_live_stt_session(
        websocket,
        session,
        failure=TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='parakeet'),
        reason='send_failed',
        platform='android',
    )

    assert sent is False
    assert session.active is False
    assert websocket.actions[-1] == ('close', LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)


def test_live_initialization_maps_provider_value_errors_to_config_failure() -> None:
    failure = live_stt_initialization_failure(ValueError('synthetic missing config'), 'modulate')

    assert failure.outcome == TranscriptionOutcome.CONFIG_ERROR
    assert failure.provider == 'modulate'
    assert failure.retryable is False


@pytest.mark.asyncio
async def test_single_channel_dead_socket_preserves_unsent_buffer_and_terminates() -> None:
    websocket = FakeClientSocket()
    session = FakeSession()
    provider_socket = FakeProviderSocket(dead=True)
    audio = bytearray(b'synthetic-pcm')

    sent = await flush_live_stt_buffer(
        websocket,
        session,
        stt_socket=provider_socket,
        buffer=audio,
        provider='deepgram',
        platform='ios',
    )

    assert sent is False
    assert audio == b'synthetic-pcm'
    assert provider_socket.sent == []
    assert websocket.actions[0][1]['reason'] == 'connection_lost'
    assert websocket.actions[0][1]['outcome'] == 'upstream_error'
    assert websocket.actions[-1] == ('close', LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)


@pytest.mark.asyncio
async def test_unreadable_provider_death_latch_is_terminal() -> None:
    websocket = FakeClientSocket()
    session = FakeSession()

    sent = await send_live_stt_audio(
        websocket,
        session,
        stt_socket=BrokenDeathLatchSocket(),
        audio=b'synthetic-pcm',
        provider='deepgram',
        platform='web',
    )

    assert sent is False
    assert session.active is False
    assert websocket.actions[0][1]['reason'] == 'connection_lost'


@pytest.mark.asyncio
async def test_deepgram_callback_death_latch_terminates_before_late_audio_send() -> None:
    websocket = FakeClientSocket()
    session = FakeSession()
    raw_connection = MagicMock()
    safe_socket = SafeDeepgramSocket(
        raw_connection,
        cfg=KeepaliveConfig(keepalive_interval_sec=5.0, check_period_sec=999.0),
    )
    try:
        safe_socket.set_close_reason('DG close event: synthetic peer close')

        sent = await send_live_stt_audio(
            websocket,
            session,
            stt_socket=safe_socket,
            audio=b'late-audio',
            provider='deepgram',
            platform='ios',
        )

        assert sent is False
        assert session.active is False
        assert raw_connection.send.call_count == 0
        assert websocket.actions[0][1]['reason'] == 'connection_lost'
    finally:
        safe_socket.finish()


@pytest.mark.asyncio
async def test_single_channel_send_latch_failure_preserves_unsent_buffer() -> None:
    websocket = FakeClientSocket()
    session = FakeSession()
    provider_socket = FakeProviderSocket(die_during_send=True)
    audio = bytearray(b'synthetic-pcm')

    sent = await flush_live_stt_buffer(
        websocket,
        session,
        stt_socket=provider_socket,
        buffer=audio,
        provider='parakeet',
        platform='macos',
    )

    assert sent is False
    assert audio == b'synthetic-pcm'
    assert websocket.actions[0][1]['reason'] == 'send_failed'


@pytest.mark.asyncio
async def test_false_send_acknowledgement_preserves_buffer_and_terminates() -> None:
    """A queue wrapper must explicitly accept audio before local data is cleared."""
    websocket = FakeClientSocket()
    session = FakeSession()
    provider_socket = FakeProviderSocket(reject_send=True)
    audio = bytearray(b'synthetic-pcm')

    sent = await flush_live_stt_buffer(
        websocket,
        session,
        stt_socket=provider_socket,
        buffer=audio,
        provider='modulate',
        platform='ios',
    )

    assert sent is False
    assert audio == b'synthetic-pcm'
    assert provider_socket.sent == []
    assert websocket.actions[0][1]['reason'] == 'send_failed'


@pytest.mark.asyncio
async def test_successful_single_channel_send_clears_buffer() -> None:
    websocket = FakeClientSocket()
    session = FakeSession()
    provider_socket = FakeProviderSocket()
    audio = bytearray(b'synthetic-pcm')

    sent = await flush_live_stt_buffer(
        websocket,
        session,
        stt_socket=provider_socket,
        buffer=audio,
        provider='deepgram',
        platform='ios',
    )

    assert sent is True
    assert audio == b''
    assert provider_socket.sent == [b'synthetic-pcm']
    assert websocket.actions == []
    assert session.active is True


@pytest.mark.asyncio
async def test_multi_channel_send_exception_is_terminal_and_machine_readable() -> None:
    websocket = FakeClientSocket()
    session = FakeSession()
    provider_socket = FakeProviderSocket(fail_send=True)

    sent = await send_live_stt_audio(
        websocket,
        session,
        stt_socket=provider_socket,
        audio=b'synthetic-channel-pcm',
        provider='deepgram',
        platform='ios',
    )

    assert sent is False
    assert session.active is False
    assert websocket.actions[0][1] == {
        'status': 'stt_failed',
        'status_text': 'The transcription provider could not complete the request.',
        'outcome': 'upstream_error',
        'provider': 'deepgram',
        'retryable': True,
        'reason': 'send_failed',
        'type': 'service_status',
    }
    assert websocket.actions[-1] == ('close', LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)


@pytest.mark.asyncio
async def test_vad_boundary_finalize_failure_is_customer_visible() -> None:
    """Do not keep a live session open after its pending utterance was lost."""
    websocket = FakeClientSocket()
    session = FakeSession()
    provider_socket = MagicMock()
    provider_socket.is_connection_dead = False
    provider_socket.finalize.side_effect = RuntimeError('synthetic flush failure')
    gate = MagicMock(spec=VADStreamingGate)
    gate.uid = 'test-uid'
    gate.session_id = 'test-session'
    gate._finalize_errors = 0
    gate.process_audio.return_value = SimpleNamespace(audio_to_send=b'', should_finalize=True)
    gated_socket = GatedSTTSocket(provider_socket, gate=gate)

    sent = await send_live_stt_audio(
        websocket,
        session,
        stt_socket=gated_socket,
        audio=b'synthetic-silence-boundary',
        provider='deepgram',
        platform='macos',
    )

    assert sent is False
    assert gate._finalize_errors == 1
    assert websocket.actions[0][1]['reason'] == 'send_failed'
    assert websocket.actions[0][1]['outcome'] == 'upstream_error'
    assert websocket.actions[-1] == ('close', LIVE_STT_FAILURE_CLOSE_CODE, LIVE_STT_FAILURE_CLOSE_REASON)
