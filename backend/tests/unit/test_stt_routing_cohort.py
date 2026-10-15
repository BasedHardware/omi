"""Cohort attribution exercises the production emitters and adapter boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from routers.listen import runtime as runtime_module
from tests.unit.test_live_session_transcript_outcome import _runtime
from tests.unit.test_soniox_idle_close import build
from utils.observability import transcription
from utils.observability.fallback import record_fallback
from utils.observability.routing_cohort import (
    COHORT_OUTCOMES,
    COHORT_PAID_AUDIO,
    RoutingCohort,
    current_routing_cohort,
)
from utils.stt import live_session, streaming


def value(arm, signal, outcome):
    return COHORT_OUTCOMES.labels(routing_arm=arm, signal=signal, outcome=outcome)._value.get()


async def finish_runtime(runtime):
    runtime.request.owner_persistence_blocked = SimpleNamespace(is_set=lambda: True)

    async def teardown():
        pass

    runtime._teardown_components = teardown
    await runtime._teardown()


@pytest.mark.parametrize(
    'mode,percent,expected',
    [('off', '0', 'off'), ('shadow', '0', 'shadow'), ('on', '100', 'on'), ('on', '0', 'off'), ('on', 'invalid', 'off')],
)
async def test_runtime_pins_cohort_before_initialization(monkeypatch, mode, percent, expected):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', percent)
    monkeypatch.setattr(runtime_module, 'managed_chain_enabled', lambda _: True)
    runtime = _runtime(terminal=True)
    runtime._capture_cost_routing_arm()
    assert runtime._routing_cohort.arm == expected
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    before = value(expected, 'transcript', 'no_transcript')
    with patch.object(runtime_module, 'record_live_session_transcript_outcome'):
        runtime._record_session_transcript_outcome()
        runtime._record_session_transcript_outcome()
        await finish_runtime(runtime)
    assert value(expected, 'transcript', 'no_transcript') == before + 1


def test_unmanaged_sessions_have_no_cohort(monkeypatch):
    monkeypatch.setattr(runtime_module, 'managed_chain_enabled', lambda _: False)
    runtime = _runtime(delivered=True)
    runtime._capture_cost_routing_arm()
    assert runtime._routing_cohort is None


@pytest.mark.parametrize('outcome', ['success', 'failure', 'cancelled'])
def test_terminal_attempt_pins_cohort_and_counts_once(outcome):
    cohort = RoutingCohort('on')
    token = current_routing_cohort.set(cohort)
    try:
        attempt = transcription.LiveSTTAttempt(provider='soniox', platform='ios', emitter=Mock())
    finally:
        current_routing_cohort.reset(token)
    before = value('on', 'terminal', outcome)
    attempt.finish(outcome, phase='teardown')
    attempt.finish(outcome, phase='teardown')
    assert value('on', 'terminal', outcome) == before + 1


@pytest.mark.asyncio
async def test_child_task_pre_audio_failure_and_exhaustion_keep_assigned_arm():
    cohort = RoutingCohort('shadow')
    token = current_routing_cohort.set(cohort)
    terminal = value('shadow', 'terminal', 'failure')
    exhausted = value('shadow', 'fallback_exhausted', 'yes')

    async def initialize():
        transcription.record_live_stt_pre_audio_failure(provider='modulate', platform='ios', phase='initialization')
        for _ in range(2):
            record_fallback(
                component='stt_selection',
                from_mode='modulate',
                to_mode='none',
                reason='connection_lost',
                outcome='exhausted',
            )

    task = asyncio.create_task(initialize())
    current_routing_cohort.reset(token)
    await task
    cohort.finish('no_transcript', terminal_after_text=False)
    cohort.finish('no_transcript', terminal_after_text=False)
    assert value('shadow', 'terminal', 'failure') == terminal + 1
    assert value('shadow', 'fallback_exhausted', 'yes') == exhausted + 1
    assert current_routing_cohort.get() is None


def test_unrelated_fallback_is_excluded():
    cohort = RoutingCohort('off')
    token = current_routing_cohort.set(cohort)
    try:
        record_fallback(
            component='sync_dispatch', from_mode='none', to_mode='none', reason='other', outcome='exhausted'
        )
    finally:
        current_routing_cohort.reset(token)
    assert not cohort.exhausted


@pytest.mark.parametrize('recovery', [False, True])
async def test_runtime_terminal_after_text_uses_existing_recovery_gate(monkeypatch, recovery):
    runtime = _runtime(delivered=True, terminal=True)
    runtime._routing_cohort = RoutingCohort('on')
    monkeypatch.setattr(runtime_module, 'session_recovery_enabled', lambda _: recovery)
    outcome = 'yes' if recovery else 'no'
    before = value('on', 'terminal_after_text', outcome)
    with patch.object(runtime_module, 'record_live_session_transcript_outcome'):
        runtime._record_session_transcript_outcome()
        await finish_runtime(runtime)
    assert value('on', 'terminal_after_text', outcome) == before + 1


@pytest.mark.parametrize('family', ['soniox', 'modulate', 'deepgram', 'parakeet'])
def test_paid_audio_counts_accepted_live_replay_and_successor_sends(monkeypatch, family):
    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    cohort = RoutingCohort('on')
    token = current_routing_cohort.set(cohort)
    recv = SimpleNamespace(
        host=SimpleNamespace(language='en', request=SimpleNamespace(uid='synthetic')),
        _telemetry_platform=lambda: 'ios',
        client_closing=False,
    )
    session = live_session.LiveChainSession(recv)
    raw = SimpleNamespace(send=Mock(return_value=True), is_connection_dead=False, finish=Mock(), finalize=Mock())
    try:
        leg = live_session.LiveLegSocket(raw, None, session, streaming.STTService(family), 16000, False, False)
    finally:
        current_routing_cohort.reset(token)
    provider = family if family != 'parakeet' else 'soniox'
    counter = COHORT_PAID_AUDIO.labels(routing_arm='on', provider=provider)
    before = counter._value.get()
    assert leg.send(b'\x00\x00' * 16000)
    leg._replaying = True
    assert leg.send(b'\x00\x00' * 8000)
    assert leg.send_admitted_audio(b'\x00\x00' * 8000, ())
    assert counter._value.get() == before  # completed sockets only
    raw.send.return_value = False
    assert not leg.send(b'\x00\x00' * 16000)
    cohort.finish('transcribed', terminal_after_text=False)
    cohort.finish('transcribed', terminal_after_text=False)
    assert counter._value.get() == before + (2 if family != 'parakeet' else 0)


@pytest.mark.asyncio
async def test_idle_reopen_counts_when_paid_transport_accepts_not_when_buffered(monkeypatch):
    cohort = RoutingCohort('on')
    token = current_routing_cohort.set(cohort)
    try:
        socket, idle, _, peers, _, tick = build(monkeypatch)
        socket.send(b'\x00\x00' * 1600, wall_time=100)
        tick[0] += 3
        socket.send(b'\x00\x00' * 1600, wall_time=103)
        await idle._close_task
        before = cohort._paid['soniox']
        assert idle.send(b'\x01\x00' * 1600)
        assert cohort._paid['soniox'] == before
        assert await idle.complete_send()
        assert cohort._paid['soniox'] == pytest.approx(before + 0.1)
        assert len(peers) == 2
        await idle.drain_and_close()
    finally:
        current_routing_cohort.reset(token)


def test_cohort_labels_have_only_closed_values_from_process_start():
    from prometheus_client import REGISTRY

    for arm in ('off', 'shadow', 'on'):
        assert (
            REGISTRY.get_sample_value(
                'omi_stt_routing_cohort_outcomes_total',
                {'routing_arm': arm, 'signal': 'fallback_exhausted', 'outcome': 'yes'},
            )
            is not None
        )
    with pytest.raises(ValueError):
        RoutingCohort('synthetic-user-id')


@pytest.mark.asyncio
@pytest.mark.parametrize('crash', [False, True])
async def test_run_restores_parent_context_on_success_and_error(crash):
    parent = RoutingCohort('shadow')
    token = current_routing_cohort.set(parent)
    runtime = _runtime()
    runtime.recovery_enabled = False

    async def run():
        assert current_routing_cohort.get() is None
        current_routing_cohort.set(RoutingCohort('on'))
        if crash:
            raise RuntimeError('synthetic runtime failure')

    runtime._run = run
    try:
        if crash:
            with pytest.raises(RuntimeError):
                await runtime.run()
        else:
            await runtime.run()
        assert current_routing_cohort.get() is parent
    finally:
        current_routing_cohort.reset(token)


@pytest.mark.asyncio
async def test_final_cleanup_settlement_and_paid_audio_precede_cohort_completion():
    runtime = _runtime(delivered=True)
    cohort = runtime._routing_cohort = RoutingCohort('on')
    runtime.request.owner_persistence_blocked = SimpleNamespace(is_set=lambda: True)
    token = current_routing_cohort.set(cohort)
    before = value('on', 'fallback_exhausted', 'yes')
    paid = COHORT_PAID_AUDIO.labels(routing_arm='on', provider='soniox')
    paid_before = paid._value.get()

    async def teardown():
        # Same order as runtime: headline outcome precedes receiver finish.
        with patch.object(runtime_module, 'record_live_session_transcript_outcome'):
            runtime._record_session_transcript_outcome()
        record_fallback(
            component='stt_live_session',
            from_mode='soniox',
            to_mode='none',
            reason='connection_lost',
            outcome='exhausted',
        )
        cohort.paid_audio('soniox', 0.5)

    runtime._teardown_components = teardown
    try:
        await runtime._teardown()
        await runtime._teardown()
    finally:
        current_routing_cohort.reset(token)
    assert value('on', 'fallback_exhausted', 'yes') == before + 1
    assert paid._value.get() == paid_before + 0.5


async def test_companion_metric_failure_cannot_break_terminal_or_cleanup():
    runtime = _runtime(delivered=True)
    cohort = runtime._routing_cohort = RoutingCohort('on')
    runtime._routing_cohort_completion = ('transcribed', False)
    token = current_routing_cohort.set(cohort)
    try:
        attempt = transcription.LiveSTTAttempt(provider='soniox', platform='ios', emitter=Mock())
        with patch.object(COHORT_OUTCOMES, 'labels', side_effect=RuntimeError('synthetic metric failure')):
            attempt.finish('success', phase='transcript_delivery')
            await finish_runtime(runtime)
        assert attempt.finished
    finally:
        current_routing_cohort.reset(token)
