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
