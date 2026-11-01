"""Selection hops must name why the origin route never served.

Failure-Class: FC-typed-failure-collapsed-to-generic — instance in
backend/utils/stt/live_chain.py ``connect_configured_chain`` (2026-10-20
backend-listen, listen 4bd8dae): a chain whose origin route (the policy's first
Soniox target) was skipped without a dial carried the ``'circuit_open'``
sentinel, and ``PendingLiveFailover`` normalized it through the live reason
vocabulary to ``connection_lost``. 454 of 489 ``stt_selection`` Soniox
``connection_lost`` lines in 00:00-00:30Z had no Soniox dial; most shared their
instant with the session's real ``stt_live_session`` hop. The largest exhaustion
bucket, ``selection soniox->unavailable connection_lost``, was a recovery
chain that had excluded Soniox for the session after a replay overflow and had
no other candidate.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.unit.test_live_chain_exhaustion_classification import serving  # noqa: F401 -- pytest fixture
from tests.unit.test_live_stt_chain import configured, socket  # noqa: F401 -- pytest fixture
from tests.unit.test_modulate_capacity_failover import dead_receiver
from tests.unit.test_parakeet_failover_exhausted import Replacement
from tests.unit.test_parakeet_window_live import _nonwindow_replay_leg, _stream_nonwindow, runtime  # noqa: F401
from utils.observability import fallback
from utils.stt import live_chain, live_failure, live_recovery, streaming as st
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_metrics import SESSION_LOCAL_EXCLUSION_RELEASES


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture
def hops(monkeypatch):
    events = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: events.append(kw))
    return events


def _soniox_first(**overrides):
    return dict(
        primary_service=st.STTService.soniox,
        connect_primary=overrides.get('soniox', AsyncMock(return_value=socket())),
        callbacks={st.STTService.modulate: overrides.get('modulate', AsyncMock(return_value=socket()))},
        failed=overrides.get('failed', set()),
        models=['soniox', 'modulate-velma-2'],
    )


@pytest.mark.asyncio
async def test_session_excluded_origin_is_typed_not_connection_lost(monkeypatch, hops):
    args = _soniox_first(failed={'soniox'})
    _, actual = await live_chain.connect_configured_chain(**args)

    assert actual == st.STTService.modulate
    args['connect_primary'].assert_not_called()
    [hop] = [event for event in hops if event['component'] == 'stt_selection']
    assert (hop['from_mode'], hop['to_mode'], hop['reason'], hop['outcome']) == (
        'soniox',
        'modulate',
        'session_excluded',
        'recovered',
    )


@pytest.mark.asyncio
async def test_circuit_open_origin_keeps_its_own_label(monkeypatch, hops):
    st._soniox_circuit.record_failure()
    assert st._soniox_circuit.state == 'open'
    await live_chain.connect_configured_chain(**_soniox_first())

    [hop] = [event for event in hops if event['component'] == 'stt_selection']
    assert (hop['from_mode'], hop['reason']) == ('soniox', 'circuit_open')


@pytest.mark.asyncio
async def test_exhaustion_without_a_dial_names_every_skip(monkeypatch, hops, caplog):
    args = _soniox_first(failed={'soniox', 'modulate'})
    with caplog.at_level(logging.WARNING, logger='utils.stt.live_chain'):
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(**args)

    [hop] = [event for event in hops if event['outcome'] == 'exhausted']
    assert (hop['from_mode'], hop['to_mode'], hop['reason']) == ('soniox', 'unavailable', 'session_excluded')
    [line] = [r.getMessage() for r in caplog.records if 'live_stt_chain_exhausted' in r.getMessage()]
    assert line == (
        'live_stt_chain_exhausted origin=soniox reason=session_excluded '
        'skips=soniox:session_excluded,modulate:session_excluded'
    )


@pytest.mark.asyncio
async def test_a_real_origin_death_still_reports_connection_lost_with_cause(monkeypatch, hops):
    dead = socket()
    dead.is_connection_dead = True
    dead.death_reason = dead.typed_death_reason = None
    dead.connection_cause = 'abnormal_close'
    await live_chain.connect_configured_chain(**_soniox_first(soniox=AsyncMock(return_value=dead)))

    [hop] = [event for event in hops if event['component'] == 'stt_selection']
    assert (hop['from_mode'], hop['reason'], hop['connection_cause']) == ('soniox', 'connection_lost', 'abnormal_close')


def test_skip_reasons_reach_the_metric_but_stay_out_of_live_session_hops():
    selection = PendingLiveFailover(
        component='stt_selection', from_mode='soniox', to_mode='parakeet', reason='session_excluded'
    )
    assert selection.reason == 'session_excluded'
    live = PendingLiveFailover(from_mode='soniox', to_mode='parakeet', reason='session_excluded')
    assert live.reason == 'connection_lost'
    for reason in ('session_excluded', 'recovery_budget', 'circuit_open', 'last_resort'):
        assert fallback.bucket_reason(reason) == reason


def _overflowed_soniox_receiver(reason='replay_ring_overflow'):
    receiver = dead_receiver()
    receiver.host.stt_service, receiver.host.stt_model = st.STTService.soniox, 'soniox'
    receiver.stt_socket.typed_death_reason = reason
    receiver.stt_socket.routing_target = 'soniox'
    receiver._create_stt_socket = AsyncMock(return_value=Replacement(lambda _: None))
    return receiver


@pytest.mark.anyio
async def test_overflow_exclusion_is_released_once_a_successor_is_adopted():
    receiver = _overflowed_soniox_receiver()
    before = SESSION_LOCAL_EXCLUSION_RELEASES.labels(provider='soniox')._value.get()

    assert await receiver._failover_stt_socket() is True

    # The replacement could not be Soniox itself, but the successor's next
    # ordinary death may return to the healthy provider.
    assert receiver.host.stt_service != st.STTService.soniox
    assert 'soniox' not in receiver._stt_failed_providers
    assert 'soniox' not in receiver._stt_failed_targets
    assert receiver._stt_session_local_exclusions == {}
    assert SESSION_LOCAL_EXCLUSION_RELEASES.labels(provider='soniox')._value.get() == before + 1


@pytest.mark.anyio
async def test_provider_evidence_death_keeps_the_session_exclusion():
    receiver = _overflowed_soniox_receiver(reason='connection_lost')

    assert await receiver._failover_stt_socket() is True

    assert 'soniox' in receiver._stt_failed_providers | receiver._stt_failed_targets


@pytest.mark.anyio
async def test_exclusion_release_kill_switch(monkeypatch):
    monkeypatch.setenv('LISTEN_SESSION_LOCAL_EXCLUSION_RELEASE_ENABLED', 'false')
    receiver = _overflowed_soniox_receiver()

    assert await receiver._failover_stt_socket() is True

    assert 'soniox' in receiver._stt_failed_providers | receiver._stt_failed_targets


def test_a_later_provider_death_cancels_a_pending_overflow_release():
    receiver = SimpleNamespace(
        stt_socket=SimpleNamespace(routing_target='soniox'),
        _stt_failed_providers={'soniox'},
        _stt_failed_targets=set(),
        _stt_failed_reasons={'soniox': 'connection_lost'},
    )
    live_recovery.note_session_local_exclusion(receiver, 'soniox', 'replay_ring_overflow')
    live_recovery.note_session_local_exclusion(receiver, 'soniox', 'connection_lost')
    live_recovery.release_session_local_exclusions(receiver, 'parakeet')

    assert receiver._stt_failed_providers == {'soniox'}


def _talking_soniox(leg, ring, clock, seconds, *, text_every):
    """Continuous speech with final text every few seconds that never places."""

    pcm = b'\x01\x00' * 16000
    for second in range(seconds):
        clock[0] = float(second)
        sample = second * 16000
        if second and second % text_every == 0:
            leg.note_selection_transcript([{'text': 'still talking', 'start': 0.0, 'end': 1.0}])
        from utils.stt.resilient_stream import window_replay_action

        if window_replay_action(ring, leg, pcm, sample) == 'failover':
            return second
        assert leg.send(pcm, start_sample=sample)
        ring.append(pcm, sample)
    return None


@pytest.mark.asyncio
async def test_unplaced_final_soniox_text_accounts_aged_sends(monkeypatch):
    leg, raw, ring, clock = _nonwindow_replay_leg(monkeypatch)
    raw.pending_output = True  # Active speech always has non-final tokens.

    assert _talking_soniox(leg, ring, clock, 240, text_every=3) is None

    assert not leg.is_connection_dead
    # Only sends older than the 15 s grace at the last text are accounted.
    pending = leg.window_replay_pending_sample()
    assert 222 * 16000 <= pending <= 225 * 16000
    first, _ = ring.capture_bounds
    assert first <= pending


@pytest.mark.asyncio
async def test_emitted_text_accounting_kill_switch_restores_overflow(monkeypatch):
    monkeypatch.setenv('LISTEN_NONWINDOW_EMITTED_TEXT_ACCOUNTING_ENABLED', 'false')
    leg, raw, ring, clock = _nonwindow_replay_leg(monkeypatch)
    raw.pending_output = True

    assert _talking_soniox(leg, ring, clock, 120, text_every=3) == 90
    assert leg.death_reason == 'replay_ring_overflow'


@pytest.mark.asyncio
async def test_emitted_text_accounting_is_soniox_only(monkeypatch):
    leg, raw, ring, clock = _nonwindow_replay_leg(monkeypatch, st.STTService.modulate)
    raw.pending_output = True

    assert _talking_soniox(leg, ring, clock, 120, text_every=3) == 90


@pytest.mark.asyncio
async def test_text_right_after_a_replay_burst_accounts_nothing_inside_the_grace(monkeypatch):
    leg, raw, ring, clock = _nonwindow_replay_leg(monkeypatch)
    raw.pending_output = True
    pcm = b'\x01\x00' * 16000
    for second in range(100):
        assert leg.send(pcm, start_sample=second * 16000)
    clock[0] = 10.0
    leg.note_selection_transcript([{'text': 'replayed', 'start': 0.0, 'end': 1.0}])
    assert leg.window_replay_pending_sample() == 0

    clock[0] = 16.0
    leg.note_selection_transcript([{'text': 'replayed', 'start': 1.0, 'end': 2.0}])
    assert not leg.has_untranscribed_speech()


@pytest.mark.asyncio
async def test_exhaustion_log_keeps_a_dialed_death_over_a_later_skip(monkeypatch, hops, caplog):
    dead = socket()
    dead.is_connection_dead = True
    dead.death_reason = dead.typed_death_reason = None
    args = _soniox_first(soniox=AsyncMock(return_value=dead))
    shared = live_chain.connect_backoff()

    class ModulateCooling:
        # Modulate loses its backoff lease after Soniox's dialed death, which
        # rewrites prior_reason to circuit_open without a dial of its own.
        def acquire(self, identity, *, provider, force=False):
            return None if provider == 'modulate' else shared.acquire(identity, provider=provider, force=force)

        def __getattr__(self, name):
            return getattr(shared, name)

    monkeypatch.setattr(live_chain, 'connect_backoff', lambda: ModulateCooling())
    with caplog.at_level(logging.WARNING, logger='utils.stt.live_chain'):
        with pytest.raises(live_chain.LiveChainExhausted):
            await live_chain.connect_configured_chain(**args)

    [hop] = [event for event in hops if event['outcome'] == 'exhausted']
    assert (hop['from_mode'], hop['reason']) == ('soniox', 'connection_lost')
    [line] = [r.getMessage() for r in caplog.records if 'live_stt_chain_exhausted' in r.getMessage()]
    assert ' reason=connection_lost ' in line and 'modulate:circuit_open' in line


def test_skip_series_are_exposed_before_the_first_exhaustion():
    sample = fallback.OMI_FALLBACK_TOTAL.labels(
        component='stt_selection',
        from_mode='soniox',
        to_mode='unavailable',
        reason='session_excluded',
        outcome='exhausted',
    )
    assert sample._value.get() >= 0
    names = {
        (s.labels['component'], s.labels['reason'])
        for metric in fallback.OMI_FALLBACK_TOTAL.collect()
        for s in metric.samples
    }
    assert ('stt_selection', 'recovery_budget') in names
