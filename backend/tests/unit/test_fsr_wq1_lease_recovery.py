"""Recovery lease liveness without changing queue publisher ownership semantics."""

from __future__ import annotations

import signal
import threading

import pytest

from tests.unit.test_fsr_s2_singleton_loops import CountingFirestore, fleet  # noqa: F401
from utils.other import fsr_leader_lease as leases


def test_rolling_restart_contenders_take_over_at_tick_not_last_heartbeat(fleet, monkeypatch):
    monkeypatch.setenv('FSR_LEADER_LEASE_TTL_SECONDS', '7200')
    owner, followers = fleet.replica(), [fleet.replica() for _ in range(5)]
    permits = []
    owner.run(lambda: permits.append(leases._current_permit.get()), 300)
    old = permits[0]
    fleet.redis.advance(299)
    old.check()  # Simulate the last heartbeat before a crash, without release.
    assert fleet.redis.get(owner.keys[0]) == owner.token
    for follower in followers:
        assert follower.run(lambda: pytest.fail('before tick expiry'), 300) is None
    assert all(follower.next_check_at == 300 for follower in followers)
    fleet.redis.advance(1)
    calls = []
    for follower in followers:
        follower.run(lambda: calls.append(leases._current_permit.get()), 300)
    assert len(calls) == 1
    assert calls[0].generation == old.generation + 1
    with pytest.raises(leases.LeaseLost):
        old.check()
    owner.release(clear_tick=True)  # Former epoch cannot delete new owner's tick.
    assert fleet.redis.get(owner.keys[0]) == followers[0].token
    assert fleet.redis.get(owner.keys[2]) == calls[0].generation


def test_wedged_local_callback_has_bounded_skips_then_local_execution(fleet, monkeypatch):
    owner, follower = fleet.replica(), fleet.replica()
    entered, resume = threading.Event(), threading.Event()
    permits = []
    errors = []

    def wedged():
        permits.append(leases._current_permit.get())
        entered.set()
        if not resume.wait(5):
            errors.append('test callback did not resume')
        leases.check_leader_lease()  # Fence the old work if it eventually resumes.

    worker = threading.Thread(target=lambda: owner.run(wedged, 300))
    worker.start()
    try:
        assert entered.wait(2)
        fleet.redis.advance(299)
        assert owner.run(lambda: pytest.fail('early local fallback'), 300) is None
        assert ('test_loop', 'skipped_local_busy') in fleet.outcomes
        fleet.redis.advance(1)
        assert follower.run(lambda: 'fleet healthy', 300) == 'fleet healthy'
        fleet.redis.advance(600)
        with pytest.raises(leases.LeaseLost):
            permits[0].check()
        assert worker.is_alive()
        # Even when called in an inherited stale context, local fallback must
        # have exactly the permit-free callback contract of lever-off.
        token = leases._current_permit.set(permits[0])
        try:

            def locally():
                leases.check_leader_lease(require_ownership=True)
                assert leases._current_permit.get() is None
                return 'local healthy'

            assert owner.run(locally, 300) == 'local healthy'
            assert leases._current_permit.get() is permits[0]
        finally:
            leases._current_permit.reset(token)
        monkeypatch.setattr(leases, 'loop_lease', lambda _: owner)
        assert leases.poll_delay(300) == 300  # No expired-PTTL busy spin.
        fleet.redis.advance(300)
        assert owner.run(lambda: 'still local healthy', 300) == 'still local healthy'
        assert fleet.outcomes.count(('test_loop', 'fail_open_local')) == 2
    finally:
        resume.set()
        worker.join(timeout=2)
    assert not worker.is_alive()
    assert not errors


def test_redis_failure_during_stale_takeover_runs_every_contender_locally(fleet):
    owner = fleet.replica()
    owner.run(lambda: None, 300)
    fleet.redis.advance(300)
    fleet.redis.error = True
    assert [fleet.replica().run(lambda: 'local', 300) for _ in range(3)] == ['local'] * 3
    assert fleet.outcomes.count(('test_loop', 'redis_error')) == 3


def test_closed_lease_does_not_fail_open_even_with_wedged_mutex(fleet):
    owner = fleet.replica()
    owner._lock.acquire()
    owner._lock_started = 0
    fleet.redis.advance(1000)
    owner.release()
    try:
        assert owner.run(lambda: pytest.fail('shutdown admission'), 300) is None
    finally:
        owner._lock.release()


def test_sigterm_release_all_six_and_immediate_recovery_admission(fleet, monkeypatch):
    owners = {loop: fleet.replica(loop) for loop in leases._LOOPS}
    for owner in owners.values():
        owner.run(lambda: None, 300)
        assert fleet.redis.get(owner.keys[0]) == owner.token
    monkeypatch.setattr(leases, 'loop_lease', owners.__getitem__)
    monkeypatch.setattr(leases, '_sigterm_release_started', False)
    finished = threading.Event()
    original = leases.release_loop_leases

    def release(**kwargs):
        try:
            original(**kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(leases, 'release_loop_leases', release)
    leases.release_loop_leases_on_sigterm(signal.SIGTERM, None)
    assert finished.wait(2)
    for loop, owner in owners.items():
        assert owner.closed
        assert fleet.redis.get(owner.keys[0]) is None
        assert fleet.replica(loop).run(lambda: 'new holder', 300) == 'new holder'
    assert fleet.redis.now == 0


def test_sigterm_handler_chains_server_and_does_not_use_executor(fleet, monkeypatch):
    installed, calls = [], []
    monkeypatch.setattr(leases, '_sigterm_installed', False)
    monkeypatch.setattr(signal, 'getsignal', lambda _: lambda signum, frame: calls.append(('server', signum)))
    monkeypatch.setattr(signal, 'signal', lambda signum, handler: installed.append((signum, handler)))
    monkeypatch.setattr(leases, 'release_loop_leases_on_sigterm', lambda *args: calls.append(('release', args[0])))
    leases.install_loop_lease_sigterm_handler()
    leases.install_loop_lease_sigterm_handler()
    assert len(installed) == 1
    assert installed[0][0] == signal.SIGTERM
    installed[0][1](signal.SIGTERM, None)
    assert calls == [('release', signal.SIGTERM), ('server', signal.SIGTERM)]


def test_lever_off_keeps_signal_and_mutex_paths_untouched(fleet, monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    monkeypatch.setattr(leases, '_sigterm_installed', False)
    monkeypatch.setattr(leases, '_sigterm_release_started', False)
    monkeypatch.setattr(signal, 'signal', lambda *args: pytest.fail('lever-off signal modification'))
    leases.install_loop_lease_sigterm_handler()
    leases.release_loop_leases_on_sigterm(signal.SIGTERM, None)
    assert not leases._sigterm_release_started
    owner = fleet.replica()
    owner.closed = True
    owner._lock.acquire()
    try:
        assert [owner.run(lambda: 'local', 300) for _ in range(5)] == ['local'] * 5
    finally:
        owner._lock.release()
    assert fleet.redis.calls == 0
    assert not fleet.outcomes


def test_recovery_scans_five_replicas_ten_ticks_preserve_80_percent_read_saving(fleet, monkeypatch):
    reads = []
    for enabled in (False, True):
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"singleton_loops":100}' if enabled else '{}')
        replicas = [fleet.replica(f'recovery_proof_{enabled}') for _ in range(5)]
        client = CountingFirestore()
        for _ in range(10):
            for replica in replicas:
                replica.run(lambda: list(client.collection_group('jobs').stream()), 300)
            fleet.redis.advance(300)
        reads.append(client.reads)
    assert reads == [100, 20]
