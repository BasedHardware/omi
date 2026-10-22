"""Dispatch-level regression matrix: no billed provider work after denial."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest

from config import stt_cap_dispatch as flag
from models.message_event import SttCapLiveHeldEvent
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


@pytest.mark.parametrize('flag', [None, 'true', 'false', '0', 'off'])
def test_cap_proxy_preserves_provider_finalize_arguments(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv('STT_CAP_FINALIZE_FORWARD_ENABLED', raising=False)
    else:
        monkeypatch.setenv('STT_CAP_FINALIZE_FORWARD_ENABLED', flag)
    raw = Mock(finalize=Mock(return_value='finalized'))
    state = cap.LiveAdmission('synthetic')
    socket = cap.CapSocket(state, 'parakeet', 16000, AsyncMock(), raw)
    assert socket.finalize(vad_pause=True) == 'finalized'
    if flag in {'false', '0', 'off'}:
        raw.finalize.assert_called_once_with()
    else:
        raw.finalize.assert_called_once_with(vad_pause=True)


def test_cap_finalize_while_held_never_opens_provider():
    factory = AsyncMock()
    socket = cap.CapSocket(cap.LiveAdmission('synthetic'), 'parakeet', 16000, factory)
    assert socket.finalize(vad_pause=True) is None
    factory.assert_not_called()


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
@pytest.mark.parametrize('ladder_packet', [False, True])
def test_suppression_never_fabricates_provider_timeline_spans(kind, ladder_packet):
    state = cap.LiveAdmission('synthetic')
    state.reason = 'plan_allowance_exhausted'
    if ladder_packet:
        state.managed = True
        state.remaining = 1 / 32000
        state.remaining_units = cap._units_per_second('parakeet') / 32000
        state.reason = 'usage_budget_available'
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


@pytest.mark.parametrize('dispatch', [False, True])
@pytest.mark.parametrize('percent', [99, 100])
def test_funded_dispatch_uses_ladder_budget_instead_of_legacy_seconds(monkeypatch, dispatch, percent):
    from utils import ladder_v1, subscription

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(
        ladder_v1,
        'budget_snapshot',
        lambda *a, **k: {'budget_percent': percent, 'budget_units': 100, 'used_units': percent},
    )
    monkeypatch.setattr(subscription, 'is_marketplace_reviewer', lambda _: False)
    monkeypatch.setattr(subscription, 'is_trial_paywalled', lambda *a, **k: False)
    monkeypatch.setattr(subscription.users_db, 'get_user_valid_subscription', lambda _: SimpleNamespace(plan='plus'))
    legacy = Mock(side_effect=AssertionError('ladder admission consulted the legacy seconds meter'))
    monkeypatch.setattr(subscription, 'get_monthly_usage_for_subscription', legacy)
    assert cap.sync_allowed('synthetic') is (percent < 100)
    assert cap.funded_allowance('synthetic').reason == (
        'usage_budget_available' if percent < 100 else 'usage_budget_exhausted'
    )
    legacy.assert_not_called()


def test_ladder_only_execution_bypasses_legacy_dispatch_and_fails_closed_on_budget_error(monkeypatch):
    from utils import ladder_v1

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(ladder_v1, 'budget_snapshot', lambda *a, **k: None)
    assert cap.sync_allowed('synthetic')
    monkeypatch.setattr(ladder_v1, 'budget_snapshot', Mock(side_effect=RuntimeError('ledger unavailable')))
    assert not cap.sync_allowed('synthetic')


async def test_live_minute_refresh_stops_funded_audio_after_ladder_crossing(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    allowance = SimpleNamespace(
        managed=True, remaining_seconds=None, reason='usage_budget_available', remaining_units=None, budget_units=None
    )
    monkeypatch.setattr(cap, 'funded_allowance', lambda *a, **k: allowance)

    async def run(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap, 'run_blocking', run)
    state = cap.LiveAdmission('synthetic')
    await state.refresh()
    raw = Mock(send=Mock(return_value=True))
    # Crossing just after a flush permits at most the next minute's audio.
    for _ in range(60):
        state.send(raw, b'\0' * 32000, 'modulate', 16000)
    allowance = SimpleNamespace(
        managed=False, remaining_seconds=0, reason='usage_budget_exhausted', remaining_units=0, budget_units=100
    )
    await state.refresh()
    for _ in range(60):
        state.send(raw, b'\0' * 32000, 'modulate', 16000)
    assert raw.send.call_count == 60


@pytest.mark.parametrize('percent,interval', [(0, 900), (50, 900), (95, 60)])
@pytest.mark.parametrize('dispatch', [False, True])
async def test_ladder_live_estimate_debits_locally_and_bounds_rescans(monkeypatch, percent, interval, dispatch):
    from utils.transcription_allowance import TranscriptionAllowance

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(dispatch).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    now = [0]
    monkeypatch.setattr(cap.time, 'monotonic', lambda: now[0])
    budget = 100000
    resolver = Mock(
        return_value=TranscriptionAllowance(
            'managed', None, 'usage_budget_available', remaining_units=budget * (1 - percent / 100), budget_units=budget
        )
    )
    monkeypatch.setattr(cap, 'funded_allowance', resolver)

    async def run(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap, 'run_blocking', run)
    state = cap.LiveAdmission('synthetic')
    await state.refresh()
    raw = Mock(send=Mock(return_value=True))
    token = cap.current_live_admission.set(state)
    try:
        socket = await cap.live_provider('modulate', 0)(AsyncMock(return_value=raw))(16000)
    finally:
        cap.current_live_admission.reset(token)
    before = state.remaining_units
    for second in range(1, interval):
        now[0] = second
        socket.send(b'\0' * 32000)
        await state.refresh(force=False)
    assert state.remaining_units < before
    assert resolver.call_count == 1
    now[0] = interval
    await state.refresh(force=False)
    assert resolver.call_count == 2
    # Local exhaustion suppresses every subsequent provider packet, including
    # ladder-only activation with the legacy dispatch switch still dark.
    state.remaining_units = cap._units_per_second('modulate') * 0.5
    state.remaining = state.remaining_units / cap._units_per_second()
    sent = raw.send.call_count
    for _ in range(100):
        socket.send(b'\0' * 32000)
    assert raw.send.call_count == sent
    assert state.reason == 'usage_budget_exhausted'
    await state.refresh(force=True)  # Subscription invalidation bypasses cadence.
    assert resolver.call_count == 3


async def test_ladder_only_legacy_profile_keeps_long_read_cadence_and_invalidates(monkeypatch):
    from utils.transcription_allowance import TranscriptionAllowance

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    now = [0]
    monkeypatch.setattr(cap.time, 'monotonic', lambda: now[0])
    resolver = Mock(return_value=TranscriptionAllowance('managed', None, 'legacy_dispatch_disabled'))
    monkeypatch.setattr(cap, 'funded_allowance', resolver)

    async def run(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(cap, 'run_blocking', run)
    state = cap.LiveAdmission('synthetic')
    await state.refresh()
    for second in (60, 120, 899):
        now[0] = second
        await state.refresh(force=False)
    assert resolver.call_count == 1
    now[0] = 900
    await state.refresh(force=False)
    assert resolver.call_count == 2
    resolver.return_value = TranscriptionAllowance(
        'managed', None, 'usage_budget_available', remaining_units=10000, budget_units=10000
    )
    await state.refresh(force=True)
    assert resolver.call_count == 3
    assert state.remaining_units == 10000


def test_live_notice_is_a_session_scoped_durable_receipt():
    event = SttCapLiveHeldEvent(session_id='socket-1', held_seconds=12, paused=True, reset_at=123)
    assert event.to_json() == {
        'type': 'stt_cap_live_held',
        'session_id': 'socket-1',
        'held_seconds': 12,
        'paused': True,
        'reset_at': 123,
    }


def test_provider_capture_observer_sees_only_actual_admission(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    state = cap.LiveAdmission('synthetic')
    state.managed, state.remaining = True, 1
    observer = Mock()
    state.capture_observer = observer
    raw = Mock(send=Mock(return_value=True))
    socket = cap.CapSocket(state, 'soniox', 16000, AsyncMock(), raw)
    packet = b'\0' * 32000
    assert not cap.suppress_socket_audio(socket, packet, start_sample=0)
    assert socket.send(packet)
    assert cap.suppress_socket_audio(socket, packet, start_sample=16000)
    assert [c.args[-1] for c in observer.call_args_list] == [True, False]
    raw.send.assert_called_once()


def test_vad_preroll_observer_uses_actual_spans_not_current_input(monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    state = cap.LiveAdmission('synthetic')
    state.managed, state.remaining = True, None
    observer = Mock()
    state.capture_observer = observer
    socket = cap.CapSocket(state, 'soniox', 16000, AsyncMock(), Mock(send=Mock(return_value=True)))
    data = b'\1\0' * 100 + b'\2\0' * 200
    cap.set_cap_capture(socket, data, ((100, 100), (900, 200)))
    assert socket.send(data)
    assert [call.args for call in observer.call_args_list] == [
        (b'\1\0' * 100, 16000, 100, True),
        (b'\2\0' * 200, 16000, 900, True),
    ]


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize(
    'cohort,lanes,admitted',
    [
        (None, 'live', False),
        ('', 'live', False),
        ('uid:synthetic', 'live', True),
        ('uid:other', 'live', False),
        ('all', 'sync,batch', False),
    ],
)
def test_actual_receiver_passes_authenticated_uid_and_live_lane(monkeypatch, ladder, cohort, lanes, admitted):
    from routers.listen import receiver

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.delenv('STT_CAP_DISPATCH_COHORT', raising=False)
    if cohort is not None:
        monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', cohort)
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    monkeypatch.setattr(receiver, 'session_recovery_enabled', lambda host: False)
    host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic', source='omi'),
        state=SimpleNamespace(),
        use_custom_stt=False,
        is_multi_channel=True,
    )
    value = receiver.ListenReceiver(host, [], {})
    assert (value.cap_admission is not None) is admitted
    assert (value.live_hold is not None) is admitted
    if admitted:
        assert value.cap_admission.uid == 'synthetic'


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize('cohort,lanes', [('', 'live,sync,batch'), ('uid:other', 'sync'), ('all', 'live')])
def test_downstream_sync_boundary_has_no_allowance_reads_outside_scope(monkeypatch, ladder, cohort, lanes):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setenv('STT_CAP_DISPATCH_COHORT', cohort)
    monkeypatch.setenv('STT_CAP_DISPATCH_LANES', lanes)
    allowance = Mock(side_effect=AssertionError('out-of-scope allowance read'))
    monkeypatch.setattr(cap, 'funded_allowance', allowance)
    assert cap.sync_allowed('synthetic')
    allowance.assert_not_called()


def test_unknown_downstream_lane_cannot_authorize_spend(monkeypatch):
    with pytest.raises(ValueError, match='unknown cap dispatch lane'):
        cap.sync_allowed('synthetic', lane='typo')


def _identity_trap_host(shape, custom):
    class RequestTrap(SimpleNamespace):
        @property
        def request(self):
            raise AssertionError('cap bypass touched request')

    class UIDTrap:
        @property
        def uid(self):
            raise AssertionError('cap bypass touched uid')

    if shape == 'request_raises':
        return RequestTrap(is_multi_channel=True, use_custom_stt=custom, state=SimpleNamespace())
    host = SimpleNamespace(is_multi_channel=True, use_custom_stt=custom, state=SimpleNamespace())
    if shape == 'uid_missing':
        host.request = SimpleNamespace(source='omi')
    elif shape == 'uid_raises':
        host.request = UIDTrap()
    return host


@pytest.mark.parametrize('shape', ['request_missing', 'request_raises', 'uid_missing', 'uid_raises'])
def test_actual_receiver_flags_off_short_circuits_before_identity(monkeypatch, shape):
    from routers.listen import receiver

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setattr(receiver, 'session_recovery_enabled', lambda host: False)
    scoped = Mock(side_effect=AssertionError('flag-off consulted scoped admission'))
    monkeypatch.setattr(receiver, 'stt_cap_dispatch_enabled', scoped)
    value = receiver.ListenReceiver(_identity_trap_host(shape, False), [], {})
    assert value.cap_admission is None and value.live_hold is None
    scoped.assert_not_called()


@pytest.mark.parametrize('legacy,ladder', [(True, False), (False, True), (True, True)])
@pytest.mark.parametrize('shape', ['request_missing', 'request_raises', 'uid_missing', 'uid_raises'])
def test_actual_receiver_custom_stt_short_circuits_before_identity(monkeypatch, legacy, ladder, shape):
    from routers.listen import receiver

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(legacy).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    monkeypatch.setattr(receiver, 'session_recovery_enabled', lambda host: False)
    scoped = Mock(side_effect=AssertionError('custom STT consulted scoped admission'))
    monkeypatch.setattr(receiver, 'stt_cap_dispatch_enabled', scoped)
    value = receiver.ListenReceiver(_identity_trap_host(shape, True), [], {})
    assert value.cap_admission is None and value.live_hold is None
    scoped.assert_not_called()


@pytest.mark.parametrize('ladder', [False, True])
@pytest.mark.parametrize('shape,error', [('uid_missing', AttributeError), ('uid_raises', AssertionError)])
def test_actual_receiver_active_admission_requires_identity_without_fallback(monkeypatch, ladder, shape, error):
    from routers.listen import receiver

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', str(not ladder).lower())
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(ladder).lower())
    with pytest.raises(error):
        receiver.ListenReceiver(_identity_trap_host(shape, False), [], {})


def test_actual_receiver_idle_cohort_armed_still_never_touches_identity(monkeypatch):
    """The Soniox idle cohort resolves its uid lazily; even with the cohort
    armed, receiver construction must not consult the listen request's identity
    on a cap-bypass path (identity traps raise on touch)."""
    from routers.listen import receiver

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_PERCENT', '100')
    monkeypatch.setenv('SONIOX_IDLE_COHORT_CLOSE_SECONDS', '30')
    monkeypatch.setattr(receiver, 'session_recovery_enabled', lambda host: False)
    value = receiver.ListenReceiver(_identity_trap_host('request_raises', False), [], {})
    assert value.soniox_idle_budget is not None
