"""Hermetic regressions for router cache protection and unit-test isolation."""

import threading

import pytest

from config import live_stt_state
from tests.unit.conftest import _reset_live_stt_fleet_health
from tests.unit.test_live_router_hardening import MemoryRedis
from utils.stt import live_health, streaming


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['account_expiry', 'off_on'])
@pytest.mark.parametrize('endpoint', [None, 'wss://synthetic.invalid/stt'])
async def test_known_selection_survives_masking_and_redis_outage(monkeypatch, case, endpoint):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = [1000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    redis.data[live_stt_state.fleet_state_key('soniox', endpoint=endpoint)] = 'selection:1800.000'
    if case == 'account_expiry':
        redis.data[live_stt_state.fleet_state_key('soniox', account=True)] = 'account:1030.000'
    pod.cached_snapshot(['soniox'], 'en', endpoint=endpoint)
    await pod.refresh_once()
    if case == 'off_on':
        assert pod.cached_snapshot(['soniox'], 'en', endpoint=endpoint)['soniox'].bench == 'selection'
        monkeypatch.setenv('STT_ROUTING_MODE', 'off')
        await pod.refresh_once()
        assert pod.cached_snapshot(['soniox'], 'en', endpoint=endpoint)['soniox'].bench is None
        monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    else:
        assert pod.cached_snapshot(['soniox'], 'en', endpoint=endpoint)['soniox'].bench == 'account'
        now[0] = 1031.0

    class Down:
        async def mget(self, keys):
            raise OSError('synthetic outage')

    pod._client = Down()
    await pod.refresh_once()
    state = pod.cached_snapshot(['soniox'], 'en', endpoint=endpoint)['soniox']
    assert state.bench == 'selection' and state.bench_until == 1800.0
    # A later authoritative successful read can clear the retained evidence.
    pod._client = redis
    redis.data.clear()
    now[0] += 11
    await pod.refresh_once()
    assert pod.cached_snapshot(['soniox'], 'en', endpoint=endpoint)['soniox'].bench is None


@pytest.mark.asyncio
async def test_cost_refresh_snapshots_interests_under_owning_lock(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    lock = threading.RLock()
    iterations = []

    class Interests(dict):
        def __iter__(self):
            iterations.append(lock._is_owned())
            assert lock._is_owned(), 'cost interests iterated after releasing their lock'
            return super().__iter__()

    class GuardedHealth(live_health.FleetHealth):
        def __setattr__(self, name, value):
            if name == '_cost_interests':
                value = Interests(value)
            super().__setattr__(name, value)

    pod = GuardedHealth(clock=lambda: 1000, redis_client=MemoryRedis())
    pod._lock = lock
    await pod.refresh_cost_once()
    assert iterations and all(iterations)
    assert pod._cost_cached  # the refresh reached and published fake Redis state


def _reset():
    fixture = _reset_live_stt_fleet_health.__wrapped__()
    next(fixture)
    fixture.close()


def test_singleton_fixture_preserves_owning_lock_and_import_references():
    shared = live_health.health
    lock = shared._lock
    with lock:
        shared._benches['soniox'] = ('account', 9999)
        _reset()
        assert live_health.health is shared
        assert shared._lock is lock
        assert not shared._benches
        assert streaming.health is shared


@pytest.mark.parametrize('family', ['parakeet', 'deepgram', 'modulate', 'soniox'])
def test_singleton_fixture_resets_family_breaker_evidence(family):
    circuit = getattr(streaming, f'_{family}_circuit')
    circuit.record_serve_failure()
    circuit.record_account_failure()
    streaming._family_circuits_identity[family] = 'synthetic-old-identity'
    assert circuit.state == 'open'
    _reset()
    assert getattr(streaming, f'_{family}_circuit') is circuit
    assert circuit.state == 'closed'
    assert circuit.allow_request()
    assert circuit._account_cooldown is None
    assert circuit._serve_error_events == 0
    assert not streaming._family_circuits_identity
