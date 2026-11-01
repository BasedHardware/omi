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


@pytest.mark.parametrize('provider', ['soniox', 'modulate', 'deepgram'])
@pytest.mark.parametrize('configured,expected', [(None, 30), ('0', 0), ('2', 2), ('10000', 10000)])
def test_budget_valid_caps_and_unset_default(monkeypatch, provider, configured, expected):
    setting = f'STT_PAID_SPILLOVER_{provider.upper()}_PER_MINUTE'
    if configured is None:
        monkeypatch.delenv(setting, raising=False)
    else:
        monkeypatch.setenv(setting, configured)
    assert paid_admission.limit(provider) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['soniox', 'modulate', 'deepgram'])
@pytest.mark.parametrize('configured', ['typo-private-value', '', '1.5', '-1', '10001'])
async def test_invalid_budget_denies_before_redis_and_logs_once(monkeypatch, provider, configured):
    setting = f'STT_PAID_SPILLOVER_{provider.upper()}_PER_MINUTE'
    monkeypatch.setenv(setting, configured)
    monkeypatch.setattr(paid_admission, '_client', None)
    monkeypatch.setattr(paid_admission, '_invalid_config_logged', set())
    redis = Mock(side_effect=AssertionError('invalid cap must not create Redis client'))
    monkeypatch.setattr(paid_admission.aioredis, 'Redis', redis)
    warning = Mock()
    monkeypatch.setattr(paid_admission.logger, 'warning', warning)
    with pytest.raises(ValueError):
        paid_admission.limit(provider)
    assert not any(await asyncio.gather(*(paid_admission.admit(provider) for _ in range(12))))
    redis.assert_not_called()
    warning.assert_called_once()
    message = warning.call_args.args[0] % warning.call_args.args[1:]
    assert setting in message
    if configured:
        assert configured not in message
    # Config is read at the call boundary, so correcting it restores admission.
    monkeypatch.setenv(setting, '2')
    monkeypatch.setattr(paid_admission, '_client', MinuteRedis())
    assert await paid_admission.admit(provider)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mode,budget,expected,percent',
    [
        ('on', True, 'soniox', 100),
        ('on', False, 'modulate', 100),
        ('on', 'invalid', 'modulate', 100),
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
    if budget == 'invalid':
        monkeypatch.setenv('STT_PAID_SPILLOVER_SONIOX_PER_MINUTE', 'typo')
        admission = AsyncMock(side_effect=AssertionError('invalid cap must not reach Redis'))
        monkeypatch.setattr(paid_admission, '_client', SimpleNamespace(eval=admission))
    else:
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
    assert admission.await_count == (1 if mode == 'on' and percent > 0 and budget != 'invalid' else 0)


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
    assert MAX_RECOVERY_TARGETS >= MAX_REGISTRY_TARGETS + 4
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


@pytest.mark.asyncio
async def test_budget_denial_skipped_attempt_spends_no_admission(monkeypatch, isolated):
    """A backoff-gated (skipped) paid promotion must not burn the Redis budget:
    admission is spent only after the backoff lease exists for a real dial."""
    from utils.stt import connect_backoff as connect_backoff_module

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('STT_PAID_SPILLOVER_BUDGET_ENABLED', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('PARAKEET_FULL', 'true')
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    _prime_chain(
        monkeypatch,
        [
            dict(id='parakeet-window', family='parakeet', cost_per_audio_hour=0.02, capacity_env='PARAKEET_FULL'),
            dict(id='soniox', family='soniox', cost_per_audio_hour=0.04),
            dict(id='modulate-velma-2', family='modulate', cost_per_audio_hour=0.05),
        ],
    )
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda targets, _: {t.id: GateState() for t in targets})
    admission = AsyncMock(return_value=True)
    monkeypatch.setattr(paid_admission, 'admit', admission)

    # Soniox (the cost-ordered paid promotion after Parakeet capacity refusal)
    # sits inside an open connect-backoff window, so its route is skipped.
    backoff = connect_backoff_module.ConnectRefusalBackoff(clock=lambda: 0.0)
    monkeypatch.setattr(live_chain, 'connect_backoff', lambda: backoff)
    soniox_state = backoff._state('soniox', 'soniox')
    soniox_state.refusals.extend([0.0, 0.0, 0.0])
    soniox_state.open = True
    soniox_state.cooldown_until = 60.0

    async def paid():
        return SimpleNamespace(is_connection_dead=False)

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
    assert service.value == 'modulate'  # configured order restored without any dial on Soniox
    # The skipped Soniox promotion never reaches Redis: the only admission is
    # the real Modulate dial. (The pre-fix gate spent a second admission on the
    # backoff-skipped Soniox attempt before any lease existed.)
    assert admission.await_count == 1
    admission.assert_awaited_once_with('modulate')


@pytest.mark.asyncio
async def test_cheap_reentry_grant_consumed_by_new_identity_dial(monkeypatch, isolated):
    """The no-text lease failback authorizes exactly one Parakeet dial: after
    the first Parakeet reservation (even under a new endpoint identity), the
    configured-chain retry after TargetEngineMismatch cannot dial Parakeet
    again through the grant."""
    host = SimpleNamespace(state=SimpleNamespace(active=True), stt_language='en')
    recovery = LiveRecoveryController(host)
    recovery.mark_attempted('parakeet-window')
    recovery.mark_attempted('soniox')
    recovery.begin(family='soniox')
    assert recovery.grant_cheap_reentry('parakeet-window')
    # Lease-return dial lands on a different Parakeet endpoint identity.
    assert recovery.reserve('parakeet-custom-endpoint', 'parakeet')
    assert 'parakeet-custom-endpoint' in recovery.attempted_targets
    # The grant is consumed by the first Parakeet-family reservation...
    assert not recovery._cheap_reentry_available('parakeet-window')
    # ...so the original window identity cannot re-enter through the grant.
    assert not recovery.can_attempt('parakeet-window')
    assert not recovery.reserve('parakeet-window', 'parakeet')


def test_malformed_routing_percent_keeps_legacy_failover_alive(monkeypatch):
    """A malformed STT_ROUTING_ON_PERCENT must degrade the rebuild cap to the
    router-off policy, not abort legacy failover selection with ValueError."""
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', 'not-a-number')
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
    # Router-on cap (MAX_RECOVERY_TARGETS=20) would allow the rebuild; the
    # malformed percent must fall back to the managed router-off cap of 3,
    # which this receiver has already exhausted.
    assert live_recovery.select_live_replacement(receiver, 'modulate', select, managed=True) == (None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['off', 'shadow', 'on'])
@pytest.mark.parametrize('allocation', ['private-malformed-value', '-1', '101', 'nan', 'inf'])
async def test_invalid_hard_permission_is_bounded_chain_unavailability(monkeypatch, isolated, mode, allocation):
    monkeypatch.setenv('STT_ROUTING_MODE', mode)
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', allocation)
    connect = AsyncMock()
    fallback = Mock()
    monkeypatch.setattr(live_chain, 'record_fallback', fallback)
    before = live_chain.COST_FAIL_OPEN.labels(reason='router_error')._value.get()
    failed = set()
    failed_targets = set()
    with pytest.raises(live_chain.ProviderChainUnavailable) as caught:
        await live_chain.connect_configured_chain(
            primary_service=STTService.parakeet,
            connect_primary=connect,
            callbacks={STTService.soniox: connect},
            failed=failed,
            failed_targets=failed_targets,
            models=['parakeet-window', 'soniox'],
            routing_uid='synthetic',
            routing_language='en',
            routing_models={'parakeet': 'parakeet-window', 'soniox': 'soniox'},
        )
    assert caught.value.retry_after == 5
    assert allocation not in str(caught.value)
    connect.assert_not_awaited()
    assert failed == failed_targets == set()
    assert live_chain.COST_FAIL_OPEN.labels(reason='router_error')._value.get() == before + 1
    fallback.assert_called_once_with(
        component='stt_selection',
        from_mode='parakeet',
        to_mode='parakeet',
        reason='config_incomplete',
        outcome='degraded',
    )
