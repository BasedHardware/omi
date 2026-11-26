"""Pipeline-lab spend ledger: reserve before send, hard cap, settle/release. Synthetic only."""

import threading

import pytest

from testing.pipeline_lab.ledger import SpendCapReached, SpendLedger


@pytest.fixture
def ledger(tmp_path):
    return SpendLedger(tmp_path / 'ledger.json', budget_usd=1.0)


def test_reserve_settle_release(ledger):
    first = ledger.reserve(0.4, purpose='llm:notes')
    assert ledger.snapshot()['in_flight_usd'] == pytest.approx(0.4)
    ledger.settle(first, 0.1)
    second = ledger.reserve(0.3)
    ledger.release(second)
    snap = ledger.snapshot()
    assert snap['settled_usd'] == pytest.approx(0.1)
    assert snap['in_flight_usd'] == 0
    assert snap['requests'] == 2


def test_cap_counts_in_flight_reservations(ledger):
    ledger.reserve(0.6)
    with pytest.raises(SpendCapReached):
        ledger.reserve(0.5)
    assert ledger.snapshot()['refused'] == 1
    assert ledger.spent() == pytest.approx(0.6)


def test_settle_over_estimate_never_raises_but_blocks_next(ledger):
    reservation = ledger.reserve(0.2)
    ledger.settle(reservation, 1.3)  # the call already happened; record the truth
    assert ledger.exhausted()
    with pytest.raises(SpendCapReached):
        ledger.reserve(0.0001)


def test_ledger_persists_across_instances(tmp_path):
    path = tmp_path / 'ledger.json'
    SpendLedger(path, budget_usd=1.0).settle(SpendLedger(path, budget_usd=1.0).reserve(0.5), 0.5)
    assert SpendLedger(path, budget_usd=1.0).spent() == pytest.approx(0.5)


def test_concurrent_reservations_never_exceed_the_cap(ledger):
    granted = []
    refused = []

    def take():
        try:
            granted.append(ledger.reserve(0.15))
        except SpendCapReached:
            refused.append(1)

    threads = [threading.Thread(target=take) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(granted) == 6 and len(refused) == 14
    assert ledger.spent() <= 1.0


def test_negative_amounts_rejected(ledger):
    with pytest.raises(ValueError):
        ledger.reserve(-1)
    with pytest.raises(ValueError):
        SpendLedger(ledger.path, budget_usd=-1)
