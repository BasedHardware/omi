"""Tests for the executor-backed listen persistence boundary."""

import pytest

from routers.listen.contracts import ListenLimits, ListenSessionState
from routers.listen.persistence import ListenPersistence
from routers.listen import runtime as listen_runtime


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
async def test_credit_refresh_fetches_with_source_and_emits_threshold_event(monkeypatch):
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

    assert runtime.state.freemium_threshold_sent is True
    assert events[0].remaining_seconds == 120
    assert (listen_runtime.get_remaining_transcription_seconds, ('user-1',), {'source': 'desktop'}) in calls


async def _completed():
    return None
