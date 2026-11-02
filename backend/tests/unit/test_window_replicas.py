"""A sick GPU cannot bench its siblings, and old answers cannot heal it."""

from types import SimpleNamespace

from utils.stt import streaming
from utils.stt.window_replicas import WindowReplicas, can_route_replicas, service_snapshot_allows


def test_service_grace_never_bypasses_family_or_known_pod_benches(monkeypatch):
    pressure = SimpleNamespace(ready_replicas=lambda: (), allows=lambda *_args: True)
    circuit = SimpleNamespace(state='closed')
    monkeypatch.setattr(streaming, '_parakeet_circuit', circuit)
    pool = WindowReplicas()
    assert service_snapshot_allows(pressure, streaming.parakeet_family_circuit_state(), pool)
    circuit.state = 'half_open'
    assert not service_snapshot_allows(pressure, streaming.parakeet_family_circuit_state(), pool)
    circuit.state = 'open'
    assert not service_snapshot_allows(pressure, streaming.parakeet_family_circuit_state(), pool)
    circuit.state = 'closed'
    pool.settle(pool.claim(('10.0.0.1',)), failed=True)
    assert pool.claim(()) is None
    assert not service_snapshot_allows(pressure, streaming.parakeet_family_circuit_state(), pool)
    pool.claim(('10.0.0.1', '10.0.0.2'))
    assert service_snapshot_allows(pressure, streaming.parakeet_family_circuit_state(), pool)  # healthy sibling
    pressure.ready_replicas = lambda: ('10.0.0.1',)
    assert not service_snapshot_allows(pressure, streaming.parakeet_family_circuit_state(), pool)


def test_only_default_http_family_with_ready_inventory_can_use_pods():
    ready = ('10.0.0.1',)
    assert can_route_replicas('http://parakeet', 'http://parakeet', ready)
    assert not can_route_replicas('https://parakeet', 'https://parakeet', ready)
    assert not can_route_replicas('http://override', 'http://parakeet', ready)
    assert not can_route_replicas('http://user:pass@parakeet', 'http://user:pass@parakeet', ready)
    assert not can_route_replicas('http://parakeet', 'http://parakeet', ())


def test_failure_is_local_and_half_open_has_one_probe_with_bounded_backoff():
    now = [100.0]
    pool = WindowReplicas(clock=lambda: now[0])
    a = pool.claim(('10.0.0.1',))
    pool.settle(a, failed=True)
    assert pool.claim(('10.0.0.1',)) is None
    b = pool.claim(('10.0.0.1', '10.0.0.2'))
    assert b.ip == '10.0.0.2'
    pool.settle(b, failed=False)
    for cooldown in (120, 240, 300, 300):
        now[0] += cooldown
        probe = pool.claim(('10.0.0.1',))
        assert probe is not None
        assert pool.claim(('10.0.0.1',)) is None
        pool.settle(probe, failed=True)
    now[0] += 300
    pool.settle(pool.claim(('10.0.0.1',)), failed=False)
    assert pool.claim(('10.0.0.1',)) is not None


def test_old_success_cannot_heal_new_failure_but_old_failure_still_counts_after_success():
    pool = WindowReplicas()
    old = pool.claim(('10.0.0.1',))
    failed = pool.claim(('10.0.0.1',))
    pool.settle(failed, failed=True)
    pool.settle(old, failed=False)
    assert pool.claim(('10.0.0.1',)) is None

    pool = WindowReplicas()
    good = pool.claim(('10.0.0.1',))
    bad = pool.claim(('10.0.0.1',))
    pool.settle(good, failed=False)
    pool.settle(bad, failed=True)
    assert pool.claim(('10.0.0.1',)) is None


def test_cancelled_probe_is_released_without_new_outage_evidence():
    now = [0.0]
    pool = WindowReplicas(clock=lambda: now[0])
    pool.settle(pool.claim(('10.0.0.1',)), failed=True)
    now[0] = 120
    probe = pool.claim(('10.0.0.1',))
    pool.settle(probe, failed=None)
    assert pool.claim(('10.0.0.1',)) is not None


def test_removed_pods_are_not_selected_and_storage_is_bounded():
    pool = WindowReplicas()
    old = pool.claim(('10.0.0.1',))
    assert pool.claim(('10.0.0.2',)).ip == '10.0.0.2'
    pool.settle(old, failed=True)
    assert '10.0.0.1' not in pool._states
    ready = tuple(f'10.0.0.{i}' for i in range(1, 250))
    for _ in range(200):
        pool.claim(ready)
    assert len(pool._states) <= pool.MAX_REPLICAS
    assert pool.claim(ready, exclude=frozenset(ready)) is None


def test_direct_urls_preserve_route_query_and_support_ipv6():
    pool = WindowReplicas()
    admission = pool.claim(('fd00::1',))
    assert admission.url('http://parakeet/service/v1/transcribe?model=tdt') == (
        'http://[fd00::1]:8080/service/v1/transcribe?model=tdt'
    )
