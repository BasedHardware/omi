"""omi_listen_ws_close_total: each listen close path counts once, under closed labels only."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from routers.listen.contracts import ListenRequest, ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from utils.observability.listen_close import (
    CODE_CLASSES,
    HELD,
    INITIATORS,
    LISTEN_WS_CLOSE_FINALIZE_SECONDS,
    LISTEN_WS_CLOSE_TOTAL,
    close_code_class,
    note_ws_close,
    record_listen_ws_close,
)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _closes(**labels):
    for family in LISTEN_WS_CLOSE_TOTAL.collect():
        for sample in family.samples:
            if sample.name.endswith('_total') and sample.labels == labels:
                return sample.value
    return 0.0


def _finalize_count(**labels):
    for family in LISTEN_WS_CLOSE_FINALIZE_SECONDS.collect():
        for sample in family.samples:
            if sample.name.endswith('_count') and sample.labels == labels:
                return sample.value
    return 0.0


def _snapshot():
    return {
        (code_class, initiator, held): _closes(code_class=code_class, initiator=initiator, held=held)
        for code_class in CODE_CLASSES
        for initiator in INITIATORS
        for held in HELD
    }


def _delta(before):
    after = _snapshot()
    return {key: after[key] - before[key] for key in after if after[key] != before[key]}


class _Persistence:
    async def call(self, fn, *args, **kwargs):
        if fn.__name__ == '_account_deletion_blocks_owner_persistence':
            return False
        return None


def _runtime(client_state=WebSocketState.CONNECTED, close=None):
    """A real ListenSessionRuntime teardown with collaborators stubbed at their seams."""
    websocket = SimpleNamespace(client_state=client_state, close=close or AsyncMock())
    request = ListenRequest(websocket=websocket, uid='synthetic')
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = request
    runtime.state = ListenSessionState()
    runtime.task_supervisor = SimpleNamespace(end_session=MagicMock(), drain_all=AsyncMock())
    runtime._finish_live_transcription = MagicMock()
    runtime._record_session_transcript_outcome = MagicMock()
    runtime.transcripts = SimpleNamespace(
        flush_translations=AsyncMock(), flush_speaker_assignments=AsyncMock(), clear=MagicMock()
    )
    runtime.receiver = SimpleNamespace(
        finish=MagicMock(), flush_multi_channel_tail=AsyncMock(), clear=MagicMock(), cap_paused=False, live_hold=None
    )
    runtime._flush_usage = AsyncMock()
    runtime.persistence = _Persistence()
    runtime.conversations = SimpleNamespace(process_conversation=AsyncMock())
    runtime.is_multi_channel = False
    runtime.language_observations = None
    runtime.pusher_close = None
    runtime.onboarding_handler = None
    runtime.parity_capture = SimpleNamespace(persist=MagicMock())
    runtime.speakers = SimpleNamespace(clear=MagicMock())
    return runtime


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        frame = next(self.frames)
        if isinstance(frame, BaseException):
            raise frame
        return frame


def _receiver(frames, state):
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=_FramesWebSocket(frames), uid='test-uid', codec='opus'),
        state=state,
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=lambda segments: None),
        start_live_transcription=lambda: None,
    )
    return ListenReceiver(host, [], {})


@pytest.mark.parametrize(
    ('code', 'expected'),
    [
        (1000, '1000'),
        (1001, '1001'),
        (1006, '1006'),
        (1011, '1011'),
        (1008, 'other'),
        (4001, 'other'),
        (None, 'other'),
        (True, 'other'),
        ('1000', 'other'),
        (10**9, 'other'),
    ],
)
def test_close_code_class_is_closed(code, expected):
    assert close_code_class(code) == expected


def test_first_observed_close_wins_and_unknown_initiator_folds():
    state = ListenSessionState()
    note_ws_close(state, 'client', 1006)
    note_ws_close(state, 'server', 1000)
    assert (state.ws_close_initiator, state.ws_close_code) == ('client', 1006)

    other = SimpleNamespace()
    note_ws_close(other, 'a-uid-shaped-value', 1000)
    assert other.ws_close_initiator == 'unknown'


@pytest.mark.anyio
async def test_client_close_frame_counts_client_with_its_code():
    state = ListenSessionState()
    receiver = _receiver([{'type': 'websocket.disconnect', 'code': 1000}], state)
    await receiver.receive_data()
    runtime = _runtime(client_state=WebSocketState.DISCONNECTED)
    runtime.state = state
    before = _snapshot()
    await runtime._teardown()
    assert _delta(before) == {('1000', 'client', 'false'): 1}
    runtime.request.websocket.close.assert_not_awaited()


@pytest.mark.anyio
async def test_abnormal_client_drop_counts_1006():
    state = ListenSessionState()
    receiver = _receiver([{'type': 'websocket.disconnect', 'code': 1006}], state)
    await receiver.receive_data()
    runtime = _runtime(client_state=WebSocketState.DISCONNECTED)
    runtime.state = state
    before = _snapshot()
    await runtime._teardown()
    assert _delta(before) == {('1006', 'client', 'false'): 1}


@pytest.mark.anyio
async def test_websocket_disconnect_exception_counts_its_code():
    state = ListenSessionState()
    receiver = _receiver([WebSocketDisconnect(code=1001)], state)
    await receiver.receive_data()
    runtime = _runtime(client_state=WebSocketState.DISCONNECTED)
    runtime.state = state
    before = _snapshot()
    await runtime._teardown()
    assert _delta(before) == {('1001', 'client', 'false'): 1}


@pytest.mark.anyio
async def test_receive_failure_then_server_close_counts_server_1011():
    state = ListenSessionState()
    receiver = _receiver([RuntimeError('synthetic receive failure')], state)
    await receiver.receive_data()
    assert state.close_code == 1011
    runtime = _runtime()
    runtime.state = state
    before = _snapshot()
    await runtime._teardown()
    runtime.request.websocket.close.assert_awaited_once_with(code=1011)
    assert _delta(before) == {('1011', 'server', 'false'): 1}


@pytest.mark.anyio
async def test_server_inactivity_close_counts_server_1001_and_held():
    runtime = _runtime()
    runtime.state.close_code = 1001
    runtime.receiver.cap_paused = True
    before = _snapshot()
    finalized = _finalize_count(initiator='server', held='true')
    await runtime._teardown()
    assert _delta(before) == {('1001', 'server', 'true'): 1}
    assert _finalize_count(initiator='server', held='true') == finalized + 1


@pytest.mark.anyio
async def test_live_hold_pause_marks_held():
    runtime = _runtime(client_state=WebSocketState.DISCONNECTED)
    runtime.receiver.live_hold = SimpleNamespace(paused=True)
    note_ws_close(runtime.state, 'client', 1000)
    before = _snapshot()
    await runtime._teardown()
    assert _delta(before) == {('1000', 'client', 'true'): 1}


@pytest.mark.anyio
async def test_terminal_stt_failure_counts_server_close_sent_by_live_failure():
    # live_failure.terminate_live_stt_session closes the socket itself; teardown skips its close.
    runtime = _runtime(client_state=WebSocketState.DISCONNECTED)
    runtime.state.stt_terminal_failure = True
    runtime.state.close_code = 1011
    before = _snapshot()
    await runtime._teardown()
    assert _delta(before) == {('1011', 'server', 'false'): 1}


@pytest.mark.anyio
async def test_failed_server_close_is_unknown():
    runtime = _runtime(close=AsyncMock(side_effect=RuntimeError('already closed')))
    runtime.state.close_code = 1000
    before = _snapshot()
    await runtime._teardown()
    assert _delta(before) == {('1000', 'unknown', 'false'): 1}


@pytest.mark.anyio
async def test_teardown_exception_still_counts_once():
    runtime = _runtime()
    runtime.state.close_code = 1011
    runtime._teardown_components = AsyncMock(side_effect=RuntimeError('synthetic teardown failure'))
    before = _snapshot()
    with pytest.raises(RuntimeError):
        await runtime._teardown()
    assert _delta(before) == {('1011', 'unknown', 'false'): 1}


@pytest.mark.anyio
async def test_heartbeat_disconnect_counts_client():
    async def send_text(_payload):
        raise WebSocketDisconnect(code=1006)

    runtime = _runtime()
    runtime.request.websocket.send_text = send_text
    assert await runtime._send_ping() is False
    assert (runtime.state.ws_close_initiator, runtime.state.ws_close_code) == ('client', 1006)


def test_record_never_raises_on_hostile_state():
    record_listen_ws_close(SimpleNamespace(ws_close_observed_at='x'), held=False, teardown_started_at=0.0)
    record_listen_ws_close(object(), held=True, teardown_started_at=0.0)


def test_metrics_carry_only_bounded_labels():
    assert LISTEN_WS_CLOSE_TOTAL._labelnames == ('code_class', 'initiator', 'held')
    assert LISTEN_WS_CLOSE_FINALIZE_SECONDS._labelnames == ('initiator', 'held')
    for family in (*LISTEN_WS_CLOSE_TOTAL.collect(), *LISTEN_WS_CLOSE_FINALIZE_SECONDS.collect()):
        for sample in family.samples:
            assert sample.labels.get('code_class', '1000') in CODE_CLASSES
            assert sample.labels['initiator'] in INITIATORS
            assert sample.labels['held'] in HELD
