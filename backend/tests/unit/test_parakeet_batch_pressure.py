"""Real cached fleet refresh and admission policy, with synthetic metrics only."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
import yaml

from utils.stt import batch_pressure as pressure_module
from utils.stt.live_metrics import WINDOW_PRESSURE_REFRESH, WINDOW_PRESSURE_REFUSAL, WINDOW_PRESSURE_REPLICAS


def seed(pressure, now, busy=False):
    pressure._ready = ('10.0.0.1', '10.0.0.2')
    pressure._samples = {ip: pressure_module.ReplicaPressure(4 if busy else 0, 0.0, now) for ip in pressure._ready}
    pressure._observed_at = now


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2')
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', 'tdt-headless.invalid')
    for name in ('MAX_LIVE_PENDING_PER_REPLICA', 'MAX_LIVE_OLDEST_SECONDS', 'BUSY_REPLICA_SHARE'):
        monkeypatch.delenv('PARAKEET_BATCH_PRESSURE_' + name, raising=False)


@pytest.mark.asyncio
async def test_batch_pressure_cache_never_waits_at_admission_and_stands_down(monkeypatch):
    pressure = pressure_module.BatchPressure()
    began = asyncio.Event()
    release = asyncio.Event()
    missing_before = WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get()
    pressure_before = WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get()
    stale_before = WINDOW_PRESSURE_REFUSAL.labels(reason='stale')._value.get()

    async def refresh(_host, _replicas, _client):
        began.set()
        await release.wait()
        seed(pressure, pressure_module.time.monotonic(), busy=True)

    monkeypatch.setattr(pressure, '_refresh', refresh)
    assert not pressure.allows('tdt-headless.invalid', 2)  # admission never starts a poll
    assert WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get() == missing_before + 1
    assert pressure._task is None
    pressure.start('tdt-headless.invalid', 2)
    try:
        await began.wait()
        assert not pressure.allows('tdt-headless.invalid', 2)
        release.set()
        await asyncio.sleep(0)
        assert not pressure.allows('tdt-headless.invalid', 2)
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get() == pressure_before + 1
        pressure._observed_at -= pressure.STALE_SECONDS + 1
        assert not pressure.allows('tdt-headless.invalid', 2)  # stale signal: fleet stands down
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='stale')._value.get() == stale_before + 1
    finally:
        await pressure.stop()


@pytest.mark.asyncio
async def test_batch_pressure_keeps_sample_fresh_between_rare_admissions(monkeypatch):
    pressure = pressure_module.BatchPressure()
    pressure.REFRESH_SECONDS = 0.01
    clock = [100.0]
    monkeypatch.setattr(pressure_module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    refreshed = asyncio.Event()
    calls = 0

    async def refresh(_host, _replicas, _client):
        nonlocal calls
        calls += 1
        seed(pressure, clock[0])
        refreshed.set()

    monkeypatch.setattr(pressure, '_refresh', refresh)
    pressure.start('tdt-headless.invalid', 2)
    try:
        assert not pressure.allows('tdt-headless.invalid', 2)
        await refreshed.wait()
        assert pressure.allows('tdt-headless.invalid', 2)
        for _ in range(2):
            refreshed.clear()
            clock[0] += 16.0
            await asyncio.wait_for(refreshed.wait(), 1)
            assert pressure.allows('tdt-headless.invalid', 2)
        assert calls >= 3
    finally:
        await pressure.stop()


@pytest.mark.asyncio
async def test_batch_pressure_poller_retries_exception_starts_once_and_stops(monkeypatch):
    pressure = pressure_module.BatchPressure()
    pressure.REFRESH_SECONDS = 0.01
    recovered = asyncio.Event()
    calls = 0
    unavailable_before = WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable')._value.get()

    async def refresh(_host, _replicas, _client):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('transient poll failure')
        seed(pressure, pressure_module.time.monotonic())
        recovered.set()

    monkeypatch.setattr(pressure, '_refresh', refresh)
    pressure.start('tdt-headless.invalid', 2)
    task = pressure._task
    pressure.start('tdt-headless.invalid', 2)
    assert pressure._task is task
    try:
        await asyncio.wait_for(recovered.wait(), 1)
        assert pressure.allows('tdt-headless.invalid', 2)
        assert calls >= 2
        assert WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable')._value.get() == unavailable_before + 1
    finally:
        await pressure.stop()
    assert task.done()
    assert pressure._task is None
    assert not pressure.allows('tdt-headless.invalid', 2)


@pytest.mark.asyncio
async def test_batch_pressure_poller_off_configuration_does_no_work(monkeypatch):
    pressure = pressure_module.BatchPressure()
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    pressure.start_from_env()
    assert pressure._task is None
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '1')
    monkeypatch.delenv('PARAKEET_BATCH_PRESSURE_POOL_HOST')
    pressure.start_from_env()
    assert pressure._task is None
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', 'tdt-headless.invalid')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', 'nan')
    pressure.start_from_env()
    assert pressure._task is None
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '1')
    monkeypatch.setattr(pressure, '_refresh', AsyncMock())
    pressure.start_from_env()
    task = pressure._task
    assert task is not None
    pressure.start_from_env()
    assert pressure._task is task
    await pressure.stop()


@pytest.mark.asyncio
async def test_batch_pressure_reuses_bounded_client_until_shutdown(monkeypatch):
    pressure = pressure_module.BatchPressure()
    pressure.REFRESH_SECONDS = 0.01
    created = []
    used = []
    refreshed_twice = asyncio.Event()

    class Client:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.closed = False
            created.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

    async def refresh(_host, _replicas, client):
        used.append(client)
        if len(used) == 2:
            refreshed_twice.set()

    monkeypatch.setattr(pressure_module.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(pressure, '_refresh', refresh)
    pressure.start('tdt-headless.invalid', 2)
    try:
        await asyncio.wait_for(refreshed_twice.wait(), 1)
        assert len(created) == 1
        assert used[:2] == [created[0], created[0]]
        assert created[0].options['timeout'] == 1.0
        assert created[0].options['trust_env'] is False
        limits = created[0].options['limits']
        assert limits.max_connections == pressure.MAX_REPLICAS
        assert limits.max_keepalive_connections == pressure.MAX_REPLICAS
        assert not created[0].closed
    finally:
        await pressure.stop()
    assert created[0].closed


def test_batch_pressure_poller_can_restart_on_a_new_event_loop(monkeypatch):
    pressure = pressure_module.BatchPressure()
    clients = []

    class Client:
        def __init__(self, **_kwargs):
            self.closed = False
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

    monkeypatch.setattr(pressure_module.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(pressure, '_refresh', AsyncMock())

    async def one_lifecycle():
        pressure.start('tdt-headless.invalid', 2)
        task = pressure._task
        await asyncio.sleep(0)
        await pressure.stop()
        assert task is not None and task.done()

    asyncio.run(one_lifecycle())
    asyncio.run(one_lifecycle())
    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert all(client.closed for client in clients)


@pytest_asyncio.fixture
async def fleet(monkeypatch):
    clock = [100.0]
    ips = [f'10.0.0.{n}' for n in range(1, 7)]
    failed = set()
    payloads = {}
    calls = []
    monkeypatch.setattr(pressure_module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    lookup = AsyncMock(side_effect=lambda *_args, **_kwargs: [(None, None, None, None, (ip, 8080)) for ip in ips])
    monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', lookup)

    async def handle(request):
        ip = request.url.host
        calls.append(ip)
        await asyncio.sleep(0)
        if ip in failed:
            raise httpx.ReadTimeout('synthetic timeout')
        return httpx.Response(
            200, json=payloads.get(ip, {'live_pending_requests': 0, 'live_oldest_pending_seconds': 0})
        )

    return SimpleNamespace(
        pressure=pressure_module.BatchPressure(),
        clock=clock,
        ips=ips,
        failed=failed,
        payloads=payloads,
        calls=calls,
        lookup=lookup,
        transport=httpx.MockTransport(handle),
    )


@pytest.mark.asyncio
async def test_one_intermittently_slow_replica_never_voids_fleet_sample(fleet):
    partial_before = WINDOW_PRESSURE_REFRESH.labels(outcome='partial')._value.get()
    missing_before = WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get()
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        admitted = []
        for n in range(10):
            fleet.clock[0] = 100 + n * 5
            fleet.failed.clear()
            if n in (1, 4, 7):
                fleet.failed.add(fleet.ips[-1])
            await fleet.pressure._refresh('synthetic.invalid', 2, client)
            admitted.append(fleet.pressure.allows('synthetic.invalid', 2))
    assert admitted == [True] * 10
    assert len(fleet.calls) == 60
    assert WINDOW_PRESSURE_REFRESH.labels(outcome='partial')._value.get() == partial_before + 3
    assert WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get() == missing_before
    assert WINDOW_PRESSURE_REPLICAS.labels(state='ready')._value.get() == 6
    assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 6


@pytest.mark.asyncio
async def test_cold_partial_fleet_requires_minimum_and_strict_majority(fleet):
    missing_before = WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get()
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        fleet.failed.update(fleet.ips[3:])
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert not fleet.pressure.allows('synthetic.invalid', 2)  # Three of six is not a majority.
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 3
        fleet.failed.remove(fleet.ips[3])
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert fleet.pressure.allows('synthetic.invalid', 2)
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 4
        assert not fleet.pressure.allows('synthetic.invalid', 5)  # Configured minimum also applies.
    assert WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get() == missing_before + 2


@pytest.mark.asyncio
async def test_cached_timestamp_does_not_refresh_on_error_and_ages_out(fleet):
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        fleet.failed.update(fleet.ips[3:])
        fleet.clock[0] = 115
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert fleet.pressure._samples[fleet.ips[-1]].observed_at == 100
        assert fleet.pressure.allows('synthetic.invalid', 2)  # Exactly 15s is still fresh.
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 6
        fleet.clock[0] = 115.001
        assert not fleet.pressure.allows('synthetic.invalid', 2)
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 3
        assert WINDOW_PRESSURE_REPLICAS.labels(state='ready')._value.get() == 6
        fleet.failed.clear()
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert fleet.pressure.allows('synthetic.invalid', 2)
        fleet.clock[0] = 131
        assert not fleet.pressure.allows('synthetic.invalid', 2)  # Poller itself is stale.


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('live_pending_requests', 4), ('live_oldest_pending_seconds', 0.75)])
async def test_isolated_hot_replica_allowed_but_half_pool_pressure_refuses(fleet, field, value):
    pressure_before = WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get()
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        for n in range(1, 4):
            for ip in fleet.ips[:n]:
                fleet.payloads[ip] = {'live_pending_requests': 0, 'live_oldest_pending_seconds': 0, field: value}
            await fleet.pressure._refresh('synthetic.invalid', 2, client)
            assert fleet.pressure.allows('synthetic.invalid', 2) is (n < 3)
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get() == pressure_before + 1
        for ip in fleet.ips:
            fleet.payloads[ip] = {'live_pending_requests': 0, 'live_oldest_pending_seconds': 0, field: value}
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert not fleet.pressure.allows('synthetic.invalid', 2)
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get() == pressure_before + 2


@pytest.mark.asyncio
async def test_unknown_replicas_do_not_count_as_healthy_headroom(fleet):
    pressure_before = WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get()
    fleet.payloads[fleet.ips[0]] = {'live_pending_requests': 4, 'live_oldest_pending_seconds': 0}
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        fleet.failed.update(fleet.ips[4:])
        fleet.clock[0] = 116
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 4
        assert not fleet.pressure.allows('synthetic.invalid', 2)  # 1 hot + 2 unknown, only 3 proven healthy.
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get() == pressure_before + 1


@pytest.mark.asyncio
@pytest.mark.parametrize('replicas', [9, 16, 64])
async def test_nine_and_larger_fleets_are_polled_and_admitted(fleet, replicas):
    fleet.ips[:] = [f'10.0.0.{n}' for n in range(1, replicas + 1)]
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
    assert fleet.pressure.allows('synthetic.invalid', 2)
    assert len(fleet.calls) == replicas
    assert len(fleet.pressure._samples) == replicas
    assert WINDOW_PRESSURE_REPLICAS.labels(state='ready')._value.get() == replicas
    assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == replicas


@pytest.mark.asyncio
async def test_discovery_fanout_is_still_bounded(fleet):
    fleet.ips[:] = [f'10.0.0.{n}' for n in range(1, 66)]
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
    assert not fleet.pressure.allows('synthetic.invalid', 2)
    assert fleet.calls == []
    assert fleet.pressure._samples == {}


@pytest.mark.asyncio
async def test_dns_failure_stands_down_even_with_good_cached_replica_samples(fleet):
    missing_before = WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get()
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert fleet.pressure.allows('synthetic.invalid', 2)
        fleet.lookup.side_effect = OSError('synthetic DNS failure')
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert not fleet.pressure.allows('synthetic.invalid', 2)
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get() == missing_before + 1
        assert WINDOW_PRESSURE_REPLICAS.labels(state='ready')._value.get() == 0
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'payload',
    [
        {},
        {'live_pending_requests': 0},
        {'live_pending_requests': float('nan'), 'live_oldest_pending_seconds': 0},
        {'live_pending_requests': 1.5, 'live_oldest_pending_seconds': 0},
        {'live_pending_requests': True, 'live_oldest_pending_seconds': 0},
        {'live_pending_requests': 0, 'live_oldest_pending_seconds': -1},
        {'live_pending_requests': 0, 'live_oldest_pending_seconds': float('inf')},
    ],
)
async def test_invalid_or_old_revision_replica_is_unknown_not_a_fleet_error(fleet, payload):
    fleet.payloads[fleet.ips[-1]] = payload
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert fleet.pressure.allows('synthetic.invalid', 2)
        assert len(fleet.pressure._samples) == 5
        assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 5
        fleet.ips[:] = [fleet.ips[0], fleet.ips[-1]]
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert not fleet.pressure.allows('synthetic.invalid', 2)
        assert len(fleet.pressure._samples) == 1


@pytest.mark.asyncio
async def test_departed_replicas_are_pruned_and_new_ready_replicas_count(fleet):
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        old = fleet.ips.pop()
        fleet.ips.append('10.0.0.7')
        fleet.failed.add('10.0.0.7')
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
    assert old not in fleet.pressure._samples
    assert '10.0.0.7' not in fleet.pressure._samples
    assert len(fleet.pressure._samples) == 5
    assert WINDOW_PRESSURE_REPLICAS.labels(state='ready')._value.get() == 6
    assert WINDOW_PRESSURE_REPLICAS.labels(state='fresh')._value.get() == 5
    assert fleet.pressure.allows('synthetic.invalid', 2)


@pytest.mark.asyncio
async def test_hung_fetch_has_own_deadline_and_other_results_survive(fleet):
    fleet.pressure.REQUEST_TIMEOUT_SECONDS = 0.02
    cancelled = []
    completed = []
    never = asyncio.Event()

    async def metrics(request):
        ip = request.url.host
        if ip == fleet.ips[-1]:
            try:
                await never.wait()
            finally:
                cancelled.append(ip)
        completed.append(ip)
        return httpx.Response(200, json={'live_pending_requests': 0, 'live_oldest_pending_seconds': 0})

    async with httpx.AsyncClient(transport=httpx.MockTransport(metrics)) as client:
        await asyncio.wait_for(fleet.pressure._refresh('synthetic.invalid', 2, client), 1)
    assert cancelled == [fleet.ips[-1]]
    assert completed == fleet.ips[:-1]
    assert len(fleet.pressure._samples) == 5
    assert fleet.pressure.allows('synthetic.invalid', 2)


@pytest.mark.asyncio
async def test_pressure_thresholds_are_configurable(fleet, monkeypatch):
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_MAX_LIVE_PENDING_PER_REPLICA', '5')
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_MAX_LIVE_OLDEST_SECONDS', '1')
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_BUSY_REPLICA_SHARE', '0.75')
    for ip in fleet.ips[:3]:
        fleet.payloads[ip] = {'live_pending_requests': 4, 'live_oldest_pending_seconds': 0.75}
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert fleet.pressure.allows('synthetic.invalid', 2)
        for ip in fleet.ips[:5]:
            fleet.payloads[ip] = {'live_pending_requests': 5, 'live_oldest_pending_seconds': 1}
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
        assert not fleet.pressure.allows('synthetic.invalid', 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'name,value',
    [
        ('MAX_LIVE_PENDING_PER_REPLICA', '0'),
        ('MAX_LIVE_PENDING_PER_REPLICA', '1.5'),
        ('MAX_LIVE_OLDEST_SECONDS', 'nan'),
        ('MAX_LIVE_OLDEST_SECONDS', '-1'),
        ('BUSY_REPLICA_SHARE', '0'),
        ('BUSY_REPLICA_SHARE', '1.01'),
    ],
)
async def test_invalid_pressure_configuration_stands_down(fleet, monkeypatch, name, value):
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_' + name, value)
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        await fleet.pressure._refresh('synthetic.invalid', 2, client)
    assert not fleet.pressure.allows('synthetic.invalid', 2)
    assert fleet.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('pending,oldest', [(4, 0), (0, 0.75)])
async def test_prod_admission_retains_conservative_boundaries_and_quorum(fleet, monkeypatch, pending, oldest):
    root = Path(__file__).resolve().parents[3]
    values = yaml.safe_load((root / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml').read_text())
    env = {entry['name']: str(entry['value']) for entry in values['env'] if 'value' in entry}
    for name, value in env.items():
        if name.startswith('PARAKEET_BATCH_PRESSURE_'):
            monkeypatch.setenv(name, value)
    fleet.ips[:] = fleet.ips[:3]
    host = env['PARAKEET_BATCH_PRESSURE_POOL_HOST']
    minimum = int(env['PARAKEET_BATCH_PRESSURE_MIN_REPLICAS'])
    assert minimum == 3
    async with httpx.AsyncClient(transport=fleet.transport) as client:
        for ip in fleet.ips:
            fleet.payloads[ip] = {'live_pending_requests': 3, 'live_oldest_pending_seconds': 0.74}
        await fleet.pressure._refresh(host, minimum, client)
        assert fleet.pressure.allows(host, minimum)
        for count in (1, 2):
            fleet.payloads[fleet.ips[count - 1]] = {
                'live_pending_requests': pending,
                'live_oldest_pending_seconds': oldest,
            }
            await fleet.pressure._refresh(host, minimum, client)
            assert fleet.pressure.allows(host, minimum) is (count == 1)
        # Even an otherwise healthy fleet refuses below the production quorum.
        fleet.payloads.clear()
        fleet.failed.add(fleet.ips[-1])
        fleet.clock[0] += 16
        await fleet.pressure._refresh(host, minimum, client)
        assert not fleet.pressure.allows(host, minimum)
