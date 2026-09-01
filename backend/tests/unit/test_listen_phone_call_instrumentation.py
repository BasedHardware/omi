"""Phone-call listen instrumentation: prefix drops, first audio, silent teardown.

A real phone call (source=phone_call, codec=pcm @ 48 kHz, channels=2) that sends
no audio is invisible today: teardown deletes the empty conversation and nothing
distinguishes it from a call that was never transcribed. These tests pin the
bounded telemetry that closes that gap — no payloads, no user identifiers.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import routers.listen.conversations as conversations_module
import routers.listen.receiver as receiver_module
from routers.listen.conversations import LiveConversationController
from routers.listen.receiver import ListenReceiver
from utils.listen_audio import build_channel_config
from utils.metrics import (
    OMI_LISTEN_ACCEPTED_TOTAL,
    OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
    OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL,
)
from utils.observability.transcription import (
    record_listen_audio_outcome,
    record_listen_session_accepted,
    record_listen_unknown_channel_prefix,
)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _counter_value(counter, **labels) -> int:
    return counter.labels(**labels)._value.get()


def _phone_call_host(**overrides):
    host = SimpleNamespace(
        stt_service='modulate',
        is_multi_channel=True,
        start_live_transcription=lambda: None,
        use_custom_stt=False,
        audio_bytes_send=None,
        request=SimpleNamespace(
            source='phone_call', codec='pcm', sample_rate=48000, uid='', websocket=SimpleNamespace()
        ),
        state=SimpleNamespace(
            fair_use_dg_budget_exhausted=False,
            fair_use_track_dg_usage=False,
            dg_usage_ms_pending=0,
            first_audio_byte_timestamp=None,
        ),
        client_device_context=SimpleNamespace(platform='ios'),
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


def _phone_call_receiver(host):
    channels = build_channel_config('phone_call')
    receiver = ListenReceiver(host, channels, {channel.channel_id: index for index, channel in enumerate(channels)})
    receiver.stt_sockets_multi = [object(), object()]
    return receiver


@pytest.mark.anyio
async def test_pcm48_multi_channel_frames_resample_and_reach_stt(monkeypatch):
    """Prefixed 0x01/0x02 pcm frames at 48 kHz must be resampled and sent to STT.

    Production mobile phone calls send codec=pcm @ 48000; only pcm16 @ 16 kHz with
    custom_stt=enabled had test coverage before.
    """

    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(receiver_module, 'send_live_stt_audio', sent)
    receiver = _phone_call_receiver(_phone_call_host())

    # 960 bytes of pcm at 48 kHz mono 16-bit = 480 samples -> 160 samples at 16 kHz.
    frame = b'\x01' + b'\x00\x01' * 480
    decoded = await receiver._handle_multi_channel_audio(frame, now=1000.0)

    args, kwargs = sent.await_args
    assert len(args) == 2  # websocket, session state
    assert kwargs['stt_socket'] is receiver.stt_sockets_multi[0]
    assert len(kwargs['audio']) == 320  # 160 samples * 2 bytes at TARGET_SAMPLE_RATE


@pytest.mark.anyio
async def test_unknown_channel_prefix_counts_and_does_not_crash(monkeypatch):
    monkeypatch.setattr(receiver_module, 'send_live_stt_audio', AsyncMock(return_value=True))
    receiver = _phone_call_receiver(_phone_call_host())
    before = _counter_value(
        OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL, transcription_source='phone_call', client_platform='ios'
    )

    decoded = await receiver._handle_multi_channel_audio(b'\x07' + b'\x00\x01' * 16, now=1000.0)

    assert decoded == 0
    assert (
        _counter_value(
            OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL, transcription_source='phone_call', client_platform='ios'
        )
        == before + 1
    )
    # The stream must stay usable after the dropped frame.
    assert await receiver._handle_multi_channel_audio(b'\x02' + b'\x00\x01' * 16, now=1000.0) == 32


@pytest.mark.anyio
async def test_first_audio_byte_records_first_audio_outcome():
    host = _phone_call_host()
    host.is_multi_channel = False
    receiver = ListenReceiver(host, [], {})
    receiver.opus_decoder = None
    websocket = SimpleNamespace(receive=AsyncMock(side_effect=[{'bytes': b'\x01\x00\x00'}, _disconnect()]))
    host.request.websocket = websocket
    host.limits = SimpleNamespace(ws_receive_timeout=1.0)
    host.state.active = True
    host.state.close_code = None
    host.state.last_audio_received_time = None
    host.state.last_activity_time = None
    host.state.first_audio_byte_timestamp = None
    host.state.last_usage_record_timestamp = None
    host.state.audio_ring_buffer = None
    host.state.stt_terminal_failure = False
    host.state.live_transcription_attempt = None
    host.start_live_transcription = lambda: None
    host.use_custom_stt = True  # keep the STT socket path out of the assertion
    host.audio_bytes_send = None
    before = _counter_value(
        OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
        transcription_source='phone_call',
        outcome='first_audio',
        client_platform='ios',
    )

    await receiver.receive_data()

    assert (
        _counter_value(
            OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
            transcription_source='phone_call',
            outcome='first_audio',
            client_platform='ios',
        )
        == before + 1
    )


@pytest.mark.anyio
async def test_unknown_prefix_only_session_never_counts_first_audio():
    """Frames with unrecognized prefixes must leave the session at zero audio.

    Only then can teardown still classify it as a silent no-audio phone call —
    marking first audio on raw receipt would hide exactly that failure.
    """

    host = _phone_call_host()
    receiver = _phone_call_receiver(host)
    websocket = SimpleNamespace(
        receive=AsyncMock(
            side_effect=[
                {'bytes': b'\x07' + b'\x00\x01' * 16},
                {'bytes': b'\x09' + b'\x00\x01' * 16},
                _disconnect(),
            ]
        )
    )
    host.request.websocket = websocket
    host.limits = SimpleNamespace(ws_receive_timeout=1.0)
    host.state.active = True
    host.state.close_code = None
    host.state.last_audio_received_time = None
    host.state.last_activity_time = None
    host.state.first_audio_byte_timestamp = None
    host.state.last_usage_record_timestamp = None
    host.state.audio_ring_buffer = None
    live_started = []
    host.start_live_transcription = lambda: live_started.append(True)
    host.use_custom_stt = True
    host.audio_bytes_send = None
    before = _counter_value(
        OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
        transcription_source='phone_call',
        outcome='first_audio',
        client_platform='ios',
    )

    await receiver.receive_data()

    assert host.state.first_audio_byte_timestamp is None
    assert live_started == []
    assert (
        _counter_value(
            OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
            transcription_source='phone_call',
            outcome='first_audio',
            client_platform='ios',
        )
        == before
    )


def _disconnect():
    return {'type': 'websocket.disconnect', 'code': 1000}


def _teardown_controller(monkeypatch, *, first_audio_byte_timestamp, multi_channel=True, empty_delete_wins=True):
    outcomes = []
    monkeypatch.setattr(conversations_module, 'record_listen_audio_outcome', lambda **kwargs: outcomes.append(kwargs))
    deleted = []

    async def persistence_call(fn, *_args, **_kwargs):
        if fn.__name__ == 'get_conversation':
            return {'id': 'conversation-1'}
        if fn.__name__ == 'delete_empty_recording_conversation':
            deleted.append(empty_delete_wins)
            return empty_delete_wins
        raise AssertionError(f'unexpected persistence call: {fn.__name__}')

    host = SimpleNamespace(
        is_multi_channel=multi_channel,
        request=SimpleNamespace(source='phone_call', uid=''),
        state=SimpleNamespace(first_audio_byte_timestamp=first_audio_byte_timestamp),
        client_device_context=SimpleNamespace(platform='ios'),
        recording_session_ids_by_conversation={},
        persistence=SimpleNamespace(call=persistence_call),
    )
    return LiveConversationController(host), outcomes, deleted


@pytest.mark.anyio
async def test_teardown_without_first_audio_records_no_audio_outcome(monkeypatch):
    controller, outcomes, deleted = _teardown_controller(monkeypatch, first_audio_byte_timestamp=None)

    assert await controller.process_conversation('conversation-1') is True

    assert deleted == [True]  # deleting the empty conversation stays allowed
    (outcome,) = outcomes
    assert outcome['source'] == 'phone_call'
    assert outcome['outcome'] == 'no_audio_teardown'
    assert outcome['platform'] == 'ios'


@pytest.mark.anyio
async def test_no_audio_outcome_waits_for_the_fenced_delete_to_win(monkeypatch):
    controller, outcomes, deleted = _teardown_controller(
        monkeypatch, first_audio_byte_timestamp=None, empty_delete_wins=False
    )

    result = await controller.process_conversation('conversation-1')

    assert deleted == [False]
    assert outcomes == [], 'a delete that lost the race to content must not claim no-audio'
    assert result is False


@pytest.mark.anyio
async def test_teardown_after_first_audio_records_nothing(monkeypatch):
    controller, outcomes, _deleted = _teardown_controller(monkeypatch, first_audio_byte_timestamp=123.0)

    await controller.process_conversation('conversation-1')

    assert outcomes == []


@pytest.mark.anyio
async def test_single_channel_teardown_stays_silent(monkeypatch):
    controller, outcomes, _deleted = _teardown_controller(
        monkeypatch, first_audio_byte_timestamp=None, multi_channel=False
    )

    await controller.process_conversation('conversation-1')

    assert outcomes == []


def test_accepted_and_outcome_counters_use_bounded_labels():
    """Garbage sources/platforms must collapse to closed-enum labels, never raise."""

    record_listen_session_accepted(source='definitely-not-a-source', platform=None)
    record_listen_unknown_channel_prefix(source=None, platform='not-a-platform')

    assert _counter_value(OMI_LISTEN_ACCEPTED_TOTAL, transcription_source='unknown', client_platform='unknown') >= 1
    assert (
        _counter_value(
            OMI_LISTEN_UNKNOWN_CHANNEL_PREFIX_TOTAL, transcription_source='unknown', client_platform='unknown'
        )
        >= 1
    )

    with pytest.raises(ValueError):
        record_listen_audio_outcome(source='phone_call', outcome='not-an-outcome', platform='ios')
