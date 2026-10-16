"""Dispatch-level regression matrix: no billed provider work after denial."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import stt_cap_dispatch as flag
from utils import stt_cap_dispatch as cap
from routers.listen.receiver import _RecordingSTTSocket
from utils.stt.live_session import LiveLegSocket
from utils.stt.vad_gate import GatedSTTSocket


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    monkeypatch.delenv('STT_CAP_DISPATCH_ENFORCEMENT', raising=False)
    monkeypatch.setattr(cap, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(cap, 'record_audio', Mock())


@pytest.mark.parametrize('value', [None, '', 'false', '1', 'yes'])
def test_dark_default(value, monkeypatch):
    if value is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', value)
    resolver = Mock(side_effect=AssertionError('flag off performed admission IO'))
    monkeypatch.setattr(cap, 'funded_allowance', resolver)
    assert not flag.enabled()
    assert cap.sync_allowed('synthetic')
    resolver.assert_not_called()


@pytest.mark.parametrize('provider', ['deepgram', 'soniox', 'modulate', 'parakeet'])
@pytest.mark.parametrize('enforce', [False, True])
async def test_provider_creation_and_sends_flag_matrix(provider, enforce, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(enforce))
    admission = cap.LiveAdmission('synthetic')
    admission.reason = 'plan_allowance_exhausted'
    raw = Mock(send=Mock(return_value=True), is_connection_dead=False)
    factory = AsyncMock(return_value=raw)
    connect = cap.live_provider(provider, 0)(factory)
    token = cap.current_live_admission.set(admission)
    try:
        socket = await connect(16000)
    finally:
        cap.current_live_admission.reset(token)
    socket.send(b'\0' * 32000)
    assert factory.await_count == (0 if enforce else 1)
    assert raw.send.call_count == (0 if enforce else 1)
    assert not socket.is_connection_dead
    if enforce:
        cap.record_audio.assert_called_with('live', 'suppressed', provider, 1, True)


async def test_one_balance_covers_multichannel_replay_and_replacement(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    state = cap.LiveAdmission('synthetic')
    state.managed, state.remaining = True, 2
    state.reason = 'plan_within_allowance'
    providers = [Mock(send=Mock(return_value=True)) for _ in range(4)]
    sockets = [cap.CapSocket(state, 'soniox', 16000, AsyncMock(), raw) for raw in providers]
    # Two channel sends consume the shared balance. Replay and successor sends
    # cannot restart it. Policy refusal never publishes transport death.
    for socket in sockets:
        assert socket.send(b'\0' * 32000)
    assert [raw.send.call_count for raw in providers] == [1, 1, 0, 0]
    assert state.remaining == 0
    assert state.reason == 'plan_allowance_exhausted'


async def test_byok_exempts_only_customer_deepgram_then_reauthorizes_fallback(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(cap, 'get_byok_key', lambda _: 'synthetic-key')
    state = cap.LiveAdmission('synthetic')
    dg, fallback = Mock(), Mock()
    state.send(dg, b'00', 'deepgram', 16000)
    state.send(fallback, b'00', 'modulate', 16000)
    dg.send.assert_called_once()
    fallback.send.assert_not_called()
    monkeypatch.setenv('DEEPGRAM_SELF_HOSTED_ENABLED', 'true')
    state.send(dg, b'00', 'deepgram', 16000)
    assert dg.send.call_count == 1


async def test_held_constructor_resumes_after_reset_without_reopening_capture(monkeypatch):
    state = cap.LiveAdmission('synthetic')
    raw = Mock()
    factory = AsyncMock(return_value=raw)
    socket = cap.CapSocket(state, 'modulate', 16000, factory)
    state.send(raw, b'00', 'modulate', 16000)
    factory.assert_not_called()
    state.managed, state.remaining = True, 10
    await socket.resume()
    assert socket.raw is raw
    assert socket.send(b'00') is raw.send.return_value
    socket.finish()
    raw.finish.assert_called_once()


async def test_resumed_registry_leg_unwraps_nested_provider_and_debits_once(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    state = cap.LiveAdmission('synthetic')
    raw = Mock(send=Mock(return_value=True))
    inner = cap.live_provider('modulate', 0)(AsyncMock(return_value=raw))
    socket = cap.CapSocket(state, 'modulate', 16000, lambda: inner(16000))
    state.managed, state.remaining = True, 2
    token = cap.current_live_admission.set(state)
    try:
        await socket.resume()
        assert socket.send(b'\0' * 32000)
    finally:
        cap.current_live_admission.reset(token)
    assert socket.raw is raw
    raw.send.assert_called_once()
    assert state.remaining == 1
    assert cap.record_audio.call_count == 1


@pytest.mark.parametrize('managed', [False, True])
def test_queued_sync_always_resolves_omi_funding(managed, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    resolver = Mock(return_value=SimpleNamespace(managed=managed, reason='plan_allowance_exhausted'))
    monkeypatch.setattr('utils.subscription.resolve_transcription_allowance', resolver)
    assert cap.sync_allowed('synthetic', 60, 'parakeet') is managed
    resolver.assert_called_once_with('synthetic', source=None, byok_active=False, omi_funded=True)


@pytest.mark.parametrize('kind', ['recording', 'gated', 'managed', 'replay', 'idle-replay'])
def test_suppression_never_fabricates_provider_timeline_spans(kind):
    state = cap.LiveAdmission('synthetic')
    state.reason = 'plan_allowance_exhausted'
    raw = Mock()
    guarded = cap.CapSocket(state, 'parakeet', 16000, AsyncMock(), raw)
    tracker = Mock()
    if kind == 'recording':
        socket = _RecordingSTTSocket(guarded, tracker)
        assert socket.send(b'00', start_sample=900)
    elif kind == 'gated':
        socket = object.__new__(GatedSTTSocket)
        socket._conn, socket._send_tracker = guarded, tracker
        assert socket.send(b'00', start_sample=900)
    else:
        socket = object.__new__(LiveLegSocket)
        socket.raw, socket._send_tracker = guarded, tracker
        socket.session = SimpleNamespace(receiver=SimpleNamespace(_window_ring=lambda: None))
        if kind == 'replay':
            assert socket.replay_send(b'00', 900)
        elif kind == 'idle-replay':
            assert socket.send_admitted_audio(b'00', ((900, 1),))
        else:
            assert socket.send(b'00', start_sample=900)
    raw.send.assert_not_called()
    tracker.note_accepted.assert_not_called()
    tracker.note_accepted_spans.assert_not_called()


@pytest.mark.parametrize('provider', ['deepgram', 'soniox', 'modulate', 'parakeet'])
async def test_real_provider_constructor_wiring_refuses_before_sdk_or_wire(provider, monkeypatch):
    from utils.stt import streaming
    import websockets

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    sdk = Mock(side_effect=AssertionError('denied constructor reached SDK'))
    wire = AsyncMock(side_effect=AssertionError('denied constructor reached network'))
    monkeypatch.setattr(streaming, 'DeepgramClient', sdk)
    monkeypatch.setattr(websockets, 'connect', wire)
    state = cap.LiveAdmission('synthetic')
    token = cap.current_live_admission.set(state)
    try:
        if provider == 'deepgram':
            socket = await streaming.process_audio_dg(Mock(), 'en', 16000, 1)
        elif provider == 'soniox':
            socket = await streaming.process_audio_soniox(Mock(), 16000, 'en')
        elif provider == 'modulate':
            socket = await streaming.process_audio_modulate(Mock(), 16000, 'en')
        else:
            socket = await streaming.process_audio_parakeet(Mock(), 'en', 16000, 1)
    finally:
        cap.current_live_admission.reset(token)
    assert isinstance(socket, cap.CapSocket)
    assert socket.raw is None
    sdk.assert_not_called()
    wire.assert_not_called()


async def test_initial_exhaustion_receives_without_entering_provider_router(monkeypatch):
    from routers.listen.receiver import ListenReceiver

    state = cap.LiveAdmission('synthetic')
    state.refresh = AsyncMock()
    receiver = object.__new__(ListenReceiver)
    receiver.cap_admission = state
    receiver.host = SimpleNamespace(stt_service='modulate')
    assert await receiver.initialize_stt()
    assert receiver.cap_paused and state.funded_paused
    assert not hasattr(receiver, 'live_demand')  # No selection, model or provider initialization.


async def test_terminal_provider_error_cannot_close_capture_during_cap_pause():
    from utils.stt.live_failure import terminate_live_stt_session, terminate_live_stt_backoff

    state = cap.LiveAdmission('synthetic')
    state.omi_selected = True
    session = SimpleNamespace(stt_cap_admission=state, stt_terminal_failure=False, active=True)
    websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    assert not await terminate_live_stt_session(
        websocket, session, failure=Mock(), reason='connection_lost', platform='ios'
    )
    assert not await terminate_live_stt_backoff(websocket, session, reason='provider_unavailable', retry_after=30)
    assert session.active and not session.stt_terminal_failure
    websocket.send_json.assert_not_called()
    websocket.close.assert_not_called()


async def test_paused_soniox_binds_wire_ledger_before_resumed_audio():
    state = cap.LiveAdmission('synthetic')
    raw = Mock()
    socket = cap.CapSocket(state, 'soniox', 16000, AsyncMock(return_value=raw))
    ledger = object()
    socket.set_wire_ledger(ledger)
    socket.set_capture_axis_ledger(ledger)
    raw.set_wire_ledger.assert_not_called()
    state.managed, state.remaining = True, 10
    await socket.resume()
    raw.set_wire_ledger.assert_called_once_with(ledger)
    raw.set_capture_axis_ledger.assert_called_once_with(ledger)
