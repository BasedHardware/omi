"""Bounded admission tests for the listen reconnect guard."""

from utils.listen_reconnect_budget import ListenReconnectBudget


def test_per_uid_budget_rejects_and_refills():
    now = [0.0]
    budget = ListenReconnectBudget(per_minute=6, burst=3, clock=lambda: now[0])

    assert [budget.admit('uid')[0] for _ in range(3)] == [True, True, True]
    admitted, retry_after = budget.admit('uid')
    assert not admitted
    assert retry_after == 10

    now[0] += 10
    assert budget.admit('uid') == (True, 0)


def test_per_device_budgets_do_not_make_multi_device_users_share_a_burst():
    budget = ListenReconnectBudget(per_minute=6, burst=3)

    assert [budget.admit('uid', 'ios_12345678')[0] for _ in range(3)] == [True, True, True]
    assert budget.admit('uid', 'ios_12345678')[0] is False
    assert budget.admit('uid', 'macos_87654321') == (True, 0)


def test_budget_evicts_least_recently_used_and_expires_idle_entries():
    now = [0.0]
    budget = ListenReconnectBudget(max_entries=2, ttl_seconds=30, clock=lambda: now[0])

    budget.admit('first')
    now[0] += 1
    budget.admit('second')
    budget.admit('first')  # Refresh LRU position.
    budget.admit('third')
    assert budget.size == 2
    assert budget.admit('second') == (True, 0)  # Evicted key receives a fresh burst.

    now[0] += 31
    budget.admit('fresh')
    assert budget.size == 1


def test_concurrent_admissions_never_exceed_the_burst():
    from concurrent.futures import ThreadPoolExecutor

    budget = ListenReconnectBudget(per_minute=60, burst=3)
    with ThreadPoolExecutor(max_workers=12) as executor:
        admitted = list(executor.map(lambda _: budget.admit('uid')[0], range(24)))

    assert sum(admitted) == 3


def test_clock_samples_are_serialized_with_concurrent_bucket_updates():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    first_sampled = Event()
    release_first = Event()
    second_sampled = Event()
    call_lock = Lock()
    call_count = 0

    def clock():
        nonlocal call_count
        with call_lock:
            call_count += 1
            call = call_count
        if call == 1:
            first_sampled.set()
            assert release_first.wait(timeout=2)
            return 1.0
        second_sampled.set()
        return 2.0

    budget = ListenReconnectBudget(per_minute=60, burst=3, clock=clock)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(budget.admit, 'uid')
        assert first_sampled.wait(timeout=2)
        second = executor.submit(budget.admit, 'uid')
        # With the clock under the admission lock, the second call cannot
        # sample time until the first has updated the bucket.
        assert not second_sampled.wait(timeout=0.05)
        release_first.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert budget._buckets[('uid', None)].updated_at == 2.0
