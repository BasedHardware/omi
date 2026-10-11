"""Deterministic read retry budgets and circuit admission; no provider IO."""

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import FailedPrecondition, ServiceUnavailable

from utils.memory.read_resilience import MemoryReadCircuitOpen, MemoryReadResilience, transient_store_error
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def policy():
    clock = Clock()
    return MemoryReadResilience(clock=clock, sleep=clock.sleep, jitter=lambda low, high: 0.05)


def unavailable():
    try:
        raise ServiceUnavailable('sensitive provider details')
    except ServiceUnavailable as exc:
        raise HTTPException(503, 'Memory unavailable') from exc


def test_memory_transient_then_success(policy, caplog):
    calls = []

    def read():
        calls.append(True)
        if len(calls) == 1:
            unavailable()
        return ['memory']

    with caplog.at_level('INFO'):
        assert policy.call('read', read) == ['memory']
    assert len(calls) == 2
    record = next(r for r in caplog.records if getattr(r, 'outcome', None) == 'recovered')
    assert record.attempts == 2
    assert record.elapsed_ms == 50
    assert 'sensitive' not in caplog.text


def test_memory_permanent_failure_still_503_without_retry(policy):
    calls = []

    def read():
        calls.append(True)
        try:
            raise FailedPrecondition('missing index')
        except FailedPrecondition as exc:
            raise HTTPException(503, 'Memory unavailable') from exc

    for _ in range(4):
        with pytest.raises(HTTPException) as error:
            policy.call('read', read)
        assert error.value.status_code == 503
        assert not isinstance(error.value, MemoryReadCircuitOpen)
    assert len(calls) == 4


def test_memory_circuit_opens_then_single_probe_recovers(policy):
    calls = []

    def read():
        calls.append(True)
        unavailable()

    for _ in range(3):
        with pytest.raises(HTTPException):
            policy.call('read', read)
    assert len(calls) == 6
    with pytest.raises(MemoryReadCircuitOpen):
        policy.call('read', read)
    assert len(calls) == 6
    policy.clock.sleep(5)

    def probe():
        with pytest.raises(MemoryReadCircuitOpen):
            policy.call('read', read)
        return ['recovered']

    assert policy.call('read', probe) == ['recovered']
    assert policy.call('read', lambda: []) == []


def test_memory_failed_probe_reopens_without_retry(policy):
    for _ in range(3):
        with pytest.raises(HTTPException):
            policy.call('read', unavailable)
    policy.clock.sleep(5)
    with pytest.raises(HTTPException):
        policy.call('read', unavailable)
    with pytest.raises(MemoryReadCircuitOpen):
        policy.call('read', lambda: [])


def test_memory_slow_attempt_does_not_start_retry(policy):
    calls = []

    def read():
        calls.append(True)
        policy.clock.sleep(1.1)
        unavailable()

    with pytest.raises(HTTPException):
        policy.call('read', read)
    assert len(calls) == 1


def test_memory_request_budget_is_not_reset_by_fallback(policy):
    budget = ListReadBudget(deadline_monotonic=10.08, clock=policy.clock)
    calls = []

    def read():
        calls.append(True)
        unavailable()

    for operation in ['read_page', 'read']:
        with pytest.raises(HTTPException):
            policy.call(operation, read, budget=budget)
    assert len(calls) == 2
    assert budget.remaining_seconds == pytest.approx(0.08)
    policy.clock.sleep(1.1)
    with pytest.raises(HTTPException):
        policy.call('read', read, budget=budget)
    assert len(calls) == 3


def test_memory_scan_exhaustion_and_validation_never_retry(policy):
    for exc in [ListReadBudgetExhausted('deadline'), HTTPException(422, 'invalid'), ValueError('bad data')]:
        calls = []

        def read():
            calls.append(True)
            raise exc

        with pytest.raises(type(exc)):
            policy.call('read', read)
        assert len(calls) == 1


def test_memory_pinecone_transient_status_only():
    PineconeError = type('PineconeApiException', (Exception,), {'__module__': 'pinecone.exceptions', 'status': 429})
    assert transient_store_error(PineconeError())
    PineconeError.status = 401
    assert not transient_store_error(PineconeError())
