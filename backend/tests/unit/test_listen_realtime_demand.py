from types import SimpleNamespace
from unittest.mock import patch

import pytest

from routers.listen.contracts import ListenSessionState
from routers.listen.realtime_demand import MAX_STATE_REPORTS, RealtimeDemandTracker
from routers.listen.receiver import ListenReceiver


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _state(foreground: bool, visible: bool) -> dict:
    return {'type': 'client_state', 'foreground': foreground, 'transcript_visible': visible}


def test_a_client_that_never_reports_is_all_unreported():
    clock = Clock()
    tracker = RealtimeDemandTracker(clock=clock)
    clock.now += 90
    assert tracker.totals() == {'visible': 0.0, 'foreground': 0.0, 'background': 0.0, 'unreported': 90.0}
    assert tracker.reported is False


def test_time_before_the_first_report_belongs_to_that_state():
    # Clients report on connect; a second of latency must not read as "unreported".
    clock = Clock()
    tracker = RealtimeDemandTracker(clock=clock)
    clock.now += 1
    assert tracker.observe(_state(False, False))
    clock.now += 59
    assert tracker.totals()['background'] == 60.0
    assert tracker.totals()['unreported'] == 0.0


def test_session_time_is_split_across_states():
    clock = Clock()
    tracker = RealtimeDemandTracker(clock=clock)
    tracker.observe(_state(False, False))
    clock.now += 600  # pocket
    tracker.observe(_state(True, True))
    clock.now += 30  # watching the live transcript
    tracker.observe(_state(True, False))
    clock.now += 10  # app open elsewhere
    totals = tracker.totals()
    assert totals == {'visible': 30.0, 'foreground': 10.0, 'background': 600.0, 'unreported': 0.0}
    assert sum(totals.values()) == 640.0
    assert tracker.totals() == totals  # reading does not consume


def test_visible_transcript_counts_as_visible_even_if_foreground_is_false():
    clock = Clock()
    tracker = RealtimeDemandTracker(clock=clock)
    tracker.observe(_state(False, True))
    clock.now += 5
    assert tracker.totals()['visible'] == 5.0


@pytest.mark.parametrize(
    'payload',
    [
        {'type': 'client_state'},
        {'type': 'client_state', 'foreground': 'yes', 'transcript_visible': False},
        {'type': 'client_state', 'foreground': True, 'transcript_visible': 1},
    ],
)
def test_malformed_state_is_ignored(payload):
    tracker = RealtimeDemandTracker(clock=Clock())
    assert tracker.observe(payload) is False
    assert tracker.reported is False


def test_reports_past_the_budget_are_ignored_but_time_keeps_accruing():
    clock = Clock()
    tracker = RealtimeDemandTracker(clock=clock)
    for i in range(MAX_STATE_REPORTS):
        assert tracker.observe(_state(True, i % 2 == 0))
    assert tracker.observe(_state(False, False)) is False
    before = tracker.totals()
    clock.now += 10
    after = tracker.totals()
    assert sum(after.values()) == pytest.approx(sum(before.values()) + 10)


@pytest.mark.anyio
async def test_receiver_routes_client_state_to_the_session_tracker():
    receiver = object.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(onboarding_handler=None, use_custom_stt=False, state=ListenSessionState())

    await receiver._handle_text('{"type":"client_state","foreground":true,"transcript_visible":false}')

    assert receiver.host.state.realtime_demand.reported is True
    assert receiver.host.state.realtime_demand.reports == 1


def test_teardown_emits_bucketed_seconds_and_one_product_event():
    clock = Clock()
    state = ListenSessionState(realtime_demand=RealtimeDemandTracker(clock=clock))
    state.realtime_demand.observe(_state(False, False))
    clock.now += 120
    receiver = object.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(
        state=state,
        recording_session_id='rec-1',
        translation_language=None,
        client_device_context=SimpleNamespace(platform='ios'),
    )
    request = SimpleNamespace(uid='u1', source='omi', sample_rate=16000, conversation_role='ambient')
    with (
        patch('routers.listen.receiver.record_listen_realtime_demand') as record,
        patch('routers.listen.receiver.emit_product_event') as emit,
    ):
        receiver._emit_realtime_demand(request, decoded_audio_bytes=16000 * 2 * 120)

    assert record.call_args.kwargs['seconds']['background'] == 120.0
    assert record.call_args.kwargs['platform'] == 'ios'
    props = emit.call_args.kwargs['properties']
    assert emit.call_args.kwargs['event'] == 'Listen Session Realtime Demand'
    assert props['background_seconds'] == 120.0 and props['visible_seconds'] == 0.0
    assert props['audio_seconds'] == 120.0 and props['client_state_reported'] is True
    # Telemetry only: no transcript text or audio leaves through this event.
    assert not any(key in props for key in ('text', 'segments', 'transcript'))


def test_teardown_telemetry_never_raises():
    receiver = object.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(state=SimpleNamespace())  # no tracker at all
    receiver._emit_realtime_demand(SimpleNamespace(uid='u1'), decoded_audio_bytes=32000)
