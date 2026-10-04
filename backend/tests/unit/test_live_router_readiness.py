"""Router-on blockers: protected breakers, fleet spillover and bounded rescue."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.live_stt_registry import MAX_REGISTRY_TARGETS, Target
from tests.unit.test_live_router_hardening import isolated, _prime_chain
from utils.stt import live_chain, live_recovery, live_router, paid_admission
from utils.stt.live_gate import GateState
from utils.stt.no_text_rescue import NoTextRescue
from utils.stt.recovery_state import LiveRecoveryController, MAX_RECOVERY_TARGETS
from utils.stt.streaming import STTService


@pytest.mark.asyncio
@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('capacity', [False, True])
async def test_all_breakers_protected_keeps_static_alias(monkeypatch, isolated, recovery, capacity):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', str(recovery).lower())
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('SYNTHETIC_FULL', str(capacity).lower())
    _prime_chain(
        monkeypatch,
        [
            dict(
                id='modulate-custom',
                family='modulate',
                cost_per_audio_hour=0.01,
                endpoint='wss://custom.invalid/stream',
                capacity_env='SYNTHETIC_FULL',
            ),
            dict(
                id='modulate-static-alias', family='modulate', cost_per_audio_hour=0.05, capacity_env='SYNTHETIC_FULL'
            ),
        ],
    )
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda targets, _: {t.id: GateState() for t in targets})
    for index in range(live_router._TARGET_CIRCUITS_CAP):
        circuit = live_router.target_circuit(
            Target(f'modulate-{index}', 'modulate', 0.05, endpoint=f'wss://protected-{index}.invalid/x')
        )
        circuit.record_serve_failure()
    assert all(c.state == 'open' for c in live_router._target_circuits.values())
    calls = []

    async def connect():
        calls.append(live_router.connecting_target.get())
        return SimpleNamespace(is_connection_dead=False)

    _, service = await live_chain.connect_configured_chain(
        primary_service=STTService.modulate,
        connect_primary=connect,
        callbacks={},
        failed=set(),
        models=['modulate-velma-2'],
        routing_uid='synthetic',
        routing_language='en',
    )
    assert service == STTService.modulate
    assert len(calls) == 1 and calls[0].endpoint is None


class MinuteRedis:
    def __init__(self):
        self.minute = 100
        self.buckets = {}

    async def eval(self, script, number, key, limit):
        assert script == paid_admission.ADMIT and number == 1
        bucket = (key, self.minute)
        count = self.buckets.get(bucket, 0)
        if count >= limit:
            return 0
        self.buckets[bucket] = count + 1
        return 1


@pytest.mark.asyncio
async def test_fleet_budget_shared_by_pods_per_provider_and_minute(monkeypatch):
    redis = MinuteRedis()
    monkeypatch.setattr(paid_admission, '_client', redis)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('STT_PAID_SPILLOVER_MODULATE_PER_MINUTE', '2')
    # Independent sessions/pods call the same atomic shared counter.
    assert sum(await asyncio.gather(*(paid_admission.admit('modulate') for _ in range(12)))) == 2
    monkeypatch.setenv('MODULATE_API_KEY', 'rotated-synthetic-account')
    assert not await paid_admission.admit('modulate')
    assert await paid_admission.admit('soniox')
    redis.minute += 1
    assert await paid_admission.admit('modulate')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert await paid_admission.admit('modulate')


@pytest.mark.asyncio
async def test_budget_redis_failure_is_conservative(monkeypatch):
    monkeypatch.setattr(paid_admission, '_client', SimpleNamespace(eval=AsyncMock(side_effect=OSError())))
    assert not await paid_admission.admit('modulate')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mode,budget,expected,percent',
    [
        ('on', True, 'soniox', 100),
        ('on', False, 'modulate', 100),
        ('shadow', True, 'modulate', 100),
        ('on', True, 'modulate', 0),
        ('off', True, 'modulate', 100),
    ],
)
async def test_budget_denial_restores_configured_order(monkeypatch, isolated, mode, budget, expected, percent):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', str(percent))
    monkeypatch.setenv('STT_PAID_SPILLOVER_BUDGET_ENABLED', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('PARAKEET_FULL', 'true')
    _prime_chain(
        monkeypatch,
        [
            dict(id='parakeet-window', family='parakeet', cost_per_audio_hour=0.02, capacity_env='PARAKEET_FULL'),
            dict(id='soniox', family='soniox', cost_per_audio_hour=0.04),
            dict(id='modulate-velma-2', family='modulate', cost_per_audio_hour=0.05),
        ],
    )
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda targets, _: {t.id: GateState() for t in targets})
    admission = AsyncMock(return_value=budget)
    monkeypatch.setattr(paid_admission, 'admit', admission)

    async def paid():
        return SimpleNamespace(is_connection_dead=False)

    # Configured order has Modulate first, cost order Soniox first.
    _, service = await live_chain.connect_configured_chain(
        primary_service=STTService.modulate,
        connect_primary=paid,
        callbacks={STTService.parakeet: paid, STTService.soniox: paid},
        failed=set(),
        models=['modulate-velma-2', 'parakeet-window', 'soniox'],
        routing_uid='synthetic',
        routing_language='en',
        routing_models={'parakeet': 'parakeet-window'},
    )
    assert service.value == expected
    assert admission.await_count == (1 if mode == 'on' and percent > 0 else 0)


def test_rescue_has_one_absolute_deadline_and_ambiguous_proof(monkeypatch):
    monkeypatch.setenv('STT_NO_TEXT_RESCUE_ENABLED', 'true')
    now = [100.0]
    rescue = NoTextRescue(recovery_enabled=True, clock=lambda: now[0])
    rescue.start('first_text_deadline')
    now[0] += 30
    rescue.start('empty_streak')  # successor swaps cannot renew the lease
    assert rescue.remaining() == 30
    now[0] += 30
    assert rescue.remaining() == 0
    rescue.complete()
    assert rescue.completed and not rescue.allow_window_rescue()
    assert not rescue.text  # no claim that the audio was noise
    rescue.start('first_text_deadline')
    assert not rescue.active


def test_rescue_default_off_and_requires_recovery(monkeypatch):
    monkeypatch.delenv('STT_NO_TEXT_RESCUE_ENABLED', raising=False)
    rescue = NoTextRescue(recovery_enabled=True)
    rescue.start('first_text_deadline')
    assert not rescue.active
    monkeypatch.setenv('STT_NO_TEXT_RESCUE_ENABLED', 'true')
    assert not NoTextRescue(recovery_enabled=False).enabled


def test_rescue_proof_requires_text_in_original_capture_interval(monkeypatch):
    monkeypatch.setenv('STT_NO_TEXT_RESCUE_ENABLED', 'true')
    rescue = NoTextRescue(recovery_enabled=True)
    rescue.start('first_text_deadline', capture_interval=(16000, 64000))
    rescue.note_transcript([{'text': 'Unmapped.'}])
    rescue.note_transcript([{'text': 'Later.', '_capture_start_sample': 64000, '_capture_end_sample': 96000}])
    rescue.note_transcript([{'text': 'Before.', '_capture_start_sample': 0, '_capture_end_sample': 16000}])
    rescue.note_transcript([{'text': '', '_capture_start_sample': 32000, '_capture_end_sample': 48000}])
    assert not rescue.text
    rescue.start('empty_streak', capture_interval=(64000, 96000))
    assert rescue.capture_interval == (16000, 64000)
    rescue.note_transcript([{'text': 'Recovered.', '_capture_start_sample': 32000, '_capture_end_sample': 48000}])
    assert rescue.text


def test_failback_does_not_bench_paid_or_reset_attempt_accounting(monkeypatch):
    monkeypatch.setenv('STT_NO_TEXT_RESCUE_ENABLED', 'true')
    rescue = NoTextRescue(recovery_enabled=True)
    rescue.start('first_text_deadline')
    host = SimpleNamespace(state=SimpleNamespace(active=True), stt_language='en')
    recovery = LiveRecoveryController(host)
    recovery.mark_attempted('parakeet-window')
    recovery.mark_attempted('soniox')
    recovery.begin(family='soniox')
    receiver = SimpleNamespace(
        host=host,
        recovery=recovery,
        _managed_live_chain=SimpleNamespace(no_text_rescue=rescue),
        stt_socket=SimpleNamespace(typed_death_reason='no_text_rescue_complete'),
        _stt_failed_targets={'parakeet-window'},
        _stt_failed_providers={'parakeet'},
        _settle_pending_live_failover_failure=Mock(),
    )
    selected = live_recovery.select_live_replacement(receiver, 'soniox', Mock(), managed=True)
    assert selected == (STTService.parakeet, 'en', 'parakeet-window')
    assert receiver._stt_failed_providers == set()
    assert recovery.reserve('parakeet-window', 'parakeet')
    assert not recovery.reserve('parakeet-window', 'parakeet')
    assert recovery.dial_attempts == 3
    assert recovery.deadline is not None  # no deadline reset


def test_rebuild_cap_tracks_registry_without_changing_shadow(monkeypatch):
    assert MAX_RECOVERY_TARGETS >= MAX_REGISTRY_TARGETS
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    host = SimpleNamespace(
        request=SimpleNamespace(uid='synthetic'),
        stt_language='en',
        language='en',
        multi_lang_enabled=False,
        language_profile=None,
        stt_service=STTService.modulate,
    )
    receiver = SimpleNamespace(
        host=host,
        stt_socket=SimpleNamespace(routing_target='fourth', _routing_active=True),
        _stt_failed_targets=set(),
        _stt_failed_providers=set(),
        _stt_failed_reasons={},
        _stt_rebuild_attempts=3,
        _settle_pending_live_failover_failure=Mock(),
        _stt_rescue_retries=set(),
    )
    monkeypatch.setattr(live_recovery, 'note_typed_provider_death', lambda *_: None)
    monkeypatch.setattr(live_recovery, 'window_selection_kwargs', lambda *_: {})
    select = Mock(return_value=(STTService.modulate, 'en', 'velma-2'))
    assert live_recovery.select_live_replacement(receiver, 'modulate', select, managed=True)[0] is not None
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    assert live_recovery.select_live_replacement(receiver, 'modulate', select, managed=True) == (None, None, None)
