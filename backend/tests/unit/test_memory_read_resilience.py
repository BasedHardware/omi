"""Deterministic read retry budgets and circuit admission; no provider IO."""

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import FailedPrecondition, ServiceUnavailable

from utils.memory.read_resilience import (
    MemoryReadCircuitOpen,
    MemoryReadResilience,
    RetryAllowance,
    memory_store_read,
    transient_store_error,
)
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


class Clock:
    def __init__(self):
        self.now = 10.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    clock = Clock()
    return MemoryReadResilience(
        clock=clock, sleep=clock.sleep, jitter=lambda low, high: 0.05, allowance=RetryAllowance(clock=clock)
    )


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
        return memory_store_read(lambda: ['recovered'])

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


def test_memory_request_attempts_are_shared_with_retry_eligible_fallback(policy):
    budget = ListReadBudget(deadline_monotonic=12, clock=policy.clock)
    calls = []

    def read():
        calls.append(True)
        unavailable()

    for operation in ['read_page', 'read']:
        with pytest.raises(HTTPException):
            policy.call(operation, read, budget=budget)
    # With TWO SECONDS headroom the original implementation issued four calls.
    assert len(calls) == 2
    assert budget.remaining_seconds == pytest.approx(1.95)


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


def test_memory_first_attempt_requires_process_admission(monkeypatch, policy):
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '0')
    calls = []
    with pytest.raises(HTTPException):
        policy.call('read', lambda: calls.append(True))
    assert calls == []


def test_memory_circuit_opening_during_backoff_admits_zero_post_open_retries(policy):
    calls = 0

    def read():
        nonlocal calls
        calls += 1
        unavailable()

    def open_during_backoff(_seconds):
        # Other requests exhaust three failures while the original caller sleeps.
        original_sleep = policy.sleep
        policy.sleep = lambda _: None
        try:
            for _ in range(3):
                with pytest.raises(HTTPException):
                    policy.call('read', unavailable)
        finally:
            policy.sleep = original_sleep

    policy.sleep = open_during_backoff
    with pytest.raises(HTTPException):
        policy.call('read', read)
    assert calls == 1  # one primary, zero retries after the opening


def test_memory_malformed_cursor_probe_keeps_circuit_open_until_store_success(policy):
    for _ in range(3):
        with pytest.raises(HTTPException):
            policy.call('read_page', unavailable)
    policy.clock.sleep(5)

    def malformed_cursor():
        raise HTTPException(400, 'invalid_or_stale_cursor:malformed_cursor')

    with pytest.raises(HTTPException) as error:
        policy.call('read_page', malformed_cursor)
    assert error.value.status_code == 400
    with pytest.raises(MemoryReadCircuitOpen):
        policy.call('read_page', lambda: memory_store_read(lambda: []))
    policy.clock.sleep(5)
    assert policy.call('read_page', lambda: memory_store_read(lambda: [])) == []
    assert policy.call('read_page', lambda: []) == []


def test_memory_success_without_store_evidence_keeps_probe_open(policy):
    for _ in range(3):
        with pytest.raises(HTTPException):
            policy.call('read_page', unavailable)
    policy.clock.sleep(5)
    assert policy.call('read_page', lambda: []) == []
    with pytest.raises(MemoryReadCircuitOpen):
        policy.call('read_page', lambda: [])


def test_memory_process_retry_allowance_is_shared_configurable_and_refills(monkeypatch):
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '2')
    clock = Clock()
    bucket = RetryAllowance(clock=clock)
    policies = [
        MemoryReadResilience(clock=clock, sleep=lambda _: None, jitter=lambda *_: 0, allowance=bucket) for _ in range(3)
    ]
    calls = []

    def read():
        calls.append(True)
        unavailable()

    for policy in policies:
        with pytest.raises(HTTPException):
            policy.call('read', read)
    assert len(calls) == 2
    clock.sleep(1)
    with pytest.raises(HTTPException):
        policies[0].call('read', read)
    assert len(calls) == 3  # only one replenished whole-operation token


def test_memory_retry_allowance_caps_inflight_even_after_tokens_refill(monkeypatch):
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '2')
    clock = Clock()
    bucket = RetryAllowance(clock=clock)
    assert bucket.take()
    assert bucket.take()
    clock.sleep(3)
    assert not bucket.take()  # replenishment cannot exceed two in-flight retries
    bucket.release()
    assert bucket.take()
    bucket.release()
    bucket.release()
