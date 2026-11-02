"""Tests for the executor-backed listen persistence boundary."""

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest

from models.users import PlanType
from routers.listen.contracts import ListenLimits, ListenSessionState
from routers.listen.persistence import ListenPersistence
from routers.listen import runtime as listen_runtime


def test_should_emit_plus_meter_warning_is_plus_only():
    from types import SimpleNamespace

    assert listen_runtime.should_emit_plus_meter_warning(None) is False
    assert listen_runtime.should_emit_plus_meter_warning(SimpleNamespace(plan=PlanType.basic)) is False
    assert listen_runtime.should_emit_plus_meter_warning(SimpleNamespace(plan=PlanType.unlimited)) is False
    assert listen_runtime.should_emit_plus_meter_warning(SimpleNamespace()) is False
    assert listen_runtime.should_emit_plus_meter_warning(SimpleNamespace(plan=PlanType.plus)) is True


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_listen_persistence_offloads_and_preserves_call_arguments(monkeypatch):
    captured = {}

    def write(uid, *, value):
        return f'{uid}:{value}'

    async def fake_run_blocking(executor, function, *args, **kwargs):
        captured.update(executor=executor, function=function, args=args, kwargs=kwargs)
        return function(*args, **kwargs)

    monkeypatch.setattr('routers.listen.persistence.run_blocking', fake_run_blocking)

    result = await ListenPersistence().call(write, 'user-1', value='stored')

    assert result == 'user-1:stored'
    assert captured['function'] is write
    assert captured['args'] == ('user-1',)
    assert captured['kwargs'] == {'value': 'stored'}


@pytest.mark.anyio
async def test_credit_refresh_decrements_cached_credits_and_preserves_source(monkeypatch):
    from types import SimpleNamespace

    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', source='desktop')
    runtime.limits = ListenLimits(credits_refresh_seconds=900)
    runtime.state = ListenSessionState(
        remaining_seconds_cache=300,
        remaining_seconds_cache_ts=100.0,
        remaining_seconds_cache_initialized=True,
    )
    runtime.user_has_credits = True
    calls = []

    async def call(function, *args, **kwargs):
        calls.append((function, args, kwargs))
        if function is listen_runtime.check_credits_invalidation:
            return False
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return None
        raise AssertionError(f'unexpected persistence call: {function}')

    runtime.persistence = SimpleNamespace(call=call)
    runtime.asend_event = lambda _event: None
    monkeypatch.setattr(listen_runtime.time, 'time', lambda: 101.0)

    await runtime._refresh_credits(transcription_seconds=15)

    assert runtime.state.remaining_seconds_cache == 285
    assert runtime.user_has_credits is True
    assert not any(function is listen_runtime.get_remaining_transcription_seconds for function, _, _ in calls)


@pytest.mark.anyio
async def test_credit_refresh_fetches_with_source_and_skips_threshold_for_basic(monkeypatch):
    from types import SimpleNamespace

    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', source='desktop')
    runtime.limits = ListenLimits(credits_refresh_seconds=900)
    runtime.state = ListenSessionState()
    runtime.user_has_credits = True
    events = []
    calls = []

    async def call(function, *args, **kwargs):
        calls.append((function, args, kwargs))
        if function is listen_runtime.check_credits_invalidation:
            return False
        if function is listen_runtime.get_remaining_transcription_seconds:
            return 120
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return None
        raise AssertionError(f'unexpected persistence call: {function}')

    async def asend_event(event):
        events.append(event)

    runtime.persistence = SimpleNamespace(call=call)
    runtime.asend_event = asend_event
    monkeypatch.setattr(listen_runtime, 'send_credit_limit_notification', lambda _uid: _completed())

    await runtime._refresh_credits()

    assert runtime.state.freemium_threshold_sent is False
    assert events == []
    assert (listen_runtime.get_remaining_transcription_seconds, ('user-1',), {'source': 'desktop'}) in calls


@pytest.mark.anyio
async def test_credit_refresh_emits_threshold_event_for_plus(monkeypatch):
    from types import SimpleNamespace

    from models.users import PlanType

    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', source='desktop')
    runtime.limits = ListenLimits(credits_refresh_seconds=900)
    runtime.state = ListenSessionState()
    runtime.user_has_credits = True
    events = []
    calls = []

    async def call(function, *args, **kwargs):
        calls.append((function, args, kwargs))
        if function is listen_runtime.check_credits_invalidation:
            return False
        if function is listen_runtime.get_remaining_transcription_seconds:
            return 120
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return SimpleNamespace(plan=PlanType.plus)
        raise AssertionError(f'unexpected persistence call: {function}')

    async def asend_event(event):
        events.append(event)

    runtime.persistence = SimpleNamespace(call=call)
    runtime.asend_event = asend_event
    monkeypatch.setattr(listen_runtime, 'send_credit_limit_notification', lambda _uid: _completed())

    await runtime._refresh_credits()

    assert runtime.state.freemium_threshold_sent is True
    assert events[0].remaining_seconds == 120
    assert (listen_runtime.get_remaining_transcription_seconds, ('user-1',), {'source': 'desktop'}) in calls


async def _completed():
    return None


@pytest.mark.anyio
@pytest.mark.parametrize('enforce,legacy', [(True, False), (False, False), (True, True)])
async def test_without_funded_admission_keeps_main_long_refresh(monkeypatch, enforce, legacy):
    from types import SimpleNamespace
    from unittest.mock import Mock

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', str(enforce).lower())
    monkeypatch.setattr(listen_runtime.ladder_policy, 'entitlements', lambda _: None if legacy else {'plan_id': 'plus'})
    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', source='desktop')
    runtime.limits = ListenLimits(credits_refresh_seconds=900)
    runtime.state = ListenSessionState(
        remaining_seconds_cache=None, remaining_seconds_cache_ts=100, remaining_seconds_cache_initialized=True
    )
    runtime.user_has_credits = True
    # Custom STT has no funded socket; it must not scan the ledger each minute.
    runtime.receiver = SimpleNamespace(cap_admission=None)
    reads = Mock(return_value=0)

    async def call(function, *args, **kwargs):
        if function is listen_runtime.check_credits_invalidation:
            return False
        if function is listen_runtime.get_remaining_transcription_seconds:
            assert kwargs == {'source': 'desktop'}
            return reads()
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return SimpleNamespace(plan=PlanType.operator)
        raise AssertionError(function)

    runtime.persistence = SimpleNamespace(call=call)
    # Budget crosses immediately after the previous read; no chunk performs IO.
    for now in (110, 159, 160):
        monkeypatch.setattr(listen_runtime.time, 'time', lambda: now)
        await runtime._refresh_credits(transcription_seconds=10)
        if now < 160:
            reads.assert_not_called()
    reads.assert_not_called()
    assert runtime.user_has_credits
    monkeypatch.setattr(listen_runtime.time, 'time', lambda: 1000)
    await runtime._refresh_credits(transcription_seconds=10)
    reads.assert_called_once()
    assert not runtime.user_has_credits


@pytest.mark.anyio
@pytest.mark.parametrize('plan,remaining', [(PlanType.operator, 0), (PlanType.plus, 0.5)])
async def test_ladder_refresh_reuses_funded_admission_snapshot(monkeypatch, plan, remaining):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(listen_runtime.ladder_policy, 'entitlements', lambda _: {'plan_id': 'plus'})
    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='user-1', source='desktop')
    runtime.limits = ListenLimits()
    runtime.state = ListenSessionState()
    runtime.stt_service = 'modulate'
    admission = SimpleNamespace(refresh=AsyncMock(), remaining=remaining, managed=remaining > 0, omi_selected=True)
    runtime.receiver = SimpleNamespace(cap_admission=admission, cap_paused=False)
    runtime.asend_event = AsyncMock()
    monkeypatch.setattr(listen_runtime, 'send_credit_limit_notification', AsyncMock())

    async def call(function, *args, **kwargs):
        if function is listen_runtime.check_credits_invalidation:
            return False
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return SimpleNamespace(plan=plan)
        raise AssertionError('redundant budget read')

    runtime.persistence = SimpleNamespace(call=call)
    await runtime._refresh_credits()
    admission.refresh.assert_awaited_once()
    assert runtime.state.remaining_seconds_cache == remaining
    assert runtime.user_has_credits is (remaining > 0)
    if plan == PlanType.plus:
        event = runtime.asend_event.call_args.args[0]
        assert event.remaining_seconds == 0
        assert type(event.remaining_seconds) is int
    else:
        runtime.asend_event.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize('remaining', [0, 100, None])
async def test_ladder_only_admission_preserves_legacy_monthly_credit_state(monkeypatch, remaining):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setattr(listen_runtime.ladder_policy, 'entitlements', lambda _: None)
    monkeypatch.setattr(listen_runtime.time, 'time', lambda: 101)
    monkeypatch.setattr(listen_runtime, 'send_credit_limit_notification', AsyncMock())
    runtime = object.__new__(listen_runtime.ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='legacy', source='desktop')
    runtime.limits = ListenLimits(credits_refresh_seconds=900)
    runtime.state = ListenSessionState(
        remaining_seconds_cache=remaining, remaining_seconds_cache_ts=100, remaining_seconds_cache_initialized=True
    )
    runtime.stt_service = 'modulate'
    runtime.asend_event = AsyncMock()
    admission = SimpleNamespace(
        refresh=AsyncMock(), reason='legacy_dispatch_disabled', remaining=None, managed=True, omi_selected=True
    )
    runtime.receiver = SimpleNamespace(cap_admission=admission, cap_paused=False)

    async def call(function, *args, **kwargs):
        if function is listen_runtime.check_credits_invalidation:
            return False
        if function is listen_runtime.user_db.get_user_valid_subscription:
            return SimpleNamespace(plan=PlanType.plus)
        raise AssertionError('unexpected legacy or ladder read')

    runtime.persistence = SimpleNamespace(call=call)
    await runtime._refresh_credits()
    assert runtime.state.remaining_seconds_cache == remaining
    assert runtime.user_has_credits is (remaining is None or remaining > 0)
    assert admission.remaining is None  # Legacy dispatch remains disabled, without bypassing its credit meter.
